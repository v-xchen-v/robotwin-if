#!/usr/bin/env python3
"""Publish the completed randomized stapler suite alongside its five reused tasks."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prepare_stapler_policy_suite import RUN
from tools.publish_bell_policy_results import publish as publish_replacement

OUTPUT = ROOT / 'result/robotwin-if-press-lift-stapler-v1-20blocks'


def publish(base=RUN, output=OUTPUT):
    return publish_replacement(base, output, task_name='press_lift_stapler', task_label='Press/Lift Stapler')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, default=RUN)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    publish(args.run_dir.resolve(), args.output.resolve())
