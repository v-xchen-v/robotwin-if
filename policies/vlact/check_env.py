"""Check the complete QwenOFT inference import path and CUDA SDPA."""

import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_dir.resolve()))
    from patch_source import patch_source
    patch_source(args.source_dir)
    import torch
    import transformers
    from accelerate import PartialState
    PartialState()
    from starVLA.model.framework.QwenOFT import Qwenvl_OFT
    from starVLA.model.modules.vlm.QWen3 import _QWen3_VL_Interface
    from examples.Robotwin.eval_files.model2robotwin_interface import ModelClient
    assert Qwenvl_OFT and _QWen3_VL_Interface and ModelClient
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    q = torch.randn(1, 2, 8, 64, device="cuda", dtype=torch.bfloat16)
    result = torch.nn.functional.scaled_dot_product_attention(q, q, q)
    assert result.shape == q.shape and result.isfinite().all()
    print(f"QwenOFT imports / CUDA SDPA OK; torch={torch.__version__}, transformers={transformers.__version__}")


if __name__ == "__main__":
    main()
