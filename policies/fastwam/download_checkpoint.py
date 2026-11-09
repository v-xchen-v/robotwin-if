#!/usr/bin/env python3
"""Download the pinned official Fast-WAM RoboTwin checkpoint and Wan assets."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from policies.wam.assets import main

if __name__ == "__main__":
    main("fastwam")
