"""Seeded single-client RoboTwin service around the official LingbotVLAServer."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=REPO_ROOT / "third_party/lingbot-vla")
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8012)
    parser.add_argument("--gpu", default="0")
    parser.add_argument("--cpu-threads", type=int, default=8)
    parser.add_argument("--use-length", type=int, default=50)
    parser.add_argument("--denoising-steps", type=int, default=10)
    parser.add_argument("--use-compile", action="store_true")
    args = parser.parse_args()
    if args.cpu_threads < 1 or args.denoising_steps < 1 or not 1 <= args.use_length <= 50:
        parser.error("Threads and denoising steps must be positive; use-length must be in [1, 50]")
    source, checkpoint, output = args.source_dir.resolve(), args.checkpoint_dir.resolve(), args.output_dir.resolve()
    from download_checkpoint import CHECKPOINT, REVISION, QWEN, QWEN_REVISION
    from patch_source import patch_source
    patch_source(source)
    identity = json.loads((checkpoint / "checkpoint.json").read_text())
    if (identity.get("repo_id"), identity.get("revision")) != (CHECKPOINT, REVISION):
        raise ValueError("Use the pinned LingBot-VLA RoboTwin checkpoint")
    if identity.get("processor") != {"repo_id": QWEN, "revision": QWEN_REVISION, "directory": "qwen_processor"}:
        raise ValueError("Use the pinned Qwen processor assets")
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu
    os.environ["QWEN25_PATH"] = str(checkpoint / "qwen_processor")
    # All model assets are local after download; do not fetch moving revisions at runtime.
    os.environ["HF_HUB_OFFLINE"] = "1"
    sys.path.insert(0, str(source))
    os.chdir(source)  # Official reset resolves the robot mapping relative to its checkout.
    import torch
    from deploy.lingbot_vla_policy import LingbotVLAServer, set_seed_everywhere
    from deploy.websocket_policy_server import WebsocketPolicyServer

    torch.set_num_threads(args.cpu_threads)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required")
    output.mkdir(parents=True, exist_ok=False)
    metadata = {
        "policy": "lingbot_vla", "protocol": "lingbot_vla_robotwin_v1", "checkpoint": identity,
        "source_revision": subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip(),
        "source_diff": subprocess.check_output(["git", "-C", str(source), "diff", "HEAD"], text=True),
        "asset_sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for root, p in [(checkpoint, checkpoint / "config.json"),
                                         (checkpoint, checkpoint / "lingbotvla_cli.yaml"),
                                         (source, source / "configs/robot_configs/robotwin.yaml"),
                                         (source, source / "assets/norm_stats/robotwin_50.json")]},
        "attention": "eager (vision and joint VLM/expert attention)", "dtype": "bfloat16",
        "torch": torch.__version__, "gpu": args.gpu, "cpu_threads": args.cpu_threads,
        "use_length": args.use_length, "denoising_steps": args.denoising_steps, "compile": args.use_compile,
        "action_type": "qpos", "action_dim": 14, "single_client": True,
        "seed_control": "Each reset seeds Python/NumPy/Torch; cuDNN deterministic; full determinism not enforced",
    }
    (output / "server.json").write_text(json.dumps(metadata, indent=2) + "\n")
    model = LingbotVLAServer(str(checkpoint), use_length=args.use_length,
                            robot_norm_path=str(source / "assets/norm_stats/robotwin_50.json"),
                            num_denoising_step=args.denoising_steps, use_compile=args.use_compile)

    class SeededPolicy:
        ready = False

        def infer(self, request):
            if request.get("reset"):
                self.ready = False
                seed = request.get("seed")
                if type(seed) is not int or not 0 <= seed < 2**32:
                    raise ValueError("Reset requires a uint32 episode seed")
                if request.get("robo_name") != "robotwin":
                    raise ValueError("This checkpoint requires robo_name=robotwin")
                set_seed_everywhere(seed)
                result = model.infer(request)
                self.ready = True
                return result
            if not self.ready:
                raise RuntimeError("Reset this connection before inference")
            return model.infer(request)

    policy = SeededPolicy()

    class ExclusiveServer(WebsocketPolicyServer):
        connected = False

        async def _handler(self, websocket):
            if self.connected:
                await websocket.close(code=1013, reason="This model already has an active client")
                return
            self.connected = True
            policy.ready = False
            try:
                await super()._handler(websocket)
            finally:
                policy.ready = False
                self.connected = False

    print(f"Serving LingBot-VLA at ws://{args.host}:{args.port}", flush=True)
    ExclusiveServer(policy, host=args.host, port=args.port, metadata=metadata).serve_forever()


if __name__ == "__main__":
    main()
