"""Policy grasp scoring observes first contact without executing the oracle."""

import ast
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

import numpy as np
import transforms3d as t3d

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class BaseTask:
    def _init_task_env_(self, seed, **kwargs):
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
    namespace = dict(Base_Task=BaseTask, np=np, t3d=t3d, ArmTag=str,
                     apply_if_eval_step_limit=lambda task: None)
    exec(compile(tree, str(path), 'exec'), namespace)
    return namespace[name]


class PolicyEvaluationTests(unittest.TestCase):
    def test_grasp_policy_approach_is_observed_before_lift(self):
        cls = task_class('grasp_cube_approach')
        for seed, rotation in [(100000, t3d.euler.euler2quat(0, np.pi/2, 0)),
                               (100001, [1.,0.,0.,0.])]:
            with self.subTest(seed=seed):
                task = cls()
                task.setup_demo(seed=seed)
                task.start_policy_rollout()
                self.assertFalse(task.check_success())
                self.assertFalse(task.eval_signals()['orientation_match'])
                task.contact = True
                task.rotation = rotation
                self.assertFalse(task.check_success())
                self.assertTrue(task.eval_signals()['orientation_match'])
                task.position[2] += 0.1
                self.assertTrue(task.check_success())
                task.setup_demo(seed=seed)
                task.start_policy_rollout()
                self.assertFalse(task.check_success())
                self.assertFalse(task.eval_signals()['policy_approach_observed'])

    def test_wrong_approach_cannot_be_fixed_by_rotating_after_contact(self):
        task = task_class('grasp_cube_approach')()
        task.setup_demo(seed=100000)
        task.start_policy_rollout()
        task.contact = True
        self.assertFalse(task.check_success())
        task.rotation = t3d.euler.euler2quat(0, np.pi/2, 0)
        task.position[2] += 0.1
        self.assertFalse(task.check_success())
        self.assertTrue(task.eval_signals()['lifted'])
        self.assertFalse(task.eval_signals()['orientation_match'])

    def test_no_contact_lift_does_not_inherit_an_oracle_orientation(self):
        task = task_class('grasp_cube_approach')()
        task.setup_demo(seed=100001)
        task.start_policy_rollout()
        task.position[2] += 0.1
        self.assertFalse(task.check_success())
        self.assertFalse(task.eval_signals()['orientation_match'])


if __name__ == '__main__':
    unittest.main()
