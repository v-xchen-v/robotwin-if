#!/usr/bin/env python3
"""Run a frozen historical verifier in its original directory layout (CPU only)."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    archive = ROOT / 'seed-manifests-archive'
    releases = sorted(p.name for p in archive.iterdir() if (p / 'verify.py').is_file())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', choices=releases)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='robotwin-seed-release-verify-') as temporary:
        view = Path(temporary)
        # Materialize the small manifests, following the compatibility links.
        # A real verify.py makes Path(__file__).resolve() retain the old layout;
        # even verifier source files can therefore keep their published hashes.
        shutil.copytree(ROOT / 'seed-manifests', view / 'seed-manifests')
        for name in ('if_benchmark', 'tools', 'result', 'tasks', 'policies', 'bak', 'third_party'):
            (view / name).symlink_to(ROOT / name, target_is_directory=True)
        verifier = view / 'seed-manifests' / args.release / 'verify.py'
        return subprocess.run([sys.executable, str(verifier)], cwd=view).returncode


if __name__ == '__main__':
    sys.exit(main())
