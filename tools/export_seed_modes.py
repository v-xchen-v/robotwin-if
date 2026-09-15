#!/usr/bin/env python3
"""Export or check the six-task 20-block seed/mode JSON and CSV (CPU only)."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_modes import check_seed_modes, export_texts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-dir', type=Path,
                        default=ROOT / 'seed-manifests/if-ext-v2-six-tasks-spatial3-20-per-mode')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        check_seed_modes(args.manifest_dir)
    else:
        for name, contents in export_texts(args.manifest_dir).items():
            (args.manifest_dir / name).write_text(contents)
    print('OK: six tasks, 20 blocks/task, 460 exact seed/mode rows')


if __name__ == '__main__':
    main()
