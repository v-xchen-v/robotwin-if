"""Paired bell scene sampling and a mode-independent first-action classifier."""
from dataclasses import asdict, dataclass
import math
import random

MODES = ("press", "lift")
INSTRUCTIONS = {"press": "Press the bell.", "lift": "Lift the bell."}
CONTEXT_LAYOUT_VERSION = "random-back-region-v1"


def sample_context_positions(scene_seed, bell_xy):
    """Sample distractors without consuming the task's global random streams."""
    rng = random.Random(f"press-lift-bell/context/{scene_seed}")
    positions = []
    for asset in ("047_mouse", "057_toycar"):
        for _ in range(256):
            xy = (rng.uniform(-0.30, 0.30), rng.uniform(0.04, 0.22))
            if math.dist(xy, bell_xy) < 0.22:
                continue
            if any(math.dist(xy, p[:2]) < 0.18 for _, p in positions):
                continue
            positions.append((asset, [*xy, 0.741]))
            break
        else:
            raise RuntimeError("Could not sample separated bell distractors")
    return positions


def mode_for_seed(seed):
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**32:
        raise ValueError("episode seed must be a uint32")
    return MODES[seed % 2]


@dataclass(frozen=True)
class BellRules:
    sample_seconds: float = 0.004
    lift_height_m: float = 0.03
    lift_seconds: float = 0.10
    preclosed_seconds: float = 0.08
    descent_m: float = 0.005
    retract_m: float = 0.02
    release_seconds: float = 0.06
    press_max_rise_m: float = 0.015
    press_max_xy_m: float = 0.03
    top_xy_m: float = 0.025
    top_z_m: float = 0.03


def bell_contacts(contacts, bell_name, table_name, gripper_names, cp, rules):
    """Use native contact reports, including zero-impulse proximity contacts."""
    supported = False
    arms = {arm: dict(touching=False, top_touch=False, contact_links=[])
            for arm in gripper_names}
    for contact in contacts:
        names = [body.entity.name for body in contact.bodies]
        if bell_name not in names or not contact.points:
            continue
        other = names[1] if names[0] == bell_name else names[0]
        if other == table_name:
            supported = True
        for arm, names in gripper_names.items():
            if other not in names:
                continue
            arms[arm]['touching'] = True
            arms[arm]['contact_links'].append(other)
            for point in contact.points:
                delta = [abs(float(point.position[i]) - float(cp[i])) for i in range(3)]
                if delta[0] < rules.top_xy_m and delta[1] < rules.top_xy_m and delta[2] < rules.top_z_m:
                    arms[arm]['top_touch'] = True
    return supported, arms


class BellMonitor:
    VERSION = "press-lift-bell-v3-native-contacts-every-step"

    def __init__(self, rules=BellRules()):
        if any(not math.isfinite(v) or v <= 0 for v in asdict(rules).values()):
            raise ValueError("thresholds must be finite and positive")
        self.rules = rules
        self.time = 0.0
        self.first_action = self.first_action_time = None
        self.events = []
        self.lift_since = None
        self.max_rise = 0.0
        self.max_xy = 0.0
        self.arms = {arm: dict(closed_since=None, approach_high_z=None, touching=False,
                              candidate=None, release_since=None) for arm in ("left", "right")}
        self.latest = {}

    def observe(self, time, rise, xy, supported, arms):
        if time <= self.time:
            raise ValueError("observations require strictly increasing physics time")
        gap = time - self.time > self.rules.sample_seconds * 1.6
        self.time = float(time)
        self.max_rise, self.max_xy = max(self.max_rise, rise), max(self.max_xy, xy)
        self.latest = dict(rise_m=rise, xy_displacement_m=xy, supported=supported, arms=arms)
        held = any(a["touching"] and a["closed"] for a in arms.values())
        lifting = held and not supported and rise >= self.rules.lift_height_m
        if not lifting or gap:
            self.lift_since = None
        if lifting:
            if self.lift_since is None:
                self.lift_since = time
            if time - self.lift_since + 1e-9 >= self.rules.lift_seconds:
                self._complete("lift")
        for arm, a in arms.items():
            state = self.arms[arm]
            if gap:
                state.update(closed_since=None, approach_high_z=None, candidate=None, release_since=None)
            if not a["closed"]:
                state["closed_since"] = None
                state["approach_high_z"] = None
            elif state["closed_since"] is None:
                state["closed_since"] = time
            high = state["approach_high_z"]
            descended = high is not None and high - a["ee_z"] >= self.rules.descent_m
            preclosed = state["closed_since"] is not None and time - state["closed_since"] >= self.rules.preclosed_seconds
            # Only arm on the FIRST contact after an already-closed downward approach.
            # Closing fingers onto the bell is not a press.
            if a["touching"] and not state["touching"] and state["candidate"] is None:
                state["candidate"] = (dict(touch_z=a["ee_z"], max_rise=rise, max_xy=xy)
                    if a["top_touch"] and preclosed and descended and supported else None)
            candidate = state["candidate"]
            if candidate is not None:
                candidate["max_rise"] = max(candidate["max_rise"], rise)
                candidate["max_xy"] = max(candidate["max_xy"], xy)
                if (not a["closed"] or candidate["max_rise"] > self.rules.press_max_rise_m
                        or candidate["max_xy"] > self.rules.press_max_xy_m):
                    state["candidate"] = None
                    state["release_since"] = None
                else:
                    released = (not held and not a["touching"] and supported
                                and a["ee_z"] - candidate["touch_z"] >= self.rules.retract_m)
                    if not released:
                        state["release_since"] = None
                    else:
                        if state["release_since"] is None:
                            state["release_since"] = time
                        if time - state["release_since"] + 1e-9 >= self.rules.release_seconds:
                            self._complete("press")
                            state["candidate"] = None
            state["touching"] = a["touching"]
            # Geometric descent since closure / last contact, without imposing
            # a pressing speed. Brief contact gaps must not erase an armed press.
            if a["closed"]:
                state["approach_high_z"] = (a["ee_z"] if a["touching"] or high is None
                                             else max(high, a["ee_z"]))

    def _complete(self, action):
        if action not in [e["action"] for e in self.events]:
            self.events.append(dict(action=action, time=self.time))
        if self.first_action is None:
            self.first_action, self.first_action_time = action, self.time

    def success(self, mode):
        if mode not in MODES:
            raise ValueError(f"unknown mode: {mode}")
        return self.first_action == mode

    def signals(self):
        return dict(checker_version=self.VERSION, thresholds=asdict(self.rules), time=self.time,
                    first_action=self.first_action, first_action_time=self.first_action_time,
                    events=list(self.events), max_rise_m=self.max_rise, max_xy_displacement_m=self.max_xy,
                    press_candidates={k: v["candidate"] for k, v in self.arms.items()}, **self.latest)
