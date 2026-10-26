"""Stapler pilot parameters; reuse the existing first-completed-action monitor."""
import math
import random

from ._press_lift_bell import BellMonitor, BellRules

INSTRUCTIONS = {"press": "Press down on the stapler.", "lift": "Lift the stapler."}
MODEL_IDS = (0, 4)
PRESS_CONTACT_POINT = 2  # Native points 0/1 grasp the body; point 2 presses the head.
ROTATION_VERSION = "random-yaw-v1"
YAW_LIMITS_DEGREES = {"048_stapler": 15.0, "047_mouse": 180.0, "057_toycar": 180.0}


def resting_quaternion(yaw_degrees):
    """World-Z yaw left-multiplied onto native [0.5]*4, in SAPIEN wxyz order."""
    c, s = math.cos(math.radians(yaw_degrees) / 2), math.sin(math.radians(yaw_degrees) / 2)
    return [(c - s) / 2, (c - s) / 2, (c + s) / 2, (c + s) / 2]


def sample_rotations(scene_seed):
    """Independent per-asset streams leave position sampling and mode untouched."""
    rotations = {}
    for asset, limit in YAW_LIMITS_DEGREES.items():
        rng = random.Random(f"press-lift-stapler/{ROTATION_VERSION}/{scene_seed}/{asset}")
        yaw = rng.uniform(-limit, limit)
        rotations[asset] = dict(yaw_degrees=yaw, quaternion=resting_quaternion(yaw))
    return rotations


class StaplerMonitor(BellMonitor):
    VERSION = "press-lift-stapler-v1-native-press-contact"

    def observe(self, time, rise, xy, supported, arms):
        super().observe(time, rise, xy, supported, arms)
        # Native press_stapler stops on contact, without a retreat. Retain the
        # preclosed downward approach gate so closing around the body is a grasp.
        if supported and rise <= self.rules.press_max_rise_m and xy <= self.rules.press_max_xy_m:
            if any(self.arms[arm]['candidate'] is not None and state['touching'] and state['top_touch']
                   and state['closed'] for arm, state in arms.items()):
                self._complete('press')

    def signals(self):
        signals = super().signals()
        # These BellMonitor release parameters are not part of this task's verdict.
        for key in ('retract_m', 'release_seconds'):
            signals['thresholds'].pop(key)
        signals['press_completion'] = 'native-contact-after-preclosed-downward-approach'
        return signals


def stapler_rules(sample_seconds=0.004):
    # Native press_stapler uses a +/- 3 cm box around contact point 2.
    # The preclosed approach gate distinguishes pressing from closing a grasp.
    return BellRules(sample_seconds=sample_seconds, top_xy_m=0.03, top_z_m=0.03)
