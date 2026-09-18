"""Regression tests for wrong-object history in Attribute-Select."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

from tasks.envs._if_grounding import AttributePickMonitor


class FakeScene:
    def __init__(self):
        self.steps = 0

    def step(self):
        self.steps += 1
        return self.steps


class FakeBase:
    def _init_task_env_(self, seed, **kwargs):
        self.scene = FakeScene()
        bias = kwargs.get('table_height_bias', 0)
        self.positions = {'target': [0, 0, .77 + bias], 'distractor': [.2, 0, .79 + bias]}
        self.target = SimpleNamespace(get_pose=lambda: SimpleNamespace(p=self.positions['target']))
        self.distractor = SimpleNamespace(get_pose=lambda: SimpleNamespace(p=self.positions['distractor']))
        self.axis = ('color', 'decal', 'shape', 'size')[(seed // 2) % 4]
        self.value = seed % 2
        self._init_z = {}
        self.take_action_cnt = 0
        self.info = {}

    def close_env(self, clear_cache=False):
        self.closed = True


def task_class():
    path = Path(__file__).resolve().parents[1] / 'tasks/envs/attribute_select.py'
    tree = ast.parse(path.read_text())
    tree.body = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    namespace = dict(Base_Task=FakeBase, np=np, AttributePickMonitor=AttributePickMonitor,
                     apply_if_eval_step_limit=lambda env: None)
    exec(compile(tree, str(path), 'exec'), namespace)
    return namespace['attribute_select']


class AttributeSuccessTests(unittest.TestCase):
    def setUp(self):
        self.Task = task_class()
        self.env = self.Task()
        self.reset()
        self.addCleanup(self.env.close_env)

    def reset(self, seed=100000, **kwargs):
        self.env.setup_demo(seed=seed, **kwargs)
        self.Task._pair_ok[seed // 2] = True

    def move(self, target=0, distractor=0):
        for name, lift in [('target', target), ('distractor', distractor)]:
            self.env.positions[name][2] = self.env._init_z[name] + lift
        self.env.take_action_cnt += 1
        self.env.scene.step()

    def test_wrong_pick_then_drop_then_target_fails_for_all_eight_modes(self):
        for seed in range(100000, 100008):
            with self.subTest(seed=seed):
                self.reset(seed)
                # No success/signal query while the wrong object is in the air.
                self.move(distractor=.10)
                self.move()
                self.move(target=.10)
                self.assertFalse(self.env.check_success())
                sig = self.env.eval_signals()
                self.assertTrue(sig['target_lifted'])
                self.assertTrue(sig['distractor_lifted_ever'])
                self.assertFalse(sig['grasped_target'])
                self.assertEqual(sig['first_lifted'], 'distractor')
                self.assertEqual(sig['first_distractor_lift_action'], 1)

    def test_simultaneous_pick_fails_without_target_priority(self):
        self.move(target=.10, distractor=.10)
        self.assertFalse(self.env.check_success())
        self.assertEqual(self.env.eval_signals()['lifted'], 'both')
        self.move(target=.10)
        self.assertFalse(self.env.check_success())

    def test_clean_target_pick_still_succeeds_for_all_eight_modes(self):
        for seed in range(100000, 100008):
            with self.subTest(seed=seed):
                self.reset(seed)
                self.assertFalse(self.env.check_success())
                self.move(target=.10)
                self.assertTrue(self.env.check_success())
                self.move()
                self.assertFalse(self.env.check_success())

    def test_table_nudge_does_not_count_as_wrong_pick(self):
        self.move(distractor=.02)
        self.move(target=.10)
        self.assertTrue(self.env.check_success())
        self.assertFalse(self.env.eval_signals()['distractor_lifted_ever'])

    def test_existing_strict_lift_threshold_is_preserved(self):
        monitor = AttributePickMonitor({'target': 0., 'distractor': 0.})
        monitor.observe(.05, .05)
        self.assertFalse(monitor.success)
        self.assertFalse(monitor.distractor_lifted_ever)
        monitor.observe(.050001, .05)
        self.assertTrue(monitor.success)
        monitor.observe(.050001, .050001)
        self.assertFalse(monitor.success)

    def test_target_then_distractor_also_invalidates_episode(self):
        self.move(target=.10)
        self.move(target=.10, distractor=.10)
        self.move(target=.10)
        self.assertFalse(self.env._raw_success())

    def test_reset_clears_history_and_detaches_old_scene(self):
        self.move(distractor=.10)
        old_scene = self.env.scene
        self.reset(seed=100001, table_height_bias=.15)
        self.assertFalse(self.env.eval_signals()['distractor_lifted_ever'])
        self.assertAlmostEqual(self.env._init_z['target'], .92)
        self.env.positions['distractor'][2] += .10
        old_scene.step()
        self.assertFalse(self.env._pick_monitor.distractor_lifted_ever)
        self.move(target=.10)
        self.assertTrue(self.env.check_success())

    def test_close_restores_scene_step_and_queries_are_idempotent(self):
        self.move(distractor=.10)
        before = self.env.eval_signals()
        for _ in range(10):
            self.assertFalse(self.env.check_success())
            self.assertEqual(self.env.eval_signals(), before)
        json.dumps(before, allow_nan=False)
        scene = self.env.scene
        self.env.close_env()
        self.env.positions['target'][2] += .10
        scene.step()
        self.assertEqual(self.env._pick_monitor.signals()['lift_m'], before['lift_m'])
        self.assertIsNone(self.env._pick_observer)

    def test_clean_target_still_requires_oracle_pair_gate(self):
        self.move(target=.10)
        self.Task._pair_ok[self.env._seed // 2] = False
        self.assertTrue(self.env._raw_success())
        self.assertFalse(self.env.check_success())


if __name__ == '__main__':
    unittest.main()
