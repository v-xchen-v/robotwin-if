"""CPU regression checks for immutable result reuse and mid-block resumption."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'tools/run_formal_policy_suite.py'
SPEC = importlib.util.spec_from_file_location('formal_suite', PATH)
suite = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(suite)


class FormalReuseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.spec = dict(task='bottle_verb', task_config='demo_clean',
                         seeds=[100002, 100003, 100004, 100005], manifest='bottle_verb.json')
        suite.write(self.base / 'plan.json', dict(tasks=[self.spec]))
        suite.write(self.base / 'provenance/reused/xvla/bottle_verb/run.json',
                    dict(arguments=dict(server_url='http://127.0.0.1:8010', request_timeout=600)))

    def episode(self, seed, success):
        directory = self.base / 'source'
        directory.mkdir(exist_ok=True)
        pre = directory / suite.prefix('bottle_verb', seed)
        record = dict(task='bottle_verb', seed=seed, success=success, status='success' if success else 'failure',
                      oracle_success=True, instruction_type='unseen', instruction='Test instruction',
                      action_calls=2, step_limit=2, mode='shake' if seed % 2 else 'pick')
        suite.write(str(pre) + '_result.json', record)
        suite.write(str(pre) + '_summary.json', dict(config='demo_clean', execution_runtime_error=None,
                    success=success, instruction_type='unseen', instruction=record['instruction'], steps=2))
        suite.write(str(pre) + '_status.json', dict(status='policy_' + record['status']))
        for suffix in ('_oracle.json', '_initial_observation.npz', '_actions.npz', '_timings.json',
                       '_diagnostics.json', '_action_logs.json', f'_{int(success)}.mp4'):
            Path(str(pre) + suffix).write_bytes(b'fixture')
        return directory

    def test_checksum_failure_does_not_commit(self):
        source = self.episode(100002, False)
        with self.assertRaises(AssertionError):
            suite.import_episode(self.base, 'xvla', self.spec, 100002, source, 'reused',
                                 {'bottle_verb_ep100002_result.json': 'wrong'})
        self.assertIsNone(suite.completed_record(self.base, 'xvla', self.spec, 100002))

    def test_failure_is_immutable_and_copy_uses_exact_prefix(self):
        source = self.episode(100002, False)
        (source / 'bottle_verb_ep1000020_summary.json').write_text('unrelated')
        self.assertTrue(suite.import_episode(self.base, 'xvla', self.spec, 100002, source, 'reused'))
        self.assertFalse(suite.import_episode(self.base, 'xvla', self.spec, 100002, source, 'new'))
        self.assertFalse((self.base / 'xvla/bottle_verb/bottle_verb_ep1000020_summary.json').exists())
        record = suite.completed_record(self.base, 'xvla', self.spec, 100002)
        self.assertEqual(record['status'], 'failure')
        path = self.base / 'xvla/bottle_verb/bottle_verb_ep100002_result.json'
        path.write_text(path.read_text() + ' ')
        with self.assertRaises(AssertionError):
            suite.completed_record(self.base, 'xvla', self.spec, 100002)

    def test_resume_skips_success_and_failure_inside_complete_manifest(self):
        # A gap inside block 0 and a retained success inside block 1.
        for seed, success in ((100002, False), (100005, True)):
            source = self.episode(seed, success)
            suite.import_episode(self.base, 'xvla', self.spec, seed, source, 'reused')
        executed, returned = [], []
        def original(env, config, client, args, seed, split, directory, block=None):
            executed.append((seed, block))
            return dict(seed=seed, status='new')
        fake = SimpleNamespace(__file__='fake_eval.py', run_episode=original)
        def main():
            for i, seed in enumerate(self.spec['seeds']):
                returned.append(fake.run_episode(None, None, None, None, seed, 'unseen', None, block=i // 2))
            return 0
        fake.main = main
        loader = SimpleNamespace(create_module=lambda spec: None, exec_module=lambda module: setattr(module, 'pin_renderer',
                                 lambda: SimpleNamespace(pci_string='0000:af:00.0')))
        adapter = importlib.util.spec_from_loader('fake_adapter', loader)
        with patch.object(suite.importlib, 'import_module', return_value=fake), \
             patch.object(suite.importlib.util, 'spec_from_file_location', return_value=adapter), \
             patch.object(suite.sys, 'argv', []), patch.dict(suite.os.environ):
            self.assertEqual(suite.worker(self.base, 'xvla', 'bottle_verb', self.base / 'batch/bottle_verb'), 0)
        self.assertEqual(executed, [(100003, 0), (100004, 1)])
        self.assertEqual([r['status'] for r in returned], ['failure', 'new', 'new', 'success'])
        resume = suite.read(self.base / 'batch/bottle_verb-resume.json')
        self.assertEqual(resume['skipped_seeds'], [100002, 100005])

    def oracle_error(self):
        return dict(task='bottle_verb', seed=100002, status='error', oracle_success=False,
                    action_calls=0, chunks=0, instruction=None,
                    error=dict(stage='episode_setup', type='RuntimeError',
                               message='Exact seed failed oracle qualification; no seed substitution'))

    def test_retry_only_pre_inference_oracle_negative(self):
        error = self.oracle_error()
        self.assertTrue(suite.is_oracle_setup_failure(error))
        for fields in (dict(status='failure'), dict(action_calls=1), dict(chunks=1),
                       dict(instruction='Policy has started'), dict(close_error='CUDA error'),
                       dict(error=dict(stage='episode_setup', type='RuntimeError', message='CUDA timeout')),
                       dict(error=dict(stage='inference', type='RuntimeError', message='HTTP timeout'))):
            with self.subTest(fields=fields):
                self.assertFalse(suite.is_oracle_setup_failure(dict(error, **fields)))

    def test_crash_or_incomplete_record_never_retries(self):
        output = self.base / 'batch'
        output.mkdir()
        path = output / 'results.jsonl'
        path.write_text(json.dumps(self.oracle_error()) + '\n')
        summary = dict(complete=False, error=None)
        self.assertEqual(suite.retryable_batch_failure(output, 2, summary), 100002)
        self.assertIsNone(suite.retryable_batch_failure(output, -9, summary))
        self.assertIsNone(suite.retryable_batch_failure(output, 2, dict(summary, error='driver timeout')))
        path.write_text(json.dumps(self.oracle_error()))
        self.assertIsNone(suite.retryable_batch_failure(output, 2, summary))

    def test_oracle_retry_budget_survives_restart(self):
        for attempt in range(3):
            path = self.base / 'batches' / str(attempt) / 'xvla/bottle_verb/bottle_verb_ep100002_result.json'
            suite.write(path, self.oracle_error())
            if attempt < 2:
                suite.check_oracle_budget(self.base, 'xvla', self.spec)
        for _ in range(2):
            with self.assertRaisesRegex(AssertionError, 'Oracle failed 3 times'):
                suite.check_oracle_budget(self.base, 'xvla', self.spec)
        # An already committed policy failure is complete and never retried.
        source = self.episode(100002, False)
        suite.import_episode(self.base, 'xvla', self.spec, 100002, source, 'new')
        suite.check_oracle_budget(self.base, 'xvla', self.spec)

    def test_only_whole_blocks_count_and_policy_failures_count(self):
        suite.write(self.base / 'plan.json', dict(tasks=[self.spec], policies=['xvla'], expected_episodes=4))
        for seed in (100002, 100004):
            source = self.episode(seed, False)
            suite.import_episode(self.base, 'xvla', self.spec, seed, source, 'new')
        status = suite.report(self.base)
        self.assertEqual(status['completed_episodes'], 2)
        self.assertEqual(status['completed_blocks'], 0)
        source = self.episode(100003, False)
        suite.import_episode(self.base, 'xvla', self.spec, 100003, source, 'new')
        status = suite.report(self.base)
        self.assertEqual(status['completed_blocks'], 1)
        self.assertEqual(status['policy_failures'], 3)
        self.assertEqual(status['complete_task_policy_runs'], 0)


if __name__ == '__main__':
    unittest.main()
