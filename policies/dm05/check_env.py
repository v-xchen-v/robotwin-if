"""Check the complete official DM05 inference import path and CUDA SDPA."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path(__file__).resolve().parents[2] / "third_party/opendm")
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_dir.resolve()))
    import torch
    import transformers
    from playground.dm05_robotwin2 import DM05InferenceConfig
    from opendm.model.dm05.dm05_arch import DM05ForConditionalGeneration
    assert DM05InferenceConfig().output_action_dim == 14
    assert DM05ForConditionalGeneration.config_class.model_type == "dm05"
    assert torch.cuda.is_available(), "CUDA is required"
    q = torch.ones((1, 2, 4, 16), device="cuda", dtype=torch.bfloat16)
    assert torch.isfinite(torch.nn.functional.scaled_dot_product_attention(q, q, q)).all()
    print(json.dumps({"python": sys.version, "torch": torch.__version__, "cuda": torch.version.cuda,
                      "transformers": transformers.__version__, "gpu": torch.cuda.get_device_name()}))


if __name__ == "__main__":
    main()
