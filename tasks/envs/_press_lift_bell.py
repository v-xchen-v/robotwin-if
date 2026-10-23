"""Physics-time first-completed-action classifier; independent of commanded mode."""
from collections import deque
from dataclasses import asdict, dataclass
import math

MODES = ("press", "lift")
INSTRUCTIONS = {"press": "Press the bell.", "lift": "Lift the bell."}


def mode_for_seed(seed):
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**32:
        raise ValueError("episode seed must be a uint32")
    return MODES[seed % 2]


@dataclass(frozen=True)
class BellRules:
    sample_seconds: float = 0.02
    lift_height_m: float = 0.03
    lift_seconds: float = 0.10
    preclosed_seconds: float = 0.08
    descent_m: float = 0.005
    descent_window_seconds: float = 0.50
    retract_m: float = 0.02
    release_seconds: float = 0.06
    press_max_rise_m: float = 0.015
    press_max_xy_m: float = 0.03
    top_xy_m: float = 0.025
    top_z_m: float = 0.03


class BellMonitor:
    VERSION = "press-lift-bell-v1-first-action"

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
        self.arms = {arm: dict(closed_since=None, history=deque(), touching=False,
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
                state.update(closed_since=None, candidate=None, release_since=None)
                state["history"].clear()
            if not a["closed"]:
                state["closed_since"] = None
            elif state["closed_since"] is None:
                state["closed_since"] = time
            history = state["history"]
            while history and time - history[0][0] > self.rules.descent_window_seconds:
                history.popleft()
            descended = bool(history) and max(z for _, z in history) - a["ee_z"] >= self.rules.descent_m
            preclosed = state["closed_since"] is not None and time - state["closed_since"] >= self.rules.preclosed_seconds
            # Only arm on the FIRST contact after an already-closed downward approach.
            # Closing fingers onto the bell is not a press.
            if a["touching"] and not state["touching"]:
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
            history.append((time, a["ee_z"]))

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
