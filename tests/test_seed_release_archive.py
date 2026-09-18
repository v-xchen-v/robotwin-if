"""Keep historical release evidence readable while moving the current entry."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import release_arm_select_target_only_v2 as release
from tools import verify_archived_seed_release as archived


ROOT = Path(__file__).resolve().parents[1]


class ArchiveEvidenceTest(unittest.TestCase):
    def test_legacy_paths_resolve_to_byte_identical_archived_files(self):
        archive = ROOT / 'seed-manifests-archive'
        names = set()
        for line in (archive / 'SHA256SUMS').read_text().splitlines():
            expected, name = line.split('  ', 1)
            names.add(Path(name).parts[0])
            original = ROOT / 'seed-manifests' / name
            target = archive / name
            self.assertEqual(original.resolve(), target)
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), expected)
        self.assertEqual(len(names), 12)
        for name in names:
            self.assertTrue((ROOT / 'seed-manifests' / name).is_symlink())
        current = [p.name for p in (ROOT / 'seed-manifests').iterdir()
                   if p.is_dir() and not p.is_symlink()]
        self.assertEqual(current, ['robotwin-if-arm-only-v2-20-per-mode'])

    def test_published_qualification_paths_and_hashes_still_match(self):
        for base in (ROOT / 'seed-manifests', ROOT / 'seed-manifests-archive'):
            for evidence in base.glob('*/qualification-files.json'):
                for name, expected in json.loads(evidence.read_text()).items():
                    with self.subTest(evidence=evidence, source=name):
                        self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)


class FrozenAuditTest(unittest.TestCase):
    OLD = "parser.add_argument('--release', type=Path, default=ROOT / 'seed-manifests/robotwin-if-attribute-v2-20-per-mode')"
    NEW = OLD.replace('robotwin-if-attribute-v2', 'robotwin-if-arm-only-v2')
    RUNNER = 'tools/run_formal_policy_suite.py'

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / self.RUNNER
        self.path.parent.mkdir()
        self.original = (self.OLD + '\nrun_policy()\n').encode()
        self.updated = (self.NEW + '\nrun_policy()\n').encode()
        self.recorded = dict(source_difference_sha256={
            self.RUNNER: hashlib.sha256(self.original).hexdigest(), 'task.py': 'frozen-task'},
            unchanged_five_task_sources=True)

    def check(self, source, task_digest='frozen-task'):
        self.path.write_bytes(source)
        observed = deepcopy(self.recorded)
        observed['source_difference_sha256'].update({
            self.RUNNER: hashlib.sha256(source).hexdigest(), 'task.py': task_digest})
        with patch.object(release, 'ROOT', self.root), \
             patch.object(release, 'source_audit', return_value=observed):
            release.verify_source_audit(Path('/unused'), self.recorded)

    def test_original_and_only_default_change_preserve_frozen_audit(self):
        self.check(self.original)
        self.check(self.updated)
        self.assertEqual(self.recorded['source_difference_sha256'][self.RUNNER],
                         hashlib.sha256(self.original).hexdigest())

    def test_policy_execution_change_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, 'runner changed'):
            self.check(self.updated.replace(b'run_policy()', b'run_other_policy()'))

    def test_task_change_is_rejected_even_when_only_runner_default_changed(self):
        with self.assertRaisesRegex(AssertionError, 'Source reuse audit changed'):
            self.check(self.updated, task_digest='modified-task')


class LegacyVerifierTest(unittest.TestCase):
    def test_original_layout_is_restored_without_changing_source_or_hiding_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / 'seed-manifests-archive' / 'old'
            original.mkdir(parents=True)
            (root / 'seed-manifests').mkdir()
            (root / 'seed-manifests' / 'old').symlink_to(original, target_is_directory=True)
            source = ('from pathlib import Path\n'
                      'base = Path(__file__).resolve().parent\n'
                      "assert base.parent.name == 'seed-manifests'\n"
                      "raise SystemExit(int((base / 'exit-code').read_text()))\n")
            (original / 'verify.py').write_text(source)
            with patch.object(archived, 'ROOT', root), \
                 patch('sys.argv', ['verify_archived_seed_release.py', 'old']):
                for code in (0, 7):
                    (original / 'exit-code').write_text(str(code))
                    self.assertEqual(archived.main(), code)
                    self.assertEqual((original / 'verify.py').read_text(), source)


if __name__ == '__main__':
    unittest.main()
