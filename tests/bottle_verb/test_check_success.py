#!/usr/bin/env python3
"""Run the current Bottle-Verb trajectory and task-wiring regression tests (CPU only)."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
if __name__=='__main__':
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_bottle_verb_success.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
