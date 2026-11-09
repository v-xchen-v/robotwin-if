#!/usr/bin/env python3
"""Evaluate fastwam with the release's exact seeds and shared episode lifecycle."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from policies.wam.eval import main as evaluate


def main():
    return evaluate("fastwam")


if __name__ == "__main__":
    sys.exit(main())
