"""Read frozen audit inputs from Git without publishing old releases in the checkout."""
from contextlib import contextmanager
import io
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# Last published tree containing the original, byte-identical release evidence.
REVISION = '2670a13f53f6e3f1cc2e6f0fdae558782cb88d7d'
ARCHIVES = {'seed-manifests-archive': 'seed-manifests', 'result-archive': 'result'}


@contextmanager
def historical_evidence(root=ROOT, revision=REVISION):
    """Materialize audit files outside the checkout; never fetch or change Git state.

    A shallow clone/source archive can run fresh evaluation without these files.
    Full historical provenance verification explicitly requires the pinned commit.
    """
    run = subprocess.run(['git', '-C', str(root), 'archive', '--format=tar', revision,
                          *ARCHIVES], capture_output=True)
    if run.returncode:
        raise RuntimeError(
            f'Full provenance verification requires Git commit {revision}. '
            f'Obtain it with `git fetch origin {revision}`. '
            'Fresh evaluation and tools/export_seed_modes.py --check do not need history. '
            + run.stderr.decode(errors='replace').strip())
    with tempfile.TemporaryDirectory(prefix='robotwin-release-audit-') as temporary:
        view = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(run.stdout), mode='r:') as archive:
            for member in archive:
                parts = PurePosixPath(member.name).parts
                if (not parts or parts[0] not in ARCHIVES or '..' in parts
                        or PurePosixPath(member.name).is_absolute()):
                    raise ValueError(f'Unexpected historical evidence path: {member.name}')
                target = view.joinpath(ARCHIVES[parts[0]], *parts[1:])
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.extractfile(member).read())
                else:
                    raise ValueError(f'Historical evidence must be regular files: {member.name}')
        yield view
