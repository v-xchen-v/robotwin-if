"""Check official Hy-VLA imports and the installed CUDA FlashAttention ABI."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path(__file__).resolve().parents[2] / "third_party/hy-vla")
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_dir.resolve()))
    import torch
    import transformers
    import flash_attn
    from hy_vla import HyVLA, HyVLAConfig
    from robotwin_eval.policy_wrapper import HyVLAPolicyWrapper
    assert HyVLA.config_class is HyVLAConfig
    assert hasattr(HyVLAPolicyWrapper, "get_action")
    assert torch.cuda.is_available(), "CUDA is required"
    q = torch.ones((1, 8, 2, 64), device="cuda", dtype=torch.bfloat16)
    assert torch.isfinite(flash_attn.flash_attn_func(q, q, q)).all()
    print(json.dumps({"python": sys.version, "torch": torch.__version__, "cuda": torch.version.cuda,
                      "transformers": transformers.__version__, "flash_attn": flash_attn.__version__,
                      "cxx11abi": torch._C._GLIBCXX_USE_CXX11_ABI, "gpu": torch.cuda.get_device_name()}))


if __name__ == "__main__":
    main()
