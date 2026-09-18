"""Current-only delivery and strict, temporary recovery of frozen audit evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import release_arm_select_target_only_v2 as release
from tools.release_history import historical_evidence
from if_benchmark.seed_modes import check_seed_modes

ROOT = Path(__file__).resolve().parents[1]


class CurrentReleaseTest(unittest.TestCase):
    def test_only_latest_packages_are_exposed(self):
        for parent, name in [('seed-manifests', 'robotwin-if-arm-only-v2-20-per-mode'),
                             ('result', 'robotwin-if-arm-only-v2-20blocks')]:
            entries = list((ROOT / parent).iterdir())
            self.assertEqual([p.name for p in entries if p.is_dir()], [name])
            self.assertFalse(any(p.is_symlink() for p in entries))
            self.assertFalse((ROOT / (parent + '-archive')).exists())
        check_seed_modes(release.RELEASE)

    def test_current_files_and_checker_evidence_match_checksums(self):
        directories = [release.RELEASE, ROOT / 'result/robotwin-if-arm-only-v2-20blocks']
        directories += list((directories[1] / 'evidence').iterdir())
        for directory in directories:
            if not directory.is_dir():
                continue
            for line in (directory / 'SHA256SUMS').read_text().splitlines():
                expected, name = line.split(maxsplit=1)
                with self.subTest(directory=directory, name=name):
                    self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), expected)


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


class HistoricalEvidenceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.git('init', '-q')
        for parent in ('seed-manifests-archive', 'result-archive'):
            path = self.root / parent / 'old' / 'evidence.bin'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'original evidence\x00\r\n')
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'frozen')
        self.revision = self.git('rev-parse', 'HEAD').stdout.strip()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, text=True)

    def test_pinned_bytes_original_paths_cleanup_and_no_checkout_mutation(self):
        # A later uncommitted change must not be treated as published evidence.
        (self.root / 'result-archive/old/evidence.bin').write_bytes(b'changed')
        before = self.git('status', '--porcelain').stdout
        with historical_evidence(self.root, self.revision) as view:
            for parent in ('seed-manifests', 'result'):
                self.assertEqual((view / parent / 'old/evidence.bin').read_bytes(), b'original evidence\x00\r\n')
            self.assertFalse(view.is_relative_to(self.root))
        self.assertFalse(view.exists())
        self.assertEqual(self.git('status', '--porcelain').stdout, before)

    def test_failed_verification_propagates_and_temporary_evidence_is_removed(self):
        with self.assertRaisesRegex(AssertionError, 'verification failed'):
            with historical_evidence(self.root, self.revision) as view:
                raise AssertionError('verification failed')
        self.assertFalse(view.exists())

    def test_missing_history_fails_explicitly_without_fetching_or_using_current_files(self):
        with self.assertRaisesRegex(RuntimeError, 'git fetch origin'):
            with historical_evidence(self.root, '0' * 40):
                self.fail('Missing history must not pass verification')

    def test_git_archive_symlinks_are_rejected(self):
        (self.root / 'result-archive/unsafe').symlink_to('/tmp')
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'symlink')
        with self.assertRaisesRegex(ValueError, 'regular files'):
            with historical_evidence(self.root, self.git('rev-parse', 'HEAD').stdout.strip()):
                self.fail('A symlink must not be extracted')


if __name__ == '__main__':
    unittest.main()
