"""Policy setup must support every IF mode without executing the oracle."""

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_contracts import IF_SEED_CONTRACTS, observed_mode
from if_benchmark.seed_manifest import load_manifest
from tools.generate_if_seed_manifest import _observed_mode
from tasks.envs._if_grounding import AttributePickMonitor


class BaseTask:
    def _init_task_env_(self, seed, **kwargs):
        self.scene = SimpleNamespace(step=lambda: None)
        self.position = np.array([0., 0., 0.8])
        self.other_position = np.array([0.2, 0., 0.8])
        self.cube = self.target = SimpleNamespace(get_pose=lambda: SimpleNamespace(p=self.position))
        self.distractor = SimpleNamespace(get_pose=lambda: SimpleNamespace(p=self.other_position))
        self._init_z = {}
        self._init_cube_z = None
        self._approach_axis_z = 0.
        self.mode = ('top', 'side')[seed % 2]
        self.axis, self.value = 'color', seed % 2
        self.contact = False
        self.rotation = [1., 0., 0., 0.]

    def get_arm_pose(self, arm):
        xyz = self.position + ([0., 0., 0.02] if arm == 'right' else [-1., 0., 0.])
        return list(xyz) + list(self.rotation)

    def get_gripper_actor_contact_position(self, name):
        return [self.position] if self.contact else []


def task_class(name):
    path = ROOT / 'tasks/envs' / f'{name}.py'
    tree = ast.parse(path.read_text())
    tree.body = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    namespace = dict(Base_Task=BaseTask, np=np, ArmTag=str, AttributePickMonitor=AttributePickMonitor,
                     apply_if_eval_step_limit=lambda task: None)
    exec(compile(tree, str(path), 'exec'), namespace)
    return namespace[name]


class PolicyEvaluationTests(unittest.TestCase):
    def test_runtime_modes_agree_with_qualification(self):
        scenes = {
            'bottle_verb': SimpleNamespace(mode='shake'),
            'arm_select': SimpleNamespace(mode='right'),
            'pick_diverse_object': SimpleNamespace(target_familiarity='unseen'),
            'attribute_select': SimpleNamespace(axis='decal', value=1, AXIS_VALUES={'decal': ('cat','dog')}),
            'stack_sequence': SimpleNamespace(perm=[2,0,1], COLOR_NAMES=['red','green','blue']),
            'place_relative': SimpleNamespace(direction='on_top'),
        }
        expected = ['shake','right','unseen','decal:dog','blue>red>green','on_top']
        for (name, scene), mode in zip(scenes.items(), expected):
            with self.subTest(task=name):
                self.assertEqual(observed_mode(name, scene), mode)
                self.assertEqual(observed_mode(name, scene), _observed_mode(name, scene))
        with self.assertRaises(ValueError):
            observed_mode('unknown', SimpleNamespace())

    def test_all_six_clis_accept_all_six_tasks_and_two_blocks(self):
        for policy in ('xvla','lingbot_va','lingbot_vla','vlact','dm05','hy_vla'):
            module = importlib.import_module(f'policies.{policy}.eval')
            for task, contract in IF_SEED_CONTRACTS.items():
                manifest_path = ROOT/'seed-manifests/robotwin-if-arm-only-v2-20-per-mode'/f'{task}.json'
                with self.subTest(policy=policy, task=task), patch.object(sys, 'argv', [
                    'eval.py','--task',task,'--seed-manifest',
                    str(manifest_path), '--task-config', load_manifest(manifest_path)['task_config'],
                    '--blocks','2','--output-dir','unused-test-output']):
                    select = module.select_seeds
                    with patch.object(module, 'select_seeds', side_effect=InterruptedError) as selected:
                        with self.assertRaises(InterruptedError):
                            module.main()
                    args = selected.call_args.args[0]
                    seeds, manifest, split = select(args)
                    self.assertEqual(len(seeds), 2 * contract.block_size)
                    self.assertEqual(seeds, manifest['seeds'][:len(seeds)])
                    self.assertEqual(split, 'unseen')

    def test_attribute_target_distractor_and_reset_without_oracle(self):
        cls = task_class('attribute_select')
        cls._pair_ok = {50000: True}
        task = cls()
        task.setup_demo(seed=100000)
        self.assertFalse(task.check_success())
        task.other_position[2] += 0.1
        self.assertFalse(task.check_success())
        task.position[2] += 0.1
        self.assertFalse(task.check_success())
        task.other_position[2] -= 0.1
        self.assertFalse(task.check_success())
        task.setup_demo(seed=100001)
        self.assertFalse(task.check_success())
        task.position[2] += 0.1
        self.assertTrue(task.check_success())



if __name__ == '__main__':
    unittest.main()
