"""Single-client LingBot-VA server using the official model and WebSocket protocol."""

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=REPO_ROOT / "third_party/lingbot-va")
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--gpu", default="1")
    parser.add_argument("--cpu-threads", type=int, default=8)
    parser.add_argument("--no-offload", action="store_true")
    args = parser.parse_args()
    if args.cpu_threads < 1:
        parser.error("--cpu-threads must be positive")
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu
    source, checkpoint, output = args.source_dir.resolve(), args.checkpoint_dir.resolve(), args.output_dir.resolve()
    sys.path.insert(0, str(source / "wan_va"))
    import numpy as np
    import torch
    from configs import VA_CONFIGS
    from wan_va_server import VA_Server
    from utils import init_logger
    from utils.Simple_Remote_Infer.deploy.websocket_policy_server import WebsocketPolicyServer

    torch.set_num_threads(args.cpu_threads)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required for model inference")
    identity = json.loads((checkpoint / "checkpoint.json").read_text())
    config = deepcopy(VA_CONFIGS["robotwin"])
    config.wan22_pretrained_model_name_or_path = str(checkpoint)
    config.enable_offload = not args.no_offload
    config.local_rank, config.rank, config.world_size = 0, 0, 1
    config.host, config.port, config.infer_mode = args.host, args.port, "server"
    output.mkdir(parents=True, exist_ok=False)
    config.save_root = str(output)
    init_logger()
    metadata = {
        "policy": "lingbot_va", "protocol": "lingbot_va_robotwin_v1", "checkpoint": identity,
        "source_revision": subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip(),
        "source_diff": subprocess.check_output(["git", "-C", str(source), "diff", "HEAD"], text=True),
        "transformer_config_sha256": hashlib.sha256((checkpoint / "transformer/config.json").read_bytes()).hexdigest(),
        "attention": "torch", "offload": config.enable_offload, "dtype": str(config.param_dtype),
        "cpu_threads": args.cpu_threads,
        "video_guidance_scale": config.guidance_scale, "action_guidance_scale": config.action_guidance_scale,
        "video_steps": config.num_inference_steps, "action_steps": config.action_num_inference_steps,
        "frame_chunk_size": config.frame_chunk_size, "action_per_frame": config.action_per_frame,
        "seed_control": "Reset requests seed Python, NumPy and Torch; deterministic kernels are not enforced",
        "single_client": True,
    }
    (output / "server.json").write_text(json.dumps(metadata, indent=2) + "\n")
    model = VA_Server(config)  # Upstream explicitly loads transformer with attn_mode='torch'.

    class SeededPolicy:
        def infer(self, request):
            if request.get("reset"):
                seed = request.get("seed")
                if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32:
                    raise ValueError("Reset requires a uint32 episode seed")
                random.seed(seed)
                np.random.seed(seed)
                torch.manual_seed(seed)
                torch.cuda.manual_seed_all(seed)
            return model.infer(request)

    class ExclusiveServer(WebsocketPolicyServer):
        connected = False

        async def _handler(self, websocket):
            if self.connected:
                await websocket.close(code=1013, reason="This stateful server already has an active client")
                return
            self.connected = True
            try:
                await super()._handler(websocket)
            finally:
                self.connected = False

    print(f"Serving LingBot-VA at ws://{args.host}:{args.port}", flush=True)
    ExclusiveServer(SeededPolicy(), host=args.host, port=args.port, metadata=metadata).serve_forever()


if __name__ == "__main__":
    main()
