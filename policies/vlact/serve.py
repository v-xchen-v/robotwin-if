"""Serve pinned VLAct Qwen3OFT with explicit RoboTwin wrap32 semantics."""

import argparse
import asyncio
import http
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=REPO_ROOT / "third_party/vlact")
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8013)
    parser.add_argument("--gpu", default="0")
    parser.add_argument("--cpu-threads", type=int, default=8)
    args = parser.parse_args()
    if args.cpu_threads < 1:
        parser.error("CPU threads must be positive")
    source, checkpoint, output = args.source_dir.resolve(), args.checkpoint_dir.resolve(), args.output_dir.resolve()
    from download_checkpoint import (CHECKPOINT, REVISION, QWEN, QWEN_REVISION, QWEN_DIRECTORY,
                                     WEIGHTS, WEIGHTS_SHA256, sha256)
    from patch_source import patch_source
    patch_source(source)
    identity = json.loads((checkpoint / "checkpoint.json").read_text())
    if (identity.get("repo_id"), identity.get("revision")) != (CHECKPOINT, REVISION):
        raise ValueError("Use the pinned VLAct RoboTwin checkpoint")
    if identity.get("base_model") != {"repo_id": QWEN, "revision": QWEN_REVISION, "directory": QWEN_DIRECTORY}:
        raise ValueError("Use the pinned Qwen3 base model assets")
    if sha256(checkpoint / WEIGHTS) != WEIGHTS_SHA256:
        raise ValueError("Checkpoint SHA-256 mismatch")
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu
    os.environ["HF_HUB_OFFLINE"] = "1"
    sys.path[:0] = [str(REPO_ROOT), str(source)]
    import numpy as np
    import torch
    import transformers
    from accelerate import PartialState
    from omegaconf import OmegaConf
    from websockets.asyncio.server import serve
    from deployment.model_server.tools.websocket_policy_server import WebsocketPolicyServer
    from starVLA.model.framework import build_framework
    from policies.vlact.codec import IMAGE_BUCKETS, decode_model_actions, resize_image

    torch.set_num_threads(args.cpu_threads)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required")
    PartialState()
    config = OmegaConf.load(checkpoint / "config.yaml")
    if (config.framework.name, config.datasets.vla_data.data_mix, config.datasets.vla_data.action_mode,
        config.framework.action_model.action_dim, config.framework.action_model.future_action_window_size,
        config.framework.action_model.past_action_window_size) != ("QwenOFT", "robotwin_wrap_32", "abs", 14, 31, 0):
        raise ValueError("Unexpected checkpoint configuration")
    if OmegaConf.to_container(config.datasets.vla_data.image_size_buckets) != IMAGE_BUCKETS:
        raise ValueError("Unexpected image buckets")
    stats = json.loads((checkpoint / "dataset_statistics.json").read_text())
    mask = stats["new_embodiment"]["action"]["mask"]
    decode_model_actions(np.zeros((32, 14)), mask)
    config.framework.qwenvl.base_vlm = str(checkpoint / QWEN_DIRECTORY)
    config.trainer.pretrained_checkpoint = None
    output.mkdir(parents=True, exist_ok=False)
    OmegaConf.save(config, output / "resolved_model_config.yaml")
    metadata = {
        "ok": True, "policy": "vlact", "protocol": "vlact_robotwin_v1", "checkpoint": identity,
        "source_revision": subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip(),
        "source_diff": subprocess.check_output(["git", "-C", str(source), "diff", "HEAD"], text=True),
        "asset_sha256": {name: sha256(checkpoint / name) for name in ("config.yaml", "dataset_statistics.json")},
        "attention": "sdpa", "dtype": "BF16 VLM and OFT head; FP32 NumPy output",
        "torch": torch.__version__, "transformers": transformers.__version__,
        "gpu": args.gpu, "gpu_name": torch.cuda.get_device_name(), "cpu_threads": args.cpu_threads,
        "use_length": 32, "action_type": "qpos", "action_dim": 14, "joint_action_mode": "wrap",
        "unnorm_key": "new_embodiment", "image_size_buckets": IMAGE_BUCKETS,
        "state_input": False, "single_client": True, "action_ensemble": False,
        "normalization": "Explicit wrap from robotwin_wrap_32; no checkpoint-path heuristic or percentile scaling",
        "gripper": "Official wrap decoder clips to [-1, 1]; no binarization",
        "seed_control": "Reset seeds Python/NumPy/Torch; full kernel determinism not enforced",
    }
    (output / "server.json").write_text(json.dumps(metadata, indent=2) + "\n")
    model = build_framework(config)
    model.norm_stats = stats
    state = torch.load(checkpoint / WEIGHTS, map_location="cpu", weights_only=True, mmap=True)
    model.load_state_dict(state, strict=True)
    del state
    model.to(device="cuda", dtype=torch.bfloat16).eval()

    class Policy:
        instruction = None

        def predict_action(self, examples, **kwargs):
            if self.instruction is None:
                raise RuntimeError("Reset this connection before inference")
            if not isinstance(examples, list) or len(examples) != 1:
                raise ValueError("Expected one example")
            example = examples[0]
            if example.get("lang") != self.instruction:
                raise ValueError("Instruction changed without reset")
            if len(example["image"]) != 3:
                raise ValueError("Expected head, left wrist, right wrist RGB")
            images = [resize_image(rgb) for rgb in example["image"]]
            result = model.predict_action(examples=[{"image": images, "lang": self.instruction}])
            predictions = np.asarray(result["normalized_actions"])
            if predictions.shape != (1, 32, 14):
                raise ValueError(f"Unexpected model output: {predictions.shape}")
            raw = predictions[0].astype(np.float32)
            return {"action": decode_model_actions(raw, mask), "model_actions": raw}

    policy = Policy()

    class Server(WebsocketPolicyServer):
        connected = False

        async def run(self):
            def health(connection, request):
                if request.path == "/healthz":
                    return connection.respond(http.HTTPStatus.OK, "OK\n")

            async with serve(self._handler, self._host, self._port, compression=None,
                             max_size=64 * 1024**2, ping_interval=None, process_request=health) as server:
                await server.serve_forever()

        async def _handler(self, websocket):
            if self.connected:
                await websocket.close(code=1013, reason="This model already has an active client")
                return
            self.connected = True
            policy.instruction = None
            try:
                await super()._handler(websocket)
            finally:
                policy.instruction = None
                self.connected = False

        def _route_message(self, msg):
            started = time.monotonic()
            if not isinstance(msg, dict):
                return {"ok": False, "error": "Expected a mapping"}
            if msg.get("type") == "reset":
                policy.instruction = None
                seed, instruction = msg.get("seed"), msg.get("instruction")
                if type(seed) is not int or not 0 <= seed < 2**32:
                    return {"ok": False, "error": "Reset requires a uint32 seed"}
                if not isinstance(instruction, str) or not instruction.strip():
                    return {"ok": False, "error": "Reset requires an instruction"}
                random.seed(seed)
                np.random.seed(seed)
                torch.manual_seed(seed)
                torch.cuda.manual_seed_all(seed)
                policy.instruction = instruction
                response = {"ok": True, "type": "reset", "seed": seed}
            else:
                response = super()._route_message(msg)
            response["server_timing"] = {"infer_ms": (time.monotonic() - started) * 1000}
            return response

    print(f"Serving VLAct at ws://{args.host}:{args.port}", flush=True)
    asyncio.run(Server(policy, host=args.host, port=args.port, metadata=metadata).run())


if __name__ == "__main__":
    main()
