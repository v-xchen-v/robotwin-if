"""Current delivery and pinned Git evidence for the five reused tasks."""
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.release_history import PARENT_RESULT, read_parent_result
from tools.release_press_lift_stapler_v1 import RELEASE
from if_benchmark.seed_modes import check_seed_modes

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'result/robotwin-if-press-lift-stapler-v1-20blocks'


class CurrentReleaseTest(unittest.TestCase):
    def test_only_latest_manifest_is_exposed(self):
        entries = list((ROOT / 'seed-manifests').iterdir())
        self.assertEqual([p.name for p in entries if p.is_dir()], [RELEASE.name])
        self.assertFalse(any(p.is_symlink() for p in entries))
        self.assertFalse((ROOT / 'seed-manifests-archive').exists())
        self.assertFalse((ROOT / 'bak/robotwin-if-press-lift-bell-v1-20-per-mode').exists())
        check_seed_modes(RELEASE)

    def test_only_latest_result_is_exposed(self):
        entries = list((ROOT / 'result').iterdir())
        self.assertEqual([p.name for p in entries if p.is_dir()], [RESULT.name])
        self.assertFalse(any(p.is_symlink() for p in entries))

    def test_current_files_and_checker_evidence_match_checksums(self):
        directories = [RELEASE, RESULT]
        for directory in directories:
            self.assertTrue(directory.is_dir())
            for line in (directory / 'SHA256SUMS').read_text().splitlines():
                expected, name = line.split(maxsplit=1)
                with self.subTest(directory=directory, name=name):
                    self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), expected)

    def test_five_task_reuse_and_checkpoint_identity_survive_parent_cleanup(self):
        parent_csv = read_parent_result('episodes.csv')
        provenance = json.loads((RESULT / 'provenance.json').read_text())
        self.assertEqual(hashlib.sha256(parent_csv).hexdigest(), provenance['parent_episode_csv_sha256'])
        key = lambda row: (row['policy'], row['task'], row['seed'])
        parent = {key(row): row for row in csv.DictReader(io.StringIO(parent_csv.decode()))}
        with (RESULT / 'episodes.csv').open(newline='') as stream:
            reused = [row for row in csv.DictReader(stream) if row['origin'] == 'reused']
        self.assertEqual(len(reused), 2520)
        for row in reused:
            self.assertEqual({k: v for k, v in row.items() if k != 'origin'},
                             {k: v for k, v in parent[key(row)].items() if k != 'origin'})
        checkpoints = json.loads((RESULT / 'checkpoints.json').read_text())
        for policy, original in json.loads(read_parent_result('checkpoints.json')).items():
            self.assertEqual({k: v for k, v in checkpoints[policy].items() if not k.startswith('evidence')},
                             {k: v for k, v in original.items() if not k.startswith('evidence')})


class HistoricalEvidenceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.git('init', '-q')
        parent_result = self.root / PARENT_RESULT / 'episodes.csv'
        parent_result.parent.mkdir(parents=True)
        parent_result.write_bytes(b'policy,success\r\nxvla,0\r\n')
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'frozen')
        self.revision = self.git('rev-parse', 'HEAD').stdout.strip()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, text=True)

    def test_parent_result_reads_pinned_bytes_after_local_change_or_deletion(self):
        path = self.root / PARENT_RESULT / 'episodes.csv'
        for delete in (False, True):
            if delete:
                path.unlink()
            else:
                path.write_bytes(b'changed locally')
            before = self.git('status', '--porcelain').stdout
            self.assertEqual(read_parent_result('episodes.csv', self.root, self.revision),
                             b'policy,success\r\nxvla,0\r\n')
            self.assertEqual(self.git('status', '--porcelain').stdout, before)
        self.assertFalse(path.exists())

    def test_missing_parent_history_fails_without_falling_back_to_local_result(self):
        with self.assertRaisesRegex(RuntimeError, 'git fetch origin'):
            read_parent_result('episodes.csv', self.root, '0' * 40)


if __name__ == '__main__':
    unittest.main()
