"""Check model imports without loading weights or allocating model GPU memory."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", choices=("fastwam", "motus", "xwam"), required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    args = parser.parse_args()
    import torch
    import torchvision
    import transformers
    from policies.wam import client, serve
    source = args.source_dir.resolve()
    if args.policy == "fastwam":
        sys.path.insert(0, str(source))
        sys.path.insert(0, str(source / "src"))
        from experiments.robotwin.fastwam_policy.deploy_policy import WorldActionRobotWinPolicy
        from fastwam.runtime import create_fastwam
    elif args.policy == "motus":
        sys.path.insert(0, str(source / "inference/robotwin/Motus"))
        from deploy_policy import MotusPolicy
        import flash_attn
    else:
        sys.path.insert(0, str(source))
        from runners.xwam_runner import XWAMRunner
        from evaluation.policy_server import build_statistics, resize_and_center_crop_tensor
        import flash_attn
    print(json.dumps({"policy": args.policy, "torch": torch.__version__, "torchvision": torchvision.__version__,
                      "transformers": transformers.__version__, "cuda_available": torch.cuda.is_available()}))


if __name__ == "__main__":
    main()
