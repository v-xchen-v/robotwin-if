"""One exclusive client per seeded WAM instance; reset is required after errors."""

import argparse
from datetime import datetime, timezone
import http
import json
import os
from pathlib import Path
import random
import subprocess
import threading
import time
import traceback

import numpy as np

from policies.wam.client import CAMERAS, CONTRACTS, PROTOCOL, decode_actions, format_observation, packb, unpackb

ROOT = Path(__file__).resolve().parents[2]
SOURCE_REVISIONS = {"fastwam": "7faa71108368fbb3b6885649f112af607427a2d4",
                    "motus": "88f6fe30c62af033874b0a2e48ad1cbdaf12cfdf",
                    "xwam": "72cfb86b33fc5060963ef63412f16439fcfa472f"}
PORTS = {"fastwam": 8016, "motus": 8017, "xwam": 8018}


class EpisodePolicy:
    def __init__(self, backend, policy, seed_everywhere, *, horizon=None):
        self.backend, self.policy, self.seed_everywhere = backend, policy, seed_everywhere
        self.horizon = CONTRACTS[policy][0] if horizon is None else horizon
        self.instruction = None

    def invalidate(self):
        self.instruction = None
        self.backend.reset()

    def predict(self, obs):
        if not isinstance(obs, dict) or not isinstance(obs.get("images"), dict) or set(obs["images"]) != set(CAMERAS):
            raise ValueError("Expected three RGB cameras and 14D state")
        # Msgpack arrays view immutable bytes; pass owned, writable copies to Torch.
        obs = format_observation({
            "observation": {name: {"rgb": obs["images"][name]} for name in CAMERAS},
            "joint_action": {"vector": obs.get("state")}})
        observation = {"observation": {name: {"rgb": obs["images"][name]} for name in CAMERAS},
                       "joint_action": {"vector": obs["state"]}}
        return self.backend.predict(observation, self.instruction)

    def validate_actions(self, actions):
        return decode_actions(actions, self.horizon)

    def infer(self, message):
        started = time.monotonic()
        try:
            if not isinstance(message, dict):
                raise ValueError("Expected a mapping")
            if message.get("type") == "reset":
                self.invalidate()
                seed, instruction = message.get("seed"), message.get("instruction")
                if type(seed) is not int or not 0 <= seed < 2**32:
                    raise ValueError("Reset requires a uint32 seed")
                if not isinstance(instruction, str) or not instruction.strip():
                    raise ValueError("Reset requires an instruction")
                self.seed_everywhere(seed)
                self.instruction, self.seed, self.chunk = instruction, seed, 0
                return {"ok": True, "server_timing": {"reset_ms": (time.monotonic() - started) * 1000}}
            if self.instruction is None:
                raise RuntimeError("Reset this connection before inference")
            if message.get("type") != "infer" or type(message.get("chunk")) is not int or message["chunk"] != self.chunk:
                raise ValueError("Expected the next consecutive chunk index")
            actions = self.validate_actions(self.predict(message.get("observation")))
            response = {"ok": True, "actions": actions, "chunk": self.chunk,
                        "server_timing": {"infer_ms": (time.monotonic() - started) * 1000, "seed": self.seed}}
            self.chunk += 1
            return response
        except Exception:
            self.invalidate()
            raise


def serve_policy(policy, metadata, host, port, request_log):
    from websockets.sync.server import serve
    lock = threading.Lock()

    def health(connection, request):
        if request.path == "/healthz":
            return connection.respond(http.HTTPStatus.OK, "OK\n")

    def handler(connection):
        if not lock.acquire(blocking=False):
            connection.close(code=1013, reason="This model already has an active client")
            return
        try:
            policy.invalidate()
            connection.send(packb(metadata))
            for message in connection:
                event = {}
                try:
                    body = unpackb(message)
                    response = policy.infer(body)
                    event = {"kind": body.get("type"), "chunk": response.get("chunk"),
                             "instruction": policy.instruction, "server_timing": response.get("server_timing")}
                    connection.send(packb(response))
                except Exception as exc:
                    traceback.print_exc()
                    policy.invalidate()
                    event["error"] = f"{type(exc).__name__}: {exc}"
                    connection.send(packb({"ok": False, "error": event["error"]}))
                finally:
                    with request_log.open("a") as stream:
                        stream.write(json.dumps(event, allow_nan=False) + "\n")
        finally:
            try:
                policy.invalidate()
            finally:
                lock.release()

    with serve(handler, host, port, compression=None, max_size=64 * 1024**2,
               ping_interval=None, process_request=health) as server:
        server.serve_forever()


def main(policy_name, build_backend, *, episode_policy_class=EpisodePolicy, contract=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "third_party" / policy_name)
    parser.add_argument("--asset-dir", type=Path, required=True, help="Root created by download_checkpoint.py")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=PORTS[policy_name])
    parser.add_argument("--gpu", default="1")
    parser.add_argument("--cpu-threads", type=int, default=8)
    args = parser.parse_args()
    if args.cpu_threads < 1:
        parser.error("CPU threads must be positive")
    source, assets, output = args.source_dir.resolve(), args.asset_dir.resolve(), args.output_dir.resolve()
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != SOURCE_REVISIONS[policy_name]:
        raise ValueError("Use the pinned upstream source revision")
    if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"], text=True):
        raise ValueError("Upstream tracked source has local edits")
    if output.exists():
        raise FileExistsError(f"Use a fresh server output directory: {output}")
    from policies.wam.assets import verify_resources
    identity = verify_resources(assets, policy_name, runtime_only=True)
    os.environ.update(CUDA_VISIBLE_DEVICES=args.gpu, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                      DIFFSYNTH_SKIP_DOWNLOAD="true", PYTHONNOUSERSITE="1")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    torch.set_num_threads(args.cpu_threads)
    output.mkdir(parents=True, exist_ok=False)
    backend = build_backend(source, assets, output)
    if contract is None:
        horizon, use_length = CONTRACTS[policy_name]
        contract = {"protocol": PROTOCOL, "action_type": "qpos", "action_dim": 14,
                    "action_horizon": horizon, "use_length": use_length}
    metadata = {"ok": True, "created_at": datetime.now(timezone.utc).isoformat(),
                "policy": policy_name, **contract, "source_revision": revision,
                "assets": identity, "single_client": True,
                "torch": torch.__version__, "gpu": args.gpu, "cpu_threads": args.cpu_threads,
                "seed_control": "Each episode seeds Python/NumPy/Torch; deterministic kernels are not enforced",
                "inference": backend.metadata}
    (output / "server.json").write_text(json.dumps(metadata, indent=2) + "\n")

    def seed_everywhere(seed):
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)

    print(f"Serving {policy_name} at ws://{args.host}:{args.port}", flush=True)
    serve_policy(episode_policy_class(backend, policy_name, seed_everywhere), metadata,
                 args.host, args.port, output / "requests.jsonl")
