#!/usr/bin/env python3
"""Prepare the six-policy stapler release, retaining the five existing task results."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prepare_bell_policy_suite import OLD, PACKAGE, prepare as prepare_replacement
from tools.release_press_lift_stapler_v1 import RELEASE, verify

RUN = Path('/Data/robotwin-if/evaluations/robotwin-if-press-lift-stapler-v1-20blocks-001')


def prepare(base=RUN, old=OLD):
    return prepare_replacement(base, old, release=RELEASE, task_name='press_lift_stapler', verify_release_fn=verify)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, default=RUN)
    parser.add_argument('--old-run', type=Path, default=OLD)
    args = parser.parse_args()
    prepare(args.run_dir.resolve(), args.old_run.resolve())
