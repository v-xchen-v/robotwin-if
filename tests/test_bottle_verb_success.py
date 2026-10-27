"""Frozen Bottle trajectories remain auditable after retiring the runtime task."""
import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.legacy_bottle_checker import PickHoldMonitor as Monitor, PickHoldRules as Rules


def quaternion(degrees):
    angle=math.radians(degrees)/2
    return (math.cos(angle), 0.0, math.sin(angle), 0.0)


def feed(monitor, seconds, pose, dt=.004):
    start=monitor.time
    for i in range(1,round(seconds/dt)+1):
        t=start+i*dt
        xyz,q=pose(t-start)
        monitor.observe(t,xyz,q)
    return monitor


class PickHoldTests(unittest.TestCase):
    def monitor(self,z=.785): return Monitor((.12,-.1,z))
    def held(self,z=.825): return lambda t: ((.12,-.1,z),quaternion(0))

    def test_saved_real_oracle_and_policy_motion_traces(self):
        path=ROOT/'tests/bottle_verb/fixtures/rotation-hold-traces.json'
        for case in json.loads(path.read_text())['cases']:
            with self.subTest(case=case['name']):
                m=Monitor(case['initial_position']);ever=False
                for row in case['poses']:
                    m.observe(row[0],row[1:4],row[4:8]);ever|=m.success
                self.assertEqual(m.success,case['final_hold'])
                self.assertEqual(m.shake_detected,case['shake_detected'])
                self.assertEqual(ever,case['ever_held'])

    def test_small_lift_stable_hold_succeeds_below_old_absolute_height(self):
        m=self.monitor();feed(m,3.1,self.held())
        self.assertTrue(m.success);self.assertLess(.825,.95)
        self.assertAlmostEqual(m.lift,.04)

    def test_relative_height_is_invariant_to_table_height(self):
        for z in (.55,.785,1.1):
            m=self.monitor(z);feed(m,3.1,self.held(z+.04));self.assertTrue(m.success)
            m=self.monitor(z);feed(m,4,self.held(z+.015));self.assertFalse(m.success)

    def test_on_table_short_hold_and_drop_are_not_success(self):
        m=self.monitor();feed(m,4,self.held(.785));self.assertFalse(m.success)
        feed(m,1.6,self.held());self.assertFalse(m.success)
        feed(m,.1,self.held(.79));self.assertFalse(m.success)
        feed(m,1.6,self.held());self.assertFalse(m.success)
        feed(m,1.5,self.held());self.assertTrue(m.success)

    def test_small_translation_and_rotation_jitter_are_tolerated(self):
        m=self.monitor()
        feed(m,3.2,lambda t: ((.12+.001*math.sin(6*math.pi*t),-.1,.825+.0005*math.sin(4*math.pi*t)),quaternion(2*math.sin(6*math.pi*t))))
        self.assertTrue(m.success);self.assertFalse(m.shake_detected)

    def test_one_second_pause_then_shake_never_latches_pick(self):
        old=Monitor((.12,-.1,.785),Rules(hold_seconds=1.0))
        current=self.monitor()
        for monitor in (old,current):feed(monitor,1.6,self.held())
        self.assertTrue(old.success)  # The previous evaluator would already stop here.
        self.assertFalse(current.success)
        for i in range(1,1001):
            t=i*.004
            current.observe(1.6+t,(.12,-.1,.825),quaternion(18*math.sin(4*math.pi*t)))
            self.assertFalse(current.success)
        self.assertTrue(current.shake_detected)
        feed(current,4,self.held());self.assertFalse(current.success)

    def test_requires_three_full_seconds_after_lift(self):
        m=self.monitor();feed(m,5,self.held(.785))
        feed(m,3,self.held());self.assertFalse(m.success)
        feed(m,.02,self.held());self.assertTrue(m.success)
        self.assertAlmostEqual(m.stable_seconds,3)

    def test_rotation_during_third_second_restarts_full_hold(self):
        m=self.monitor();feed(m,2.8,self.held())
        moved=lambda t: ((.12,-.1,.825),quaternion(12))
        feed(m,.1,moved);self.assertFalse(m.success)
        feed(m,2.8,moved);self.assertFalse(m.success)
        feed(m,.2,moved);self.assertTrue(m.success)

    def test_momentary_lift_without_final_hold_does_not_pass(self):
        m=self.monitor();passed=[]
        for i in range(1,401):
            t=i*.004
            m.observe(t,(.12,-.1,.91+.08*math.sin(4*math.pi*t)),quaternion(0))
            passed.append(m.success)
        self.assertGreater(m.initial_position[2]+m.peak_lift,.95)
        self.assertFalse(any(passed));self.assertFalse(m.shake_detected)
        feed(m,.1,self.held(.785));self.assertFalse(m.success)

    def test_orientation_shake_is_detected(self):
        m=self.monitor()
        feed(m,4,lambda t: ((.12,-.1,.825),quaternion(60*math.sin(4*math.pi*t))))
        self.assertTrue(m.shake_detected);self.assertFalse(m.success)
        feed(m,4,self.held());self.assertFalse(m.success)

    def test_translation_does_not_reset_or_veto_the_orientation_hold(self):
        for pose in (lambda t: ((.12+.08*t,-.1+.1*t,.825+.01*t),quaternion(0)),
                     lambda t: ((.12+.06*math.sin(4*math.pi*t),-.1,.91+.04*math.sin(4*math.pi*t)),quaternion(0))):
            m=self.monitor();feed(m,4,pose)
            self.assertTrue(m.success);self.assertFalse(m.shake_detected)
            self.assertGreater(m.position_path,.12)

    def test_translation_does_not_hide_simultaneous_rotation(self):
        m=self.monitor()
        feed(m,4,lambda t: ((.12+.08*t,-.1,.825+.01*t),quaternion(18*math.sin(2*math.pi*t))))
        self.assertTrue(m.shake_detected);self.assertFalse(m.success)

    def test_single_reorientation_then_hold_is_valid(self):
        m=self.monitor()
        feed(m,.8,lambda t: ((.12,-.1,.825),quaternion(90*t/.8)))
        self.assertFalse(m.success)
        feed(m,3.2,lambda t: ((.12,-.1,.825),quaternion(90)))
        self.assertTrue(m.success);self.assertFalse(m.shake_detected)

    def test_fast_rotation_cannot_hide_inside_orientation_radius(self):
        m=self.monitor()
        for i in range(1,1001):
            t=i*.004
            m.observe(t,(.12,-.1,.825),quaternion(3*math.sin(20*math.pi*t)))
            self.assertFalse(m.success)
        # Below reversal hysteresis, but excessive travel inside the small
        # orientation envelope must still veto a high-frequency rocking episode.
        self.assertTrue(m.shake_detected)
        feed(m,3.2,self.held());self.assertFalse(m.success)

    def test_long_hold_with_jitter_does_not_exhaust_a_lifetime_motion_budget(self):
        m=self.monitor()
        for i in range(1,6001):
            t=i*.004
            m.observe(t,(.12+.05*t,-.1,.825),quaternion(2*math.sin(6*math.pi*t)))
            if t > 3.1:self.assertTrue(m.success)
        self.assertFalse(m.shake_detected)

    def test_moderate_repeated_rotation_is_vetoed_even_after_later_pause(self):
        m=self.monitor()
        feed(m,4,lambda t: ((.12,-.1,.825),quaternion(8*math.sin(2*math.pi*t))))
        self.assertTrue(m.shake_detected)
        feed(m,4,self.held());self.assertFalse(m.success)

    def test_rotation_direction_is_not_lost_after_large_reorientation(self):
        # After turning 90 degrees about y, rocking about x barely changes the
        # old unsigned angle to the first lifted pose; it is still real rocking.
        m=self.monitor()
        feed(m,.4,self.held())
        feed(m,.8,lambda t: ((.12,-.1,.825),quaternion(90*t/.8)))
        def rock(t):
            a=math.radians(20*math.sin(2*math.pi*t))/2
            b=math.pi/4
            q=(math.cos(a)*math.cos(b),math.sin(a)*math.cos(b),
               math.cos(a)*math.sin(b),math.sin(a)*math.sin(b))
            return ((.12,-.1,.825),q)
        feed(m,4,rock)
        self.assertTrue(m.shake_detected)
        feed(m,4,lambda t: ((.12,-.1,.825),quaternion(90)))
        self.assertFalse(m.success)

    def test_rotation_crossing_180_degrees_is_not_a_reversal(self):
        m=self.monitor()
        feed(m,4,lambda t: ((.12,-.1,.825),quaternion(t*90)))
        self.assertFalse(m.shake_detected)
        feed(m,3.2,lambda t: ((.12,-.1,.825),quaternion(360)))
        self.assertTrue(m.success)

    def test_monotonic_large_lift_is_not_misclassified_as_shaking(self):
        m=self.monitor()
        feed(m,4,lambda t: ((.12,-.1,.785+.125*t),quaternion(0)))
        self.assertTrue(m.success);self.assertFalse(m.shake_detected)
        feed(m,3.2,self.held(1.285));self.assertTrue(m.success)

    def test_quaternion_sign_flips_are_not_motion(self):
        m=self.monitor()
        feed(m,3.2,lambda t: ((.12,-.1,.825),tuple((-1 if round(t/.004)%2 else 1)*v for v in quaternion(45))))
        self.assertTrue(m.success);self.assertFalse(m.shake_detected)

    def test_no_elapsed_time_from_duplicate_observations_or_reading_signals(self):
        m=self.monitor();feed(m,.4,self.held())
        before=m.signals()
        for _ in range(1000):
            m.observe(m.time,(.12,-.1,.825),quaternion(0));m.signals()
        self.assertEqual(m.signals(),before);self.assertFalse(m.success)

    def test_physics_timestep_does_not_change_hold_duration(self):
        for dt in (.002,.004,.01):
            m=self.monitor();feed(m,2.9,self.held(),dt);self.assertFalse(m.success)
            feed(m,.2,self.held(),dt);self.assertTrue(m.success)

    def test_invalid_pose_and_clock_are_rejected(self):
        m=self.monitor()
        for t,p,q in ((float('nan'),(0,0,0),(1,0,0,0)),(-1,(0,0,0),(1,0,0,0)),
                      (.02,(0,0,float('nan')),(1,0,0,0)),(.04,(0,0,0),(0,0,0,0))):
            with self.assertRaises(ValueError):m.observe(t,p,q)
        with self.assertRaises(ValueError):Monitor((0,0,0),Rules(hold_seconds=0))


if __name__ == '__main__':
    unittest.main()
