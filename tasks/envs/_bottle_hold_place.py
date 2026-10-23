"""Simulator-free rules for the experimental bottle hold/place task."""

from dataclasses import asdict, dataclass
import math


MODES = ("hold", "place")
INSTRUCTIONS = {
    "hold": "Hold the bottle steadily above the blue pad.",
    "place": "Place the bottle on the blue pad and release it.",
}


def mode_for_seed(seed):
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise ValueError("seed must be a uint32 integer")
    return MODES[seed % 2]


@dataclass(frozen=True)
class HoldPlaceRules:
    target_radius_m: float = 0.05
    min_clearance_m: float = 0.05
    max_clearance_m: float = 0.20
    stable_seconds: float = 2.0
    position_tolerance_m: float = 0.015
    rotation_tolerance_degrees: float = 10.0
    sample_seconds: float = 0.02


def rotation_degrees(a, b):
    dot = min(1.0, abs(sum(x * y for x, y in zip(a, b))))
    return math.degrees(2 * math.acos(dot))


class HoldPlaceMonitor:
    """Two exclusive, sustained terminal states; querying never advances time.

    A prior transient success is not latched. A model can correct an earlier
    mistake: the instructions constrain the final state, not the whole path.
    Clearance is the bottle bounding box's lowest point above the pad surface.
    Contacts come from physics, not a height-only proxy for holding/releasing.
    """

    VERSION = "bottle-hold-place-v1-terminal"

    def __init__(self, rules=HoldPlaceRules()):
        if any(not math.isfinite(v) or v <= 0 for v in asdict(rules).values()):
            raise ValueError("all rule values must be finite and positive")
        if rules.min_clearance_m >= rules.max_clearance_m:
            raise ValueError("clearance range must be nonempty")
        self.rules = rules
        self.time = 0.0
        self.candidate = None
        self.since = None
        self.anchor_position = self.anchor_quaternion = None
        self.previous_position = self.previous_quaternion = None
        self.target_distance = self.clearance = None
        self.held = self.supported = False
        self.ever_held = self.ever_supported = False
        self.lifted_while_held = False
        self.vertical_travel = self.rotation_travel = 0.0

    def observe(self, time, position, quaternion, target_xy, clearance, held, supported):
        time = float(time)
        if not math.isfinite(time) or time < self.time:
            raise ValueError("simulation time must be finite and monotonic")
        if time == self.time:
            return
        position, quaternion, target_xy = tuple(position), tuple(quaternion), tuple(target_xy)
        if (len(position) != 3 or len(quaternion) != 4 or len(target_xy) != 2
                or not all(math.isfinite(v) for v in (*position, *quaternion, *target_xy, clearance))):
            raise ValueError("expected finite position, quaternion, target and clearance")
        norm = math.sqrt(sum(v * v for v in quaternion))
        if norm < 1e-12:
            raise ValueError("quaternion cannot be zero")
        quaternion = tuple(v / norm for v in quaternion)
        # Missing samples cannot count as observed stable holding.
        gap = time - self.time > self.rules.sample_seconds * 2.5
        self.time = time
        self.target_distance = math.dist(position[:2], target_xy)
        self.clearance = float(clearance)
        self.held, self.supported = bool(held), bool(supported)
        self.ever_held |= self.held
        self.ever_supported |= self.supported
        self.lifted_while_held |= self.held and clearance >= self.rules.min_clearance_m
        if self.previous_position is not None:
            self.vertical_travel += abs(position[2] - self.previous_position[2])
            self.rotation_travel += rotation_degrees(quaternion, self.previous_quaternion)
        self.previous_position, self.previous_quaternion = position, quaternion
        candidate = None
        if self.target_distance <= self.rules.target_radius_m:
            if (self.held and not self.supported
                    and self.rules.min_clearance_m <= clearance <= self.rules.max_clearance_m):
                candidate = "hold"
            elif self.supported and not self.held and self.lifted_while_held:
                candidate = "place"
        if candidate is None:
            self.candidate = self.since = None
            return
        moved = (self.anchor_position is not None and (
            math.dist(position, self.anchor_position) > self.rules.position_tolerance_m
            or rotation_degrees(quaternion, self.anchor_quaternion) > self.rules.rotation_tolerance_degrees))
        if gap or candidate != self.candidate or moved:
            self.since = time
            self.anchor_position, self.anchor_quaternion = position, quaternion
        self.candidate = candidate

    @property
    def stable_seconds(self):
        return 0.0 if self.since is None else self.time - self.since

    def success(self, mode):
        if mode not in MODES:
            raise ValueError(f"unknown mode: {mode}")
        return self.candidate == mode and self.stable_seconds + 1e-9 >= self.rules.stable_seconds

    def signals(self):
        return dict(checker_version=self.VERSION, thresholds=asdict(self.rules),
                    simulation_seconds=self.time, stable_seconds=self.stable_seconds,
                    candidate=self.candidate, hold_success=self.success("hold"),
                    place_success=self.success("place"), held=self.held,
                    supported_by_pad=self.supported, target_distance_m=self.target_distance,
                    clearance_m=self.clearance, ever_held=self.ever_held,
                    lifted_while_held=self.lifted_while_held,
                    ever_supported_by_pad=self.ever_supported,
                    vertical_travel_m=self.vertical_travel,
                    rotation_travel_degrees=self.rotation_travel)
