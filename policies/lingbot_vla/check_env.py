"""Check the complete server import path and CUDA without loading weights."""

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_dir.resolve()))
    import torch
    from deploy.lingbot_vla_policy import LingbotVLAServer  # noqa: F401
    from lingbotvla.models.vla.pi0.qwenvl_in_vla import Qwen2_5_VLVisionAttention
    # Exercise the eager branch, including RoPE and separate image/window masks.
    torch.manual_seed(0)
    attention = Qwen2_5_VLVisionAttention(32, num_heads=4).eval()
    hidden = torch.randn(8, 32)
    angles = torch.randn(8, 8)
    positions = (angles.cos(), angles.sin())
    lengths = torch.tensor([0, 3, 8], dtype=torch.int32)
    with torch.no_grad():
        output = attention(hidden, lengths, position_embeddings=positions)
        altered = hidden.clone()
        altered[3:] += 10
        other = attention(altered, lengths, position_embeddings=positions)
    assert output.shape == hidden.shape and torch.isfinite(output).all()
    torch.testing.assert_close(output[:3], other[:3])
    result = {name: importlib.metadata.version(name) for name in
              ("torch", "torchvision", "lerobot", "transformers", "websockets", "msgpack")}
    result["cuda_available"] = torch.cuda.is_available()
    result["eager_vision_forward_and_mask"] = "passed"
    if result["cuda_available"]:
        result["gpu"] = torch.cuda.get_device_name()
        result["cuda_sum"] = (torch.ones(2, device="cuda") + 1).sum().item()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
