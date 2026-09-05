"""Shared success predicates for the Place-Relative IF task (IF-Spatial-Direction).

The placement DIRECTION is the scored axis. Four lateral directions are signed
offsets on one world axis with the orthogonal axis locked (mirrors native
place_a2b_left: 'left' = object_x < target_x, |Δy|<0.05, planar dist in [0.08,0.2]);
'on top' is an elevation stack (planar ~0, clearly raised). All predicates require the
grippers open (the object was released, not still carried) and bind to the specific
named A (mover) and B (reference) actors -> placing a distractor or picking nothing
leaves A at rest and fails, which is exactly the target- + direction-specific check the
IF task needs.

The four lateral directions are mutually exclusive by construction, and jointly
exclusive with on-top:
  - wrong side (asked left, placed right) -> signed offset flips -> False
  - stacked when a lateral direction was asked -> planar < lo (0.08) -> False
  - placed beside when on-top was asked -> not elevated -> False

Thresholds 类推自 native place_a2b (lateral band / orthogonal lock) and
stack_blocks_two + place_object_stand (stacked / xy-aligned)，论文未确认.
"""
import numpy as np

# World-y sign that points "front" = toward the robot. The robot faces the table
# along world y; which sign is toward it is the one empirically-verified unknown
# (see docs/features/09 §6). Pinned by the oracle diagnostic + a front/back render
# spot-check; flip this single constant if front/back read reversed.
FRONT_SIGN = 1.0

# direction -> (axis index, signed direction along that axis). x=0 (left/right),
# y=1 (front/back). Consumed by place_relative.play_once (to build the target) and
# check_success (to score), so the oracle and the check never disagree on a sign.
_AXIS = {"x": 0, "y": 1}
DIRECTIONS = {
    "left":  ("x", -1.0),
    "right": ("x", +1.0),
    "front": ("y", +FRONT_SIGN),
    "back":  ("y", -FRONT_SIGN),
}


def _planar_dist(a, b):
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def _grippers_open(task):
    return bool(task.robot.is_left_gripper_open() and task.robot.is_right_gripper_open())


def placed_in_direction(task, mover, reference, axis, sign,
                        lo=0.08, hi=0.20, orth_lock=0.05, same_z=0.04):
    """True iff `mover` rests NEXT TO `reference` on the table in the commanded
    direction (not stacked): planar distance in [lo, hi], the commanded-axis offset
    has the commanded sign, the orthogonal axis is locked (|Δ|<orth_lock), similar
    height, grippers released."""
    a = mover.get_pose().p
    b = reference.get_pose().p
    ai = _AXIS[axis]
    oi = 1 - ai
    d = _planar_dist(a, b)
    signed = (a[ai] - b[ai]) * sign          # >0 means on the commanded side
    orth = abs(a[oi] - b[oi])
    return bool(lo <= d <= hi and signed > 0 and orth < orth_lock
                and abs(a[2] - b[2]) < same_z and _grippers_open(task))


def placed_on_top(task, mover, reference, planar=0.05, min_rise=0.02):
    """True iff `mover` sits ON TOP OF `reference`: planar distance < planar (aligned
    over B) and clearly elevated above B's center, grippers released."""
    a = mover.get_pose().p
    b = reference.get_pose().p
    return bool(_planar_dist(a, b) < planar and (a[2] - b[2]) > min_rise and _grippers_open(task))
