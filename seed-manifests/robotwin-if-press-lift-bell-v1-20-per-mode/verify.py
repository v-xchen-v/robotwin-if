#!/usr/bin/env python3
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.release_press_lift_bell_v1 import verify
verify(Path(__file__).resolve().parent)
print("OK: six tasks, 20 blocks/task, 460 episodes; qualification and checksums verified")
