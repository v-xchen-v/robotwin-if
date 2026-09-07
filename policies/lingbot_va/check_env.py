"""Import and CUDA checks without loading checkpoint weights."""

import argparse
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source-dir", type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.source_dir.resolve() / "wan_va"))

import torch  # noqa: E402
from wan_va_server import VA_Server  # noqa: E402, F401
from configs import VA_CONFIGS  # noqa: E402

assert VA_CONFIGS["robotwin"].used_action_channel_ids == list(range(7)) + [28] + list(range(7, 14)) + [29]
if torch.cuda.is_available():
    x = torch.ones((4, 4), dtype=torch.bfloat16, device="cuda")
    assert (x @ x).float().sum().item() == 64
print(f"LingBot-VA imports passed: torch={torch.__version__}, CUDA={torch.version.cuda}, available={torch.cuda.is_available()}")
