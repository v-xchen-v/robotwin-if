"""Process ownership and parent-scene guards shared by remote schedulers."""
import subprocess
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from tools import remote_eval_support as support


class ProcessOwnershipTests(unittest.TestCase):
    def test_adoption_verifies_process_identity_without_interrupting_it(self):
        proc = subprocess.Popen(['sleep', '10'], start_new_session=True)
        self.addCleanup(lambda: support.formal.stop(proc))
        identity = support.proc_identity(proc.pid)
        with self.assertRaises(AssertionError):
            support.AdoptedProcess(proc.pid, 'wrong-start-time')
        adopted = support.AdoptedProcess(proc.pid, identity['start_ticks'])
        self.assertIsNone(adopted.poll())
        self.assertIsNone(proc.poll())
        proc.terminate()
        proc.wait(timeout=2)
        self.assertEqual(adopted.poll(), 0)

    def test_changed_pid_is_treated_as_exited(self):
        identity = dict(pid=123, start_ticks='original')
        with patch.object(support, 'proc_identity', return_value=identity), \
             patch.object(support.os, 'getpgid', return_value=123):
            process = support.AdoptedProcess(123, 'original')
        with patch.object(support, 'proc_identity', return_value=dict(pid=123, start_ticks='different')):
            self.assertEqual(process.poll(), 0)
            with patch.object(support.formal, 'stop') as stop:
                support.stop_process(process)
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
        support.formal.write(record, dict(instruction='pick blue', step_limit=400, success=True))
        support.formal.write(self.directory / (self.stem + '_provenance.json'),
                              dict(files_sha256={p.name: support.formal.digest(p) for p in (record, initial)}))
        support.formal.write(self.base / 'plan.json', dict(old_run=str(self.parent)))
        self.patch = patch('policies.xvla.client.encode_proprio', return_value=self.state)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def check(self):
        support.check_parent_scene(self.base, 'lingbot_va',
            dict(task='attribute_select', success_checker_version='target-only-lift-v2'), 100001,
            'pick blue', self.obs, SimpleNamespace(step_lim=400),
            lambda suffix: self.base / (self.stem + suffix))

    def test_parent_scene_is_available_without_new_xvla_verdict(self):
        self.check()
        evidence = support.formal.read(self.base / (self.stem + '_same_host_scene.json'))
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
        support.formal.write(record, dict(instruction='use right arm', step_limit=400))
        support.formal.write(directory / (stem + '_provenance.json'), dict(
            files_sha256={p.name: support.formal.digest(p) for p in (record, initial)}))
        args = (self.base, 'lingbot_va', dict(task='arm_select',
                success_checker_version='target-arm-only-lift-v2'), 500001,
                'use right arm', self.obs, SimpleNamespace(step_lim=400),
                lambda suffix: self.base / (stem + suffix))
        support.check_parent_scene(*args)
        evidence = support.formal.read(self.base / (stem + '_same_host_scene.json'))
        self.assertEqual(evidence['reference'], str(directory / stem))
        self.obs['observation']['head_camera']['rgb'][0, 0, 0] = 1
        with self.assertRaises(AssertionError):
            support.check_parent_scene(*args)

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
