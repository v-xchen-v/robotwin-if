#!/usr/bin/env python3
"""Run the experimental paired stapler scene without changing the formal suite."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.press_lift_bell import main


if __name__ == "__main__":
    sys.exit(main(task_name="press_lift_stapler", canonical_output=True))
