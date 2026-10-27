"""Shared press/lift classifier, distractor sampling and runner regressions.

BellMonitor is the base used by StaplerMonitor; retreat behavior here tests the
base compatibility contract. Stapler completion is tested in test_press_lift_stapler."""
import json
import math
import random
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tasks.envs._press_lift_bell import (BellMonitor, BellRules, bell_contacts,
                                        mode_for_seed, sample_context_positions)
from tasks.envs._press_lift_stapler import INSTRUCTIONS
from tools.press_lift_bell import selected_seeds, summarize_pairs
from policies.evaluation import setup_episode


class Trajectory:
    def __init__(self, dt=.02):
        self.monitor = BellMonitor(BellRules(sample_seconds=dt))
        self.dt = dt
        self.t = 0

    def step(self, n=1, *, z=0.90, touching=False, top=False, closed=True, rise=0., xy=0., supported=True):
        for _ in range(n):
            self.t += self.dt
            a = dict(ee_z=z, touching=touching, top_touch=top, closed=closed)
            idle = dict(ee_z=1., touching=False, top_touch=False, closed=False)
            self.monitor.observe(self.t, rise, xy, supported, dict(left=a, right=idle))
        return self.monitor

    def press(self):
        self.step(10)
        self.step(2, z=.88, touching=True, top=True)
        return self.step(5, z=.91)

    def lift(self):
        self.step(10, closed=False)
        self.step(3, z=.86, touching=True, top=True, closed=False)
        self.step(5, z=.86, touching=True, top=True)
        return self.step(7, z=.92, touching=True, top=True, rise=.06, supported=False)


class ClassifierTests(unittest.TestCase):
    def test_one_physics_step_contact_is_enough_to_arm_press(self):
        t = Trajectory(dt=.004)
        t.step(25)
        t.step(1, z=.88, touching=True, top=True)
        self.assertTrue(t.step(20, z=.91).success('press'))

    def test_native_contact_reports_do_not_require_impulse(self):
        def contact(other, position, impulse):
            return SimpleNamespace(bodies=[SimpleNamespace(entity=SimpleNamespace(name=n))
                                          for n in ('bell', other)],
                                   points=[SimpleNamespace(position=position, impulse=impulse)])
        cp = [0., 0., 1.]
        names = dict(left={'finger'}, right={'other_finger'})
        for impulse in ([0., 0., 0.], [1e-10, 0., 0.]):
            supported, arms = bell_contacts([contact('finger', cp, impulse), contact('table', cp, impulse)],
                                           'bell', 'table', names, cp, BellRules())
            self.assertTrue(supported)
            self.assertTrue(arms['left']['touching'])
            self.assertTrue(arms['left']['top_touch'])
            self.assertFalse(arms['right']['touching'])
        _, arms = bell_contacts([contact('finger', [.026, 0., 1.], [1., 0., 0.])],
                               'bell', 'table', names, cp, BellRules())
        self.assertTrue(arms['left']['touching'])
        self.assertFalse(arms['left']['top_touch'])

    def test_press_and_grasp_then_lift_are_exclusive(self):
        for action in ("press", "lift"):
            t = Trajectory()
            m = getattr(t, action)()
            self.assertEqual(m.first_action, action)
            self.assertTrue(m.success(action))
            self.assertFalse(m.success("lift" if action == "press" else "press"))

    def test_slow_press_and_intermittent_contact_keep_the_descent_evidence(self):
        t = Trajectory()
        t.step(10)
        for index in range(10):
            t.step(15, z=.90 - index * .002)
        t.step(2, z=.88, touching=True, top=True)
        t.step(1, z=.88)
        t.step(2, z=.88, touching=True, top=True)
        self.assertTrue(t.step(5, z=.91).success('press'))

    def test_touch_without_withdrawal_does_not_complete_press(self):
        t = Trajectory()
        t.step(10)
        m = t.step(20, z=.88, touching=True, top=True)
        self.assertIsNone(m.first_action)

    def test_closing_on_bell_and_releasing_is_not_press(self):
        t = Trajectory()
        t.step(10, closed=False)
        t.step(4, z=.86, touching=True, top=True, closed=False)
        t.step(10, z=.86, touching=True, top=True)
        self.assertIsNone(t.step(10, z=.92).first_action)

    def test_side_contact_upward_contact_and_open_touch_are_not_press(self):
        for top, z, closed in ((False, .88, True), (True, .92, True), (True, .88, False)):
            t = Trajectory()
            t.step(10, closed=closed)
            t.step(3, z=z, touching=True, top=top, closed=closed)
            self.assertIsNone(t.step(10, z=.96, closed=closed).first_action)

    def test_press_cannot_drag_or_lift_then_drop_bell(self):
        for displacement in (dict(rise=.02), dict(xy=.04)):
            t = Trajectory()
            t.step(10)
            t.step(2, z=.88, touching=True, top=True)
            t.step(1, z=.89, touching=True, top=True, **displacement)
            self.assertIsNone(t.step(10, z=.93).first_action)

    def test_height_without_gripper_contact_or_with_support_does_not_count(self):
        for touching, closed, supported, rise in ((False, True, False, .10), (True, False, False, .10),
                                                  (True, True, True, .10), (True, True, False, .02)):
            t = Trajectory()
            m = t.step(20, touching=touching, closed=closed, supported=supported, rise=rise)
            self.assertIsNone(m.first_action)

    def test_first_action_is_irrevocable_even_if_policy_does_both(self):
        for first, second in (("press", "lift"), ("lift", "press")):
            t = Trajectory()
            getattr(t, first)()
            t.step(30, closed=False)
            getattr(t, second)()
            self.assertEqual(t.monitor.first_action, first)
            self.assertFalse(t.monitor.success(second))
            self.assertEqual({e['action'] for e in t.monitor.events}, {first, second})

    def test_transient_lift_and_time_gap_do_not_satisfy_debounce(self):
        t = Trajectory()
        t.step(4, rise=.04, supported=False, touching=True)
        self.assertIsNone(t.monitor.first_action)
        t.t += 1
        m = t.step(1, rise=.04, supported=False, touching=True)
        self.assertIsNone(m.first_action)
        for _ in range(10):
            self.assertFalse(m.success('lift'))
        t.step(6, rise=.04, supported=False, touching=True)
        self.assertTrue(m.success('lift'))


class ContextSceneTests(unittest.TestCase):
    def test_paired_distractors_are_reproducible_without_global_rng_changes(self):
        state = random.getstate()
        for seed in range(16):
            bell = [-.16, -.12]
            press = sample_context_positions((2 * seed) // 2, bell)
            lift = sample_context_positions((2 * seed + 1) // 2, bell)
            self.assertEqual(press, lift)
        self.assertEqual(random.getstate(), state)

    def test_random_positions_keep_clearances_and_allow_both_left_right_orders(self):
        orders = set()
        layouts = set()
        for seed in range(256):
            bell = [(-1 if seed % 2 == 0 else 1) * (.14 if seed % 4 < 2 else .19),
                    -.15 if seed % 3 else -.10]
            poses = sample_context_positions(seed, bell)
            self.assertEqual([name for name, _ in poses], ['047_mouse', '057_toycar'])
            for _, position in poses:
                self.assertTrue(-.30 <= position[0] <= .30)
                self.assertTrue(.04 <= position[1] <= .22)
                self.assertGreaterEqual(math.dist(position[:2], bell), .22)
            self.assertGreaterEqual(math.dist(poses[0][1][:2], poses[1][1][:2]), .18)
            orders.add(poses[0][1][0] < poses[1][1][0])
            layouts.add(tuple(v for _, p in poses for v in p))
        self.assertEqual(orders, {False, True})
        self.assertEqual(len(layouts), 256)


class RunnerTests(unittest.TestCase):
    def test_seed_pair_and_mode_contract(self):
        self.assertEqual(selected_seeds(0, None, [0, 3]), [0, 1, 6, 7])
        self.assertEqual([mode_for_seed(s) for s in range(4)], ['press', 'lift'] * 2)
        for bad in (-1, 2**32, True):
            with self.assertRaises(ValueError):
                mode_for_seed(bad)
        rows = [dict(seed=0, mode='press', success=True), dict(seed=1, mode='lift', success=False)]
        self.assertEqual(summarize_pairs(rows)['both_success'], 0)

    def test_opt_in_instruction_is_preserved_through_oracle_reset(self):
        class Env:
            plan_success = True
            step_lim = 250
            def setup_demo(self, **kw): self.mode = mode_for_seed(kw['seed'])
            def play_once(self): return dict(mode=self.mode, info={})
            def check_success(self): return True
            def close_env(self): pass
            def policy_instruction(self, split): return INSTRUCTIONS[self.mode]
            def set_instruction(self, instruction): self.instruction = instruction
            def get_obs(self): return {'ready': True}
        with tempfile.TemporaryDirectory() as directory, patch('policies.xvla.eval.instruction_for') as generator:
            env, record = Env(), dict(mode=None)
            instruction, obs = setup_episode(env, {}, SimpleNamespace(task='press_lift_stapler'), 1,
                'unseen', record, lambda suffix: Path(directory) / ('episode' + suffix))
            self.assertEqual(instruction, 'Lift the stapler.')
            self.assertEqual(record['mode'], 'lift')
            generator.assert_not_called()


if __name__ == '__main__':
    unittest.main()
