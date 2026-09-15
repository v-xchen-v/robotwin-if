"""CPU regression checks for immutable result reuse and mid-block resumption."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from tools import sim_device
from unittest.mock import Mock, patch

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

    def test_changed_checker_excludes_old_success_and_failure_from_reuse(self):
        self.spec['success_checker_version'] = 'relative-lift-hold-v3'
        episodes = []
        for seed, success in ((100002, True), (100003, False), (100004, True)):
            source = self.episode(seed, success)
            if seed == 100004:
                path = source / 'bottle_verb_ep100004_result.json'
                record = suite.read(path)
                record['signals'] = {'checker_version': 'relative-lift-hold-v3'}
                suite.write(path, record)
            episodes.append(dict(policy='xvla', task='bottle_verb', seed=seed,
                                 source_directory=str(source)))
        accepted, excluded = suite.compatible_reuse([self.spec], episodes)
        self.assertEqual([r['seed'] for r in accepted], [100004])
        self.assertEqual([r['seed'] for r in excluded], [100002, 100003])
        self.assertTrue(all(r['reason'] == 'success_checker_changed' for r in excluded))

    def test_prior_metadata_accepts_direct_and_formal_archive_layouts(self):
        direct = self.base / 'xvla/bottle_verb'
        archived = self.base / 'provenance/reused/xvla/bottle_verb'
        with self.assertRaises(FileNotFoundError):
            suite.prior_metadata_directory(self.base, 'xvla', 'bottle_verb')
        for name in ('resolved_config.json', 'summary.json'):
            suite.write(archived / name, {})
        self.assertEqual(suite.prior_metadata_directory(self.base, 'xvla', 'bottle_verb'), archived)
        suite.write(direct / 'run.json', {})
        self.assertEqual(suite.prior_metadata_directory(self.base, 'xvla', 'bottle_verb'), archived)
        for name in ('resolved_config.json', 'summary.json'):
            suite.write(direct / name, {})
        self.assertEqual(suite.prior_metadata_directory(self.base, 'xvla', 'bottle_verb'), direct)

    def test_same_checker_version_with_changed_thresholds_is_not_reused(self):
        spec = dict(self.spec, success_checker_version='relative-lift-hold-v3',
                    success_checker_parameters={'hold_seconds': 1.0})
        record = dict(signals={'checker_version': 'relative-lift-hold-v3',
                               'thresholds': {'hold_seconds': 2.0}})
        self.assertFalse(suite.matches_success_checker(spec, record))
        record['signals']['thresholds']['hold_seconds'] = 1.0
        self.assertTrue(suite.matches_success_checker(spec, record))

    def test_current_three_second_contract_rejects_one_second_results(self):
        from dataclasses import asdict
        from tasks.envs._if_bottle_verb import PickHoldMonitor, PickHoldRules
        parameters = asdict(PickHoldRules())
        self.assertEqual(parameters['hold_seconds'], 3.0)
        self.assertNotIn('position_travel', parameters)
        self.assertEqual(parameters['rotation_travel_degrees'], 135.0)
        spec = dict(self.spec, success_checker_version=PickHoldMonitor.VERSION,
                    success_checker_parameters=parameters)
        old_parameters = dict(parameters, hold_seconds=1.0)
        for version in ('relative-lift-hold-v3', PickHoldMonitor.VERSION):
            for success in (True, False):
                record = dict(success=success, signals=dict(checker_version=version, thresholds=old_parameters))
                self.assertFalse(suite.matches_success_checker(spec, record))
        self.assertTrue(suite.matches_success_checker(spec, dict(signals=dict(
            checker_version=PickHoldMonitor.VERSION, thresholds=parameters))))
        for version in ('relative-lift-hold-v4', PickHoldMonitor.VERSION):
            old_budget = dict(parameters, position_travel=0.04, rotation_travel_degrees=45.0)
            self.assertFalse(suite.matches_success_checker(spec, dict(signals=dict(
                checker_version=version, thresholds=old_budget))))

    def test_terminal_contract_rejects_early_stop_v5_even_with_matching_thresholds(self):
        from dataclasses import asdict
        from tasks.envs._if_bottle_verb import PickHoldMonitor, PickHoldRules
        parameters=asdict(PickHoldRules())
        self.assertNotIn('position_radius',parameters)
        self.assertNotIn('reversal_distance',parameters)
        self.assertEqual(parameters['rotation_radius_degrees'],10)
        spec=dict(self.spec,success_checker_version=PickHoldMonitor.VERSION,
                  success_checker_parameters=parameters)
        for version in ('relative-lift-hold-v5',PickHoldMonitor.VERSION):
            old=dict(parameters,position_radius=.015,rotation_radius_degrees=15,
                     reversal_distance=.025,reversal_angle_degrees=20)
            self.assertFalse(suite.matches_success_checker(spec,dict(signals=dict(
                checker_version=version,thresholds=old))))
        self.assertFalse(suite.matches_success_checker(spec,dict(signals=dict(
            checker_version='relative-lift-hold-v5',thresholds=parameters))))

    def test_import_rejects_old_checker_before_copying_any_artifacts(self):
        self.spec['success_checker_version'] = 'relative-lift-hold-v3'
        source = self.episode(100002, True)
        with self.assertRaisesRegex(AssertionError, 'incompatible success checker'):
            suite.import_episode(self.base, 'xvla', self.spec, 100002, source, 'reused')
        self.assertFalse((self.base / 'xvla/bottle_verb').exists())

    def test_terminal_pick_requires_a_full_finalized_policy_rollout(self):
        from dataclasses import asdict
        from tasks.envs._if_bottle_verb import PickHoldMonitor, PickHoldRules
        parameters=asdict(PickHoldRules())
        spec=dict(self.spec,success_checker_version=PickHoldMonitor.VERSION,
                  success_checker_parameters=parameters)
        for success in (True,False):
            record=dict(mode='pick',success=success,action_calls=700,step_limit=700,
                signals=dict(checker_version=PickHoldMonitor.VERSION,thresholds=parameters,
                    pick_verdict_protocol='action-budget-end',pick_terminal_evaluation=True,
                    pick_verdict_finalized=True,pick_final_success=success,
                    policy_action_count=700,policy_action_limit=700))
            self.assertTrue(suite.matches_success_checker(spec,record))
            for key in ('pick_verdict_finalized','pick_terminal_evaluation'):
                signals=dict(record['signals'],**{key:False})
                self.assertFalse(suite.matches_success_checker(spec,dict(record,signals=signals)))
            self.assertFalse(suite.matches_success_checker(spec,dict(record,action_calls=106)))

    def test_legacy_run_validation_remains_readable_but_new_resume_rejects_old_checker(self):
        source = self.episode(100002, False)
        suite.import_episode(self.base, 'xvla', self.spec, 100002, source, 'reused')
        self.assertIsNotNone(suite.completed_record(self.base, 'xvla', self.spec, 100002))
        self.spec['success_checker_version'] = 'relative-lift-hold-v3'
        with self.assertRaisesRegex(AssertionError, 'incompatible success checker'):
            suite.completed_record(self.base, 'xvla', self.spec, 100002)

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
        fake = SimpleNamespace(__file__='fake_eval.py', run_episode=original,
                               setup_episode=lambda *args: ('instruction', {}))
        def main():
            for i, seed in enumerate(self.spec['seeds']):
                returned.append(fake.run_episode(None, None, None, None, seed, 'unseen', None, block=i // 2))
            return 0
        fake.main = main
        with patch.object(suite.importlib, 'import_module', return_value=fake), \
             patch.object(sim_device, 'pin_renderer', return_value='0000:af:00.0'), \
             patch.object(suite.sys, 'argv', []), patch.dict(suite.os.environ):
            self.assertEqual(suite.worker(self.base, 'xvla', 'bottle_verb', self.base / 'batch/bottle_verb'), 0)
        self.assertIs(fake.run_episode, original)
        self.assertEqual(executed, [(100003, 0), (100004, 1)])
        self.assertEqual([r['status'] for r in returned], ['failure', 'new', 'new', 'success'])
        resume = suite.read(self.base / 'batch/bottle_verb-resume.json')
        self.assertEqual(resume['skipped_seeds'], [100002, 100005])
        self.assertEqual(resume['argv'][resume['argv'].index('--blocks') + 1], '2')

    def test_twenty_blocks_reports_new_target_and_keeps_old_failures(self):
        self.spec['seeds'] = list(range(100002, 100042))
        self.spec['blocks'] = 20
        suite.write(self.base / 'plan.json', dict(tasks=[self.spec], policies=['xvla'], expected_episodes=40))
        for seed in self.spec['seeds'][:24]:
            source = self.episode(seed, False)
            suite.import_episode(self.base, 'xvla', self.spec, seed, source, 'reused')
        status = suite.report(self.base)
        self.assertEqual((status['completed_blocks'], status['expected_blocks']), (12, 20))
        self.assertEqual((status['completed_episodes'], status['pending_episodes']), (24, 16))
        self.assertEqual(status['policy_failures'], 24)
        row = suite.read(self.base / 'summary.json')['tasks'][0]
        self.assertEqual(row['per_mode']['pick']['expected'], 20)
        self.assertIn('completed 24/40', (self.base / 'report.md').read_text())
        self.assertIn('20 blocks', (self.base / 'report.md').read_text())
        self.spec['blocks'] = 12
        with self.assertRaisesRegex(AssertionError, 'disagrees'):
            suite.block_count(self.spec)

    def test_worker_checks_scene_before_inference_and_restores_hooks(self):
        policy = 'dm05'
        suite.write(self.base / f'provenance/reused/{policy}/bottle_verb/run.json',
                    dict(arguments=dict(server_url='http://127.0.0.1:8014', request_timeout=600)))
        setup = Mock(return_value=('instruction', {}))
        inference = Mock()
        def episode(env, config, client, args, seed, split, directory, block=None):
            fake.setup_episode(env, config, args, seed, split, {}, lambda suffix: directory / suffix)
            inference()
        fake = SimpleNamespace(__file__='fake_eval.py', run_episode=episode, setup_episode=setup)
        fake.main = lambda: fake.run_episode(None, {}, None, None, 100002, 'unseen', self.base)
        with patch.object(suite.importlib, 'import_module', return_value=fake), \
             patch.object(sim_device, 'pin_renderer'), patch.dict(suite.os.environ), \
             patch.object(suite, 'check_scene', side_effect=AssertionError('Initial RGB mismatch')) as guard:
            with self.assertRaisesRegex(AssertionError, 'Initial RGB mismatch'):
                suite.worker(self.base, policy, 'bottle_verb', self.base / 'batch/bottle_verb')
        guard.assert_called_once()
        setup.assert_called_once()
        inference.assert_not_called()
        self.assertIs(fake.run_episode, episode)
        self.assertIs(fake.setup_episode, setup)

    def test_gpu_pressure_or_other_jobs_prevent_execution(self):
        (self.base / 'support').mkdir()
        healthy = '0, 100, 49140, 40, 0\n1, 100, 49140, 40, 0\n'
        cases = ((healthy, True, True),
                 (healthy.replace('40, 0', '87, 0', 1), False, False),
                 (healthy.replace('100, 49140', '24576, 49140', 1), False, False),
                 (healthy.replace('1, 100', '1, 48000'), False, False),
                 (healthy.replace('40, 0', '40, 90', 1), True, False))
        for rows, idle, valid in cases:
            with self.subTest(rows=rows, idle=idle), \
                 patch.object(suite.subprocess, 'run', return_value=SimpleNamespace(stdout=rows)), \
                 patch.object(suite.shutil, 'disk_usage', return_value=SimpleNamespace(free=500 * 1024**3)):
                if valid:
                    suite.gpu_check(self.base, 'test', idle=idle)
                else:
                    with self.assertRaises(AssertionError):
                        suite.gpu_check(self.base, 'test', idle=idle)

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

    def test_scene_guard_rejects_rgb_or_state_changes_before_inference(self):
        import numpy as np
        from policies.xvla import client
        spec = dict(task='arm_select')
        pre = self.base / 'xvla/arm_select/arm_select_ep500000'
        pre.parent.mkdir(parents=True)
        cameras = ('head_camera', 'left_camera', 'right_camera')
        images = {c: np.zeros((2, 2, 3), dtype=np.uint8) for c in cameras}
        proprio = np.zeros(20)
        initial = Path(str(pre) + '_initial_observation.npz')
        np.savez(initial, **images, proprio=proprio)
        suite.write(str(pre) + '_provenance.json',
                          dict(files_sha256={initial.name: suite.digest(initial)}))
        obs = dict(observation={c: dict(rgb=im.copy()) for c, im in images.items()})
        record = dict(instruction='use left arm', step_limit=400)
        def path(suffix):
            return self.base / ('guard' + suffix)
        with patch.object(suite, 'completed_record', return_value=record), \
             patch.object(client, 'encode_proprio', return_value=proprio):
            def check():
                suite.check_scene(self.base, 'dm05', spec, 500000,
                                  'use left arm', obs, SimpleNamespace(step_lim=400), path)
            check()
            self.assertTrue(path('_same_host_scene.json').exists())
            obs['observation']['head_camera']['rgb'][0, 0, 0] = 1
            with self.assertRaises(AssertionError):
                check()
            obs['observation']['head_camera']['rgb'][0, 0, 0] = 0
            proprio[0] = .01
            with self.assertRaises(AssertionError):
                check()
            proprio[0] = 0
            for key, wrong in (('instruction', 'wrong instruction'), ('step_limit', 401)):
                with patch.dict(record, {key: wrong}), self.assertRaises(AssertionError):
                    check()
            initial.write_bytes(initial.read_bytes() + b'changed')
            with self.assertRaisesRegex(AssertionError, 'Reference checksum changed'):
                check()


if __name__ == '__main__':
    unittest.main()
