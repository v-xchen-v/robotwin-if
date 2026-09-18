"""Deployment checks that protect frozen results and unrelated remote processes."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import run_remote_attribute_suite as remote


class RemoteAttributeTests(unittest.TestCase):
    def test_task_selection_keeps_attribute_default_and_requires_supported_task(self):
        self.assertEqual(remote.task_name({}), 'attribute_select')
        self.assertEqual(remote.task_name({'task': 'arm_select'}), 'arm_select')
        with self.assertRaises(AssertionError):
            remote.task_name({'task': 'unknown'})

    def test_metadata_allows_device_change_but_rejects_inference_change(self):
        expected = dict(gpu='old', created_at='old', checkpoint={'revision': 'pinned'}, steps=10)
        remote.metadata_matches(expected, dict(expected, gpu='new', created_at='new'))
        with self.assertRaises(AssertionError):
            remote.metadata_matches(expected, dict(expected, steps=20))
        with self.assertRaises(AssertionError):
            remote.metadata_matches(expected, dict(expected, checkpoint={'revision': 'other'}))

    def test_download_timestamp_is_not_checkpoint_identity(self):
        expected = dict(checkpoint=dict(revision='pinned', weights_sha256='weights', downloaded_at='first'))
        actual = dict(checkpoint=dict(revision='pinned', weights_sha256='weights', downloaded_at='second'))
        remote.metadata_matches(expected, actual)
        actual['checkpoint']['weights_sha256'] = 'different-weights'
        with self.assertRaises(AssertionError):
            remote.metadata_matches(expected, actual)

    def test_only_selected_gpu_is_subject_to_idle_admission(self):
        rows = [dict(uuid='busy', temperature=40, used=40000, total=49000, utilization=99),
                dict(uuid='assigned', temperature=35, used=4, total=49000, utilization=0)]
        self.assertEqual(remote.selected_gpu(rows, 'assigned', idle=True)['uuid'], 'assigned')
        with self.assertRaises(AssertionError):
            remote.selected_gpu(rows, 'busy', idle=True)
        with self.assertRaises(AssertionError):
            remote.selected_gpu(rows, 'missing')

    def test_stop_does_not_signal_a_reused_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            remote.formal.write(base / 'support/vlact-service.json', dict(pid=123, start_ticks='old'))
            cfg = dict(remote=dict(base=tmp), lanes=[dict(model_gpu='assigned')])
            with patch.object(remote, 'gpu_rows', return_value=[dict(uuid='assigned', temperature=90)]), \
                 patch.object(remote.parallel, 'proc_identity', return_value=dict(start_ticks='new')), \
                 patch.object(remote.parallel, 'stop_process') as stop:
                self.assertTrue(remote.service(cfg, 'stop', 0, 'vlact', '')['stopped'])
                stop.assert_not_called()

    def test_overlapping_simulators_are_rejected(self):
        cfg = dict(remote=dict(local_host='test'), lanes=[dict(sim_gpu='same', model_gpu='a'),
                                                        dict(sim_gpu='same', model_gpu='b')])
        with patch.object(remote.formal, 'read', return_value=cfg), \
             patch.object(remote.socket, 'gethostname', return_value='test'):
            with self.assertRaises(AssertionError):
                remote.load_config(Path('unused'))

    def test_three_lanes_require_explicit_sharing_and_consistent_device(self):
        lanes = [dict(sim_gpu='first', sim_pci='a'), dict(sim_gpu='second', sim_pci='b'),
                 dict(sim_gpu='second', sim_pci='b')]
        remote.validate_lanes(dict(lanes=lanes, max_simulators_per_gpu=2))
        with self.assertRaises(AssertionError):
            remote.validate_lanes(dict(lanes=lanes))
        with self.assertRaises(AssertionError):
            remote.validate_lanes(dict(lanes=[lanes[1]] * 3, max_simulators_per_gpu=2))
        lanes[2]['sim_pci'] = 'wrong'
        with self.assertRaises(AssertionError):
            remote.validate_lanes(dict(lanes=lanes, max_simulators_per_gpu=2))

    def test_shared_model_gpu_counts_existing_memory(self):
        row = dict(uuid='shared', used=8051, utilization=10, temperature=45)
        cfg = dict(shared_model_gpus=['shared'])
        self.assertFalse(remote.model_admitted({}, 'lingbot_vla', [], row))
        self.assertTrue(remote.model_admitted(cfg, 'lingbot_vla', [], row))
        self.assertFalse(remote.model_admitted(cfg, 'lingbot_vla', [], dict(row, used=40000)))
        self.assertFalse(remote.model_admitted(cfg, 'lingbot_vla', [], dict(row, temperature=83)))
        self.assertFalse(remote.model_admitted(cfg, 'lingbot_vla', ['lingbot_vla'], row))
        self.assertFalse(remote.model_admitted(cfg, 'dm05', ['lingbot_vla', 'vlact'], row))
        self.assertFalse(remote.model_admitted(cfg, 'dm05', ['lingbot_va'], row))

    def test_model_gpu_follows_policy_across_simulator_lanes(self):
        cfg = dict(lanes=[dict(model_gpu='original')] * 3,
                   policy_model_gpus=dict(lingbot_vla='shared'))
        self.assertEqual(remote.model_gpu(cfg, 0, 'xvla'), 'original')
        self.assertEqual(remote.model_gpu(cfg, 2, 'lingbot_vla'), 'shared')

    def test_shared_simulator_admission_respects_heat_memory_and_lane_count(self):
        cfg = dict(lanes=[dict(sim_gpu='a'), dict(sim_gpu='b'),
                          dict(sim_gpu='b', admit_temperature_c=78)], max_simulators_per_gpu=2)
        row = dict(uuid='b', used=6000, total=49140, temperature=73, utilization=40)
        self.assertTrue(remote.simulator_admitted(cfg, 2, {1: {}}, [row]))
        self.assertFalse(remote.simulator_admitted(cfg, 2, {1: {}}, [dict(row, temperature=78)]))
        self.assertFalse(remote.simulator_admitted(cfg, 2, {1: {}}, [dict(row, used=16000)]))
        self.assertFalse(remote.simulator_admitted(cfg, 2, {1: {}, 2: {}}, [row]))
        with self.assertRaises(AssertionError):
            remote.simulator_admitted(cfg, 2, {}, [row])

    def test_cooling_keeps_actions_and_state_while_waiting(self):
        clock = [0.0]
        actions, waits = [], []

        def take_action(action, action_type):
            actions.append((action, action_type))
            clock[0] += 4

        env = SimpleNamespace(take_action=take_action)

        def episode(environment):
            environment.take_action('first', action_type='qpos')
            environment.take_action('second', action_type='ee')
            return 'finished'

        def sleep(seconds):
            waits.append((seconds, len(actions)))
            clock[0] += seconds

        rows = [[dict(uuid='gpu', temperature=t, used=6000, total=49140, utilization=50)]
                for t in (70, 81, 79, 74)]
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(remote, 'gpu_rows', side_effect=rows), \
             patch.object(remote.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(remote.time, 'sleep', side_effect=sleep):
            cooling = remote.ActionCooling('gpu', {}, Path(tmp) / 'pacing.json')
            self.assertEqual(remote.cooled_episode(env, episode, cooling), 'finished')
            self.assertEqual(actions, [('first', 'qpos'), ('second', 'ee')])
            self.assertEqual(waits, [(1, 1), (1, 1)])
            self.assertEqual(cooling.cooling_seconds, 2)
            self.assertIs(env.take_action, take_action)

    def test_cooling_restores_environment_method_on_error(self):
        env = SimpleNamespace(take_action=lambda action: action)
        original = env.take_action
        cooling = SimpleNamespace(before_action=lambda: None, record=lambda phase: None)

        def failed(environment):
            environment.take_action('unchanged')
            raise ValueError('episode error')

        with self.assertRaisesRegex(ValueError, 'episode error'):
            remote.cooled_episode(env, failed, cooling)
        self.assertIs(env.take_action, original)

    def test_action_cooling_does_not_relax_hard_temperature_limit(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(remote, 'gpu_rows', return_value=[
                 dict(uuid='gpu', temperature=86, used=6000, total=49140, utilization=50)]), \
             patch.object(remote.time, 'sleep') as sleep:
            cooling = remote.ActionCooling('gpu', {}, Path(tmp) / 'pacing.json')
            with self.assertRaises(AssertionError):
                cooling.before_action()
            sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
