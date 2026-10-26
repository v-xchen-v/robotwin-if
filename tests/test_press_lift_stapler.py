"""Native stapler contact window and shared first-action counterexamples."""
import math
import random
from types import SimpleNamespace
import unittest

from tasks.envs._press_lift_bell import bell_contacts
from tasks.envs._press_lift_stapler import (StaplerMonitor, resting_quaternion,
                                          sample_rotations, stapler_rules)


class StaplerRotationTests(unittest.TestCase):
    def test_world_yaw_preserves_upright_axis(self):
        for degrees in (-180, -15, 0, 15, 90, 180):
            w, x, y, z = resting_quaternion(degrees)
            self.assertAlmostEqual(w*w + x*x + y*y + z*z, 1)
            # Native local Y points upwards; yaw must not introduce roll/pitch.
            upright = (2*(x*y-w*z), 1-2*(x*x+z*z), 2*(y*z+w*x))
            for value, expected in zip(upright, (0, 0, 1)):
                self.assertAlmostEqual(value, expected)
            forward = (1-2*(y*y+z*z), 2*(x*y+w*z), 2*(x*z-w*y))
            for value, expected in zip(forward, (-math.sin(math.radians(degrees)),
                                                math.cos(math.radians(degrees)), 0)):
                self.assertAlmostEqual(value, expected)

    def test_scene_seed_reproducibility_without_consuming_global_rng(self):
        before = random.getstate()
        first = sample_rotations(50000)
        self.assertEqual(before, random.getstate())
        self.assertEqual(first, sample_rotations(100001 // 2))
        second = sample_rotations(50001)
        for asset, limit in (("048_stapler", 15), ("047_mouse", 180), ("057_toycar", 180)):
            self.assertNotEqual(first[asset], second[asset])
            self.assertLessEqual(abs(first[asset]['yaw_degrees']), limit)
            self.assertLessEqual(abs(second[asset]['yaw_degrees']), limit)


class StaplerClassifierTests(unittest.TestCase):
    def test_press_finishes_on_contact_without_native_absent_retreat(self):
        monitor = StaplerMonitor(stapler_rules())
        idle = dict(touching=False, top_touch=False, closed=False, ee_z=1.)
        for _ in range(30):
            monitor.observe(monitor.time + .004, 0., 0., True,
                            dict(left=dict(touching=False, top_touch=False, closed=True, ee_z=.95), right=idle))
        monitor.observe(monitor.time + .004, 0., 0., True,
                        dict(left=dict(touching=True, top_touch=True, closed=True, ee_z=.93), right=idle))
        self.assertTrue(monitor.success('press'))
        self.assertFalse(monitor.success('lift'))
        self.assertNotIn('retract_m', monitor.signals()['thresholds'])

    def test_native_press_window_includes_zero_impulse_contacts(self):
        for offset, expected in ((0.029, True), (0.031, False)):
            contact = SimpleNamespace(bodies=[SimpleNamespace(entity=SimpleNamespace(name=n))
                                               for n in ('stapler', 'finger')],
                                      points=[SimpleNamespace(position=[offset, 0, 0], impulse=[0, 0, 0])])
            _, arms = bell_contacts([contact], 'stapler', 'table', {'left': {'finger'}}, [0, 0, 0], stapler_rules())
            self.assertTrue(arms['left']['touching'])
            self.assertEqual(arms['left']['top_touch'], expected)

    def test_closing_on_head_then_lifting_is_lift_not_press(self):
        monitor = StaplerMonitor(stapler_rules())
        idle = dict(touching=False, top_touch=False, closed=False, ee_z=1.)
        def step(count, *, touching=False, top=False, closed=False, rise=0., supported=True, z=.95):
            for _ in range(count):
                monitor.observe(monitor.time + .004, rise, 0., supported,
                                dict(left=dict(touching=touching, top_touch=top, closed=closed, ee_z=z), right=idle))
        step(30)
        step(30, touching=True, top=True, z=.90)
        step(30, touching=True, top=True, closed=True, z=.90)
        self.assertIsNone(monitor.first_action)
        step(30, touching=True, top=True, closed=True, rise=.04, supported=False, z=.94)
        self.assertTrue(monitor.success('lift'))
        self.assertFalse(monitor.success('press'))


if __name__ == '__main__':
    unittest.main()
