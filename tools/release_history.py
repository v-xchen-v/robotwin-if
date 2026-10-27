"""Read the Stapler suite's frozen five-task parent results from Git."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PARENT_RESULT = Path('result/robotwin-if-arm-only-v2-20blocks')
PARENT_RESULT_REVISION = 'ac582a75267126c7a8fe17c220475d517b73882b'


def read_parent_result(name, root=ROOT, revision=PARENT_RESULT_REVISION):
    """Read original reuse evidence from a pinned commit, without restoring old packages."""
    path = PARENT_RESULT / name
    run = subprocess.run(['git', '-C', str(root), 'show', f'{revision}:{path.as_posix()}'],
                         capture_output=True)
    if run.returncode:
        raise RuntimeError(
            f'Reusing or republishing frozen results requires Git commit {revision}. '
            f'Obtain it with `git fetch origin {revision}`. '
            'Fresh evaluation and current package checksum verification do not need history. '
            + run.stderr.decode(errors='replace').strip())
    return run.stdout
