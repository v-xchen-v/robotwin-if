#!/usr/bin/env python3
"""Export or check a suite's seed/mode JSON and CSV (CPU only)."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_modes import build_seed_modes, check_seed_modes, export_texts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-dir', type=Path,
                        default=ROOT / 'seed-manifests/20-blocks')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        check_seed_modes(args.manifest_dir)
    else:
        for name, contents in export_texts(args.manifest_dir).items():
            (args.manifest_dir / name).write_text(contents)
    data = build_seed_modes(args.manifest_dir)
    print(f"OK: {data['task_count']} tasks, {data['blocks_per_task']} blocks/task, "
          f"{data['episodes_per_policy']} exact seed/mode rows")


if __name__ == '__main__':
    main()
