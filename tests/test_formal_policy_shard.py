"""CPU checks for host ownership, GPU isolation and relocation."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import run_formal_policy_shard as shard


class ShardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        (self.base / 'support').mkdir()
        self.cfg = dict(host='host-a', repo_root=str(shard.ROOT),
                        policies=shard.suite.POLICIES.copy(), tasks=['grasp_cube_approach'],
                        assignments={'host-a': ['grasp_cube_approach'],
                                     'host-b': ['bottle_verb', 'pick_diverse_object', 'attribute_select',
                                                'arm_select', 'stack_sequence', 'place_relative']},
                        sim_gpu=dict(index=0, uuid='GPU-sim', pci='0000:31:00.0'),
                        model_gpu=dict(index=1, uuid='GPU-model', pci='0000:4b:00.0'))

    def load(self):
        path = self.base / 'config.json'
        path.write_text(json.dumps(self.cfg))
        with patch.object(shard.socket, 'gethostname', return_value='host-a'):
            return shard.load_config(path)

    def test_assignments_cover_each_task_once(self):
        self.assertEqual(self.load()['tasks'], ['grasp_cube_approach'])
        self.cfg['assignments']['host-b'].append('grasp_cube_approach')
        with self.assertRaises(AssertionError):
            self.load()

    def test_missing_task_or_policy_rejected(self):
        self.cfg['assignments']['host-b'].remove('arm_select')
        with self.assertRaises(AssertionError):
            self.load()
        self.cfg['assignments']['host-b'].append('arm_select')
        self.cfg['policies'] = ['xvla']
        with self.assertRaises(AssertionError):
            self.load()

    def test_gpu_roles_cannot_overlap(self):
        self.cfg['model_gpu']['uuid'] = 'GPU-sim'
        with self.assertRaises(AssertionError):
            self.load()

    def check_gpu(self, rows):
        with patch.object(shard.subprocess, 'run', return_value=SimpleNamespace(stdout=rows)), \
             patch('shutil.disk_usage', return_value=SimpleNamespace(free=500 * 1024**3)):
            shard.gpu_check(self.base, self.cfg, 'test', idle=True)

    def test_monitor_only_assigned_gpus_on_four_gpu_host(self):
        rows = ('0, GPU-sim, 00000000:31:00.0, 4, 49140, 40, 0\n'
                '1, GPU-model, 00000000:4B:00.0, 4, 49140, 40, 0\n'
                '2, GPU-other, 00000000:B1:00.0, 49000, 49140, 89, 99\n')
        self.check_gpu(rows)
        with self.assertRaises(AssertionError):
            self.check_gpu(rows.replace('4, 49140, 40, 0', '5000, 49140, 40, 20', 1))
        with self.assertRaises(AssertionError):
            self.check_gpu(rows.replace('00000000:31:00.0', '00000000:32:00.0'))

    def test_relocation_preserves_inference_options(self):
        original = dict(argv=['/old/repo/policies/model/serve.py', '--no-offload',
                              '--checkpoint-dir', '/old/checkpoints/model'], steps=10)
        changed = shard.relocate(original, {'/old': '/new', '/old/repo': '/new/source'})
        self.assertEqual(changed, dict(argv=['/new/source/policies/model/serve.py', '--no-offload',
                                             '--checkpoint-dir', '/new/checkpoints/model'], steps=10))
        self.assertEqual(original['argv'][0], '/old/repo/policies/model/serve.py')

    def test_relocation_does_not_rewrite_its_own_destination(self):
        mapping = {'/home/user/repo': '/Data/robotwin-if-xichen/repo',
                   '/Data/robotwin-if': '/Data/robotwin-if-xichen'}
        self.assertEqual(shard.relocate('/home/user/repo/policies/model/serve.py', mapping),
                         '/Data/robotwin-if-xichen/repo/policies/model/serve.py')

    def test_scene_guard_rejects_rgb_or_state_changes_before_inference(self):
        import numpy as np
        from policies.xvla import client
        spec = dict(task='grasp_cube_approach')
        pre = self.base / 'xvla/grasp_cube_approach/grasp_cube_approach_ep500000'
        pre.parent.mkdir(parents=True)
        cameras = ('head_camera', 'left_camera', 'right_camera')
        images = {c: np.zeros((2, 2, 3), dtype=np.uint8) for c in cameras}
        proprio = np.zeros(20)
        initial = Path(str(pre) + '_initial_observation.npz')
        np.savez(initial, **images, proprio=proprio)
        shard.suite.write(str(pre) + '_provenance.json',
                          dict(files_sha256={initial.name: shard.suite.digest(initial)}))
        obs = dict(observation={c: dict(rgb=im.copy()) for c, im in images.items()})
        record = dict(instruction='from the top', step_limit=400)
        path = lambda suffix: self.base / ('guard' + suffix)
        with patch.object(shard.suite, 'completed_record', return_value=record), \
             patch.object(client, 'encode_proprio', return_value=proprio):
            def check():
                shard.check_scene(self.base, self.cfg, 'dm05', spec, 500000,
                                  'from the top', obs, SimpleNamespace(step_lim=400), path)
            check()
            self.assertTrue(path('_same_host_scene.json').exists())
            obs['observation']['head_camera']['rgb'][0, 0, 0] = 1
            with self.assertRaises(AssertionError):
                check()
            obs['observation']['head_camera']['rgb'][0, 0, 0] = 0
            proprio[0] = .01
            with self.assertRaises(AssertionError):
                check()


if __name__ == '__main__':
    unittest.main()
