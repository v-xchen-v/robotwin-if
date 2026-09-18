"""Resource admission and live-process identity checks for two-policy execution."""
import subprocess
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from tools import run_parallel_attribute_suite as parallel


class ParallelAttributeTests(unittest.TestCase):
    def setUp(self):
        self.gpus = [[0, 6000, 49140, 78, 70], [1, 4100, 49140, 65, 20]]
        self.available = 30 * 1024**3

    def test_second_model_has_room_with_existing_xvla(self):
        self.assertTrue(parallel.admission('lingbot_va', ['xvla'], self.gpus, self.available))

    def test_never_admit_a_third_server_or_duplicate_policy(self):
        self.assertFalse(parallel.admission('vlact', ['xvla', 'lingbot_va'], self.gpus, self.available))
        self.assertFalse(parallel.admission('xvla', ['xvla'], self.gpus, self.available))

    def test_largest_models_do_not_share_reserved_memory(self):
        self.gpus[1][1] = 33854
        self.assertFalse(parallel.admission('dm05', ['lingbot_va'], self.gpus, self.available))
        self.assertTrue(parallel.admission('lingbot_vla', ['lingbot_va'], self.gpus, self.available))

    def test_real_pressure_can_override_expected_model_peak(self):
        self.gpus[1][1] = 44000
        self.assertFalse(parallel.admission('xvla', [], self.gpus, self.available))
        self.gpus[1][1] = 4100
        self.gpus[0][1] = parallel.SIM_ADMISSION_MIB
        self.assertFalse(parallel.admission('xvla', [], self.gpus, self.available))

    def test_temperature_and_host_memory_block_new_loads(self):
        self.gpus[0][3] = parallel.PAUSE_TEMPERATURE
        self.assertFalse(parallel.admission('lingbot_va', ['xvla'], self.gpus, self.available))
        self.gpus[0][3] = 78
        self.assertFalse(parallel.admission('lingbot_va', ['xvla'], self.gpus, 11 * 1024**3))

    def test_adoption_verifies_process_identity_without_interrupting_it(self):
        proc = subprocess.Popen(['sleep', '10'], start_new_session=True)
        self.addCleanup(lambda: parallel.formal.stop(proc))
        identity = parallel.proc_identity(proc.pid)
        with self.assertRaises(AssertionError):
            parallel.AdoptedProcess(proc.pid, 'wrong-start-time')
        adopted = parallel.AdoptedProcess(proc.pid, identity['start_ticks'])
        self.assertIsNone(adopted.poll())
        self.assertIsNone(proc.poll())
        proc.terminate()
        proc.wait(timeout=2)
        self.assertEqual(adopted.poll(), 0)

    def test_changed_pid_is_treated_as_exited(self):
        identity = dict(pid=123, start_ticks='original')
        with patch.object(parallel, 'proc_identity', return_value=identity), \
             patch.object(parallel.os, 'getpgid', return_value=123):
            process = parallel.AdoptedProcess(123, 'original')
        with patch.object(parallel, 'proc_identity', return_value=dict(pid=123, start_ticks='different')):
            self.assertEqual(process.poll(), 0)
            with patch.object(parallel.formal, 'stop') as stop:
                parallel.stop_process(process)
                stop.assert_not_called()


class ParentSceneTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name) / 'new'
        self.parent = Path(tmp.name) / 'old'
        self.directory = self.parent / 'xvla/attribute_select'
        self.directory.mkdir(parents=True)
        self.stem = 'attribute_select_ep100001'
        self.state = np.arange(20, dtype=float)
        cameras = ('head_camera', 'left_camera', 'right_camera')
        self.obs = dict(observation={name: dict(rgb=np.zeros((2, 3, 3), dtype=np.uint8)) for name in cameras})
        initial = self.directory / (self.stem + '_initial_observation.npz')
        np.savez(initial, proprio=self.state, **{name: self.obs['observation'][name]['rgb'] for name in cameras})
        record = self.directory / (self.stem + '_result.json')
        # Deliberately an old success without the new checker contract.
        parallel.formal.write(record, dict(instruction='pick blue', step_limit=400, success=True))
        parallel.formal.write(self.directory / (self.stem + '_provenance.json'),
                              dict(files_sha256={p.name: parallel.formal.digest(p) for p in (record, initial)}))
        parallel.formal.write(self.base / 'plan.json', dict(old_run=str(self.parent)))
        self.patch = patch('policies.xvla.client.encode_proprio', return_value=self.state)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def check(self):
        parallel.check_parent_scene(self.base, 'lingbot_va',
            dict(success_checker_version='target-only-lift-v2'), 100001,
            'pick blue', self.obs, SimpleNamespace(step_lim=400),
            lambda suffix: self.base / (self.stem + suffix))

    def test_parent_scene_is_available_without_new_xvla_verdict(self):
        self.check()
        evidence = parallel.formal.read(self.base / (self.stem + '_same_host_scene.json'))
        self.assertFalse(evidence['reference_verdict_reused'])
        self.assertTrue(evidence['exact_rgb'])
        self.assertEqual(evidence['reference_policy'], 'xvla')
        self.assertFalse((self.base / 'xvla').exists())

    def test_arm_scene_uses_arm_parent_and_keeps_rgb_guard(self):
        directory = self.parent / 'xvla/arm_select'
        directory.mkdir()
        stem = 'arm_select_ep500001'
        initial = directory / (stem + '_initial_observation.npz')
        np.savez(initial, proprio=self.state, **{
            name: self.obs['observation'][name]['rgb'] for name in self.obs['observation']})
        record = directory / (stem + '_result.json')
        parallel.formal.write(record, dict(instruction='use right arm', step_limit=400))
        parallel.formal.write(directory / (stem + '_provenance.json'), dict(
            files_sha256={p.name: parallel.formal.digest(p) for p in (record, initial)}))
        args = (self.base, 'lingbot_va', dict(task='arm_select',
                success_checker_version='target-arm-only-lift-v2'), 500001,
                'use right arm', self.obs, SimpleNamespace(step_lim=400),
                lambda suffix: self.base / (stem + suffix))
        parallel.check_parent_scene(*args)
        evidence = parallel.formal.read(self.base / (stem + '_same_host_scene.json'))
        self.assertEqual(evidence['reference'], str(directory / stem))
        self.obs['observation']['head_camera']['rgb'][0, 0, 0] = 1
        with self.assertRaises(AssertionError):
            parallel.check_parent_scene(*args)

    def test_policy_specific_sixteen_dimensional_npz_is_not_the_scene_reference(self):
        policy_directory = self.parent / 'lingbot_va/attribute_select'
        policy_directory.mkdir(parents=True)
        np.savez(policy_directory / (self.stem + '_initial_observation.npz'), proprio=np.zeros(16))
        self.check()

    def test_changed_initial_scene_is_rejected_before_inference(self):
        self.obs['observation']['head_camera']['rgb'][0, 0, 0] = 1
        with self.assertRaises(AssertionError):
            self.check()

    def test_changed_parent_record_is_rejected(self):
        (self.directory / (self.stem + '_result.json')).write_text('{}')
        with self.assertRaises(AssertionError):
            self.check()


if __name__ == '__main__':
    unittest.main()
