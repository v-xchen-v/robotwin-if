"""Simulator-free pick-and-hold trajectory predicate, in metres and simulation seconds."""
from dataclasses import asdict, dataclass
from collections import deque
import math


@dataclass(frozen=True)
class PickHoldRules:
    min_lift: float = 0.03
    hold_seconds: float = 3.0
    rotation_radius_degrees: float = 10.0
    # Three-second totals preserve the original per-second jitter allowance.
    rotation_travel_degrees: float = 135.0
    reversal_angle_degrees: float = 10.0
    sample_seconds: float = 0.02


def distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def angle_degrees(a, b):
    # q and -q represent the same orientation; no Euler-angle wrap discontinuity.
    dot = min(1.0, abs(sum(x * y for x, y in zip(a, b))))
    return math.degrees(2 * math.acos(dot))


def rotation_increment_degrees(previous, current):
    """Signed world-axis rotation between poses; invariant to quaternion sign.

    Unlike distance to one reference orientation, this retains direction when
    the bottle rocks about an axis perpendicular to its initial reorientation.
    Small sampled increments also avoid Euler-angle wrap discontinuities.
    """
    w, x, y, z = current
    a, b, c, d = previous
    delta = (w*a + x*b + y*c + z*d,
             -w*b + x*a - y*d + z*c,
             -w*c + x*d + y*a - z*b,
             -w*d - x*c + y*b + z*a)
    if delta[0] < 0:
        delta = tuple(-v for v in delta)
    size = math.sqrt(sum(v*v for v in delta[1:]))
    if size < 1e-12:
        return (0.0, 0.0, 0.0)
    scale = math.degrees(2 * math.atan2(size, delta[0])) / size
    return tuple(v * scale for v in delta[1:])


class _Reversals:
    """Count resolved changes of direction, ignoring sub-threshold jitter."""
    def __init__(self, value, amplitude):
        self.extreme = value
        self.low = self.high = value
        self.amplitude = amplitude
        self.direction = 0
        self.count = 0

    def observe(self, value):
        delta = value - self.extreme
        if not self.direction:
            self.low = min(self.low, value)
            self.high = max(self.high, value)
            if value - self.low >= self.amplitude or self.high - value >= self.amplitude:
                self.direction = 1 if value - self.low >= self.amplitude else -1
                self.extreme = value
        elif delta * self.direction >= 0:
            self.extreme = value
        elif abs(delta) >= self.amplitude:
            self.count += 1
            self.direction *= -1
            self.extreme = value


class PickHoldMonitor:
    VERSION = "relative-lift-hold-v6-terminal"

    def __init__(self, initial_position, rules=PickHoldRules()):
        if any(not math.isfinite(v) or v <= 0 for v in asdict(rules).values()):
            raise ValueError("Pick thresholds and sampling interval must be positive and finite")
        self.rules = rules
        self.initial_position = tuple(float(v) for v in initial_position)
        if len(self.initial_position) != 3 or not all(map(math.isfinite, self.initial_position)):
            raise ValueError("Expected a finite initial bottle position")
        self.time = self.sample_time = 0.0
        self.lift = self.peak_lift = 0.0
        self.hold_start = None
        self.position_path = self.rotation_path = 0.0
        self.turns = None
        self.shake_detected = False
        self.shake_reason = None
        self.shake_time = self.first_lift_time = None
        self.state = "not_lifted"

    def _start_hold(self, position, quaternion):
        self.hold_start = self.time
        self.previous_position = position
        self.previous_quaternion = quaternion
        self.position_path = self.rotation_path = 0.0
        self.hold_samples = deque([(self.time, quaternion, 0.0, 0.0)])
        self.state = "holding"

    def observe(self, simulation_time, position, quaternion):
        now = float(simulation_time)
        if not math.isfinite(now) or now < self.time:
            raise ValueError("Simulation time must be finite and monotonic")
        # Polling the checker, rendering, or waiting for inference cannot advance time.
        if now == self.time:
            return
        self.time = now
        if now - self.sample_time + 1e-9 < self.rules.sample_seconds:
            return
        self.sample_time = now
        position = tuple(float(v) for v in position)
        quaternion = tuple(float(v) for v in quaternion)
        if len(position) != 3 or len(quaternion) != 4 or not all(map(math.isfinite, position + quaternion)):
            raise ValueError("Expected a finite bottle pose")
        norm = math.sqrt(sum(v*v for v in quaternion))
        if norm < 1e-12:
            raise ValueError("Bottle quaternion must be nonzero")
        quaternion = tuple(v/norm for v in quaternion)
        self.lift = position[2] - self.initial_position[2]
        self.peak_lift = max(self.peak_lift, self.lift)
        lifted = self.lift + 1e-9 >= self.rules.min_lift
        if lifted and self.turns is None:
            self.first_lift_time = now
            self.shake_previous_quaternion = quaternion
            self.signed_rotation = (0.0, 0.0, 0.0)
            self.turns = [_Reversals(0.0, self.rules.reversal_angle_degrees) for _ in range(3)]
        if self.turns is not None:
            increment = rotation_increment_degrees(self.shake_previous_quaternion, quaternion)
            self.signed_rotation = tuple(a+b for a, b in zip(self.signed_rotation, increment))
            self.shake_previous_quaternion = quaternion
            for tracker, value in zip(self.turns, self.signed_rotation):
                tracker.observe(value)
            if not self.shake_detected and any(t.count >= 2 for t in self.turns):
                self.shake_detected = True
                self.shake_time = now
                self.shake_reason = 'rotation_reversals'
        if self.shake_detected or not lifted:
            self.hold_start = None
            self.state = "shaking" if self.shake_detected else "not_lifted"
            return
        if self.hold_start is None:
            self._start_hold(position, quaternion)
            return
        translation = distance(position, self.previous_position)
        rotation = angle_degrees(quaternion, self.previous_quaternion)
        self.position_path += translation
        self.rotation_path += rotation
        self.hold_samples.append((now, quaternion, translation, rotation))
        self.previous_position, self.previous_quaternion = position, quaternion
        # Evaluate a trailing 3 s window, not a lifetime motion budget. Otherwise
        # harmless jitter would periodically invalidate long terminal rollouts.
        while len(self.hold_samples) > 1 and self.hold_samples[1][0] <= now - self.rules.hold_seconds:
            self.hold_samples.popleft()
            self.position_path -= self.hold_samples[0][2]
            self.rotation_path -= self.hold_samples[0][3]
        # Translation is allowed while the bottle stays lifted. Only rotation
        # can reset a hold or latch the episode-wide rocking veto.
        if self.rotation_path > self.rules.rotation_travel_degrees:
            self.shake_detected = True
            self.shake_time = now
            self.shake_reason = 'rotation_travel'
            self.hold_start = None
            self.state = 'shaking'
            return
        anchor = self.hold_samples[0][1]
        if any(angle_degrees(q, anchor) > self.rules.rotation_radius_degrees
               for _, q, _, _ in self.hold_samples):
            self._start_hold(position, quaternion)
        self.state = "success" if self.success else "holding"

    @property
    def stable_seconds(self):
        return 0.0 if self.hold_start is None else self.sample_time - self.hold_start

    @property
    def success(self):
        return (not self.shake_detected and self.hold_start is not None
                and self.stable_seconds + 1e-9 >= self.rules.hold_seconds)

    def signals(self):
        return dict(checker_version=self.VERSION, initial_bottle_z=self.initial_position[2],
            current_lift_m=self.lift, peak_lift_m=self.peak_lift,
            simulation_seconds=self.time, stable_seconds=self.stable_seconds,
            pick_success=bool(self.success), state=self.state,
            shake_detected=self.shake_detected, shake_detected_at=self.shake_time,
            shake_reason=self.shake_reason,
            first_lift_at=self.first_lift_time,
            reversal_axes=['rotation_x', 'rotation_y', 'rotation_z'],
            reversals=[t.count for t in self.turns] if self.turns is not None else [0]*3,
            stable_position_travel_m=self.position_path,
            stable_rotation_travel_degrees=self.rotation_path, thresholds=asdict(self.rules))
