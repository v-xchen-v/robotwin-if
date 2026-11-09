#!/usr/bin/env python3
"""Download Motus RoboTwin, Stage 1 VGM, Qwen3-VL and Wan2.2 assets."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from policies.wam.assets import main

if __name__ == "__main__":
    main("motus")
