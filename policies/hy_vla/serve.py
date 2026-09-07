#!/usr/bin/env python3
"""Single-client Hy-VLA service preserving official per-step history and caching."""
import argparse
from datetime import datetime, timezone
import http
import json
import os
from pathlib import Path
import random
import sys
import threading
import time
import traceback

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from policies.hy_vla.client import CAMERAS, PROTOCOL, format_observation, packb, unpackb  # noqa: E402


class EpisodePolicy:
    def __init__(self, wrapper, encode_obs, seed_everywhere):
        self.wrapper, self.encode_obs, self.seed_everywhere = wrapper, encode_obs, seed_everywhere
        self.instruction = None

    def invalidate(self):
        self.instruction = None
        self.wrapper.reset()

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
                self.instruction, self.step, self.seed = instruction, 0, seed
                return {"ok": True, "server_timing": {"reset_ms": (time.monotonic() - started) * 1000}}
            if self.instruction is None:
                raise RuntimeError("Reset this connection before inference")
            if message.get("type") != "step" or type(message.get("step")) is not int or message["step"] != self.step:
                raise ValueError("Expected the next consecutive episode step")
            obs = message.get("observation")
            if not isinstance(obs, dict) or not isinstance(obs.get("images"), dict) or set(obs["images"]) != set(CAMERAS):
                raise ValueError("Expected three RGB cameras and a measured 16D EE state")
            state = obs.get("state")
            import numpy as np
            state = np.asarray(state)
            if state.shape != (16,):
                raise ValueError("Expected a measured 16D EE state")
            observation = {"observation": {name: {"rgb": obs["images"][name]} for name in CAMERAS},
                           "endpose": {"left_endpose": state[:7], "left_gripper": state[7],
                                       "right_endpose": state[8:15], "right_gripper": state[15]}}
            format_observation(observation)  # Validate RGB layout and native EE quaternions.
            action = self.wrapper.get_action(self.encode_obs(observation, self.instruction))
            if np.asarray(action).shape != (16,) or not np.isfinite(action).all():
                raise ValueError("Expected one finite 16D EE action")
            prediction = self.wrapper.last_prediction
            new_chunk = prediction is not None
            if new_chunk != (self.step % 7 == 0):
                raise RuntimeError("Official wrapper cache cadence changed")
            timing = {"step_ms": (time.monotonic() - started) * 1000, "new_chunk": new_chunk,
                      "episode_seed": self.seed, "cache_remaining": len(self.wrapper.action_cache)}
            if new_chunk:
                timing["history_steps"] = self.wrapper._eval_history_indices(self.step, 6, 5)
                timing["history_valid"] = [self.step - (5 - k) * 5 >= 0 for k in range(6)]
            response = {"action": action, "episode_step": self.step, "new_chunk": new_chunk,
                        "server_timing": timing, **(prediction or {})}
            self.step += 1
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
                    event = {"kind": body.get("type"), "episode_step": response.get("episode_step"),
                             "instruction": policy.instruction, "server_timing": response.get("server_timing")}
                    if body.get("type") == "step":
                        event["state"] = [float(value) for value in body["observation"]["state"]]
                    connection.send(packb(response))
                except Exception as exc:
                    traceback.print_exc()
                    policy.invalidate()
                    event["error"] = f"{type(exc).__name__}: {exc}"
                    connection.send(packb({"error": event["error"]}))
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=REPO_ROOT / "third_party/hy-vla")
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8015)
    parser.add_argument("--gpu", default="1")
    parser.add_argument("--cpu-threads", type=int, default=8)
    args = parser.parse_args()
    if args.cpu_threads < 1:
        parser.error("CPU threads must be positive")
    source, checkpoint, output = args.source_dir.resolve(), args.checkpoint_dir.resolve(), args.output_dir.resolve()
    from policies.hy_vla.download_checkpoint import CHECKPOINT, REVISION, SOURCE_REVISION, WEIGHTS_SHA256, NORM_SHA256, sha256
    from policies.hy_vla.patch_source import patch_source
    source_diff = patch_source(source)
    identity = json.loads((checkpoint / "checkpoint.json").read_text())
    if (identity.get("repo_id"), identity.get("revision")) != (CHECKPOINT, REVISION):
        raise ValueError("Download the pinned Hy-VLA checkpoint")
    if sha256(checkpoint / "model.safetensors") != WEIGHTS_SHA256 or sha256(checkpoint / "norm_stats.pkl") != NORM_SHA256:
        raise ValueError("Checkpoint weights/normalization checksum mismatch")
    hashes = identity.get("files_sha256", {})
    required = {"config.json", "tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "norm_stats.pkl",
                "preprocessor_config.json", "special_tokens_map.json"}
    if not required <= hashes.keys() or any(sha256(checkpoint / name) != hashes[name] for name in required):
        raise ValueError("Checkpoint assets checksum mismatch")
    os.environ.update(CUDA_VISIBLE_DEVICES=args.gpu, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONNOUSERSITE="1")
    sys.path.insert(0, str(source))
    import numpy as np
    import torch
    import transformers
    import flash_attn
    from robotwin_eval.deploy_policy import encode_obs
    from policies.hy_vla.runtime import RecordedWrapper
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    torch.set_num_threads(args.cpu_threads)
    output.mkdir(parents=True, exist_ok=False)
    wrapper = RecordedWrapper(str(checkpoint), str(checkpoint / "norm_stats.pkl"),
                              blend_mode="rel_abs", exc_action_size=7, img_history_size=6, img_history_interval=5,
                              umi_coord_frame=False, umi_gripper_space=False)
    config = wrapper.config
    if (config.chunk_size, config.n_action_steps, config.max_action_dim, config.max_state_dim,
        config.action_feature.shape[0], config.num_steps, config.use_video_encoder) != (40, 40, 32, 32, 20, 10, True):
        raise ValueError("Unexpected model architecture")
    for name, values in wrapper.norm_data.items():
        expected_shape = (20,) if name.startswith("qpos_") else (20, 20)
        if values is None or values.shape != expected_shape or not np.isfinite(values).all():
            raise ValueError(f"Unexpected rel+abs normalization statistics: {name}")
        if "std" in name and np.any(values <= 0):
            raise ValueError(f"Normalization std must be positive: {name}")
    metadata = {"protocol": PROTOCOL, "policy": "hy_vla", "checkpoint": identity,
                "created_at": datetime.now(timezone.utc).isoformat(), "source_revision": SOURCE_REVISION,
                "source_diff": source_diff, "strict_loading": True, "action_type": "ee", "action_dim": 16,
                "model_shape": [40, 20], "decoded_shape": [20, 16], "execute_horizon": 7,
                "history_size": 6, "history_interval": 5, "blend_mode": "rel_abs", "diffusion_steps": 10,
                "state_action_order": "left xyz + quaternion wxyz + gripper; right xyz + quaternion wxyz + gripper",
                "umi_coord_frame": False, "umi_gripper_space": False, "state_input": "measured EE poses and grippers",
                "normalization": "official mean/std; RT-relative + absolute halves blended 1:1 with quaternion SLERP",
                "history": "every pre-action observation; offsets [-25,-20,-15,-10,-5,0]; unavailable slots zeroed",
                "dtype": "official BF16 weights/inputs with FP32 flow sampling", "single_client": True,
                "attention": "official FlashAttention vision/MEM and eager dual-tower attention",
                "seed_control": "Reset seeds Python/NumPy/Torch; full kernel determinism not enforced",
                "torch": torch.__version__, "transformers": transformers.__version__, "flash_attn": flash_attn.__version__,
                "gpu": args.gpu, "gpu_name": torch.cuda.get_device_name(), "cpu_threads": args.cpu_threads,
                "parameter_count": sum(p.numel() for p in wrapper.policy.parameters()),
                "source_sha256": {p.name: sha256(p) for p in Path(__file__).parent.glob("*.py")}}
    (output / "server.json").write_text(json.dumps(metadata, indent=2) + "\n")
    def seed_everywhere(seed):
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    print(f"Serving Hy-VLA at ws://{args.host}:{args.port}", flush=True)
    serve_policy(EpisodePolicy(wrapper, encode_obs, seed_everywhere), metadata,
                 args.host, args.port, output / "requests.jsonl")


if __name__ == "__main__":
    main()
