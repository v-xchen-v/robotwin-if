"""Shared success predicates for the Place-Relative IF task.

The relation word is the scored axis, so the two predicates are deliberately
mutually exclusive by planar distance: an on-top placement (A directly over B) has
planar distance ~0 and fails `placed_beside`; a beside placement (A next to B at the
same height) fails `placed_on_top`'s elevation test. Both require the grippers open
(the object was released, not still carried). Because both bind to the specific named
A and B actors, picking or placing a distractor leaves A at rest -> False, which is
exactly the target-specific + relation-specific check the IF task needs.

Thresholds 类推自 native place_a2b (beside band) / stack_blocks_two + place_object_stand
(stacked/xy-aligned)，论文未确认.
"""
import numpy as np


def _planar_dist(a, b):
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def _grippers_open(task):
    return bool(task.robot.is_left_gripper_open() and task.robot.is_right_gripper_open())


def placed_beside(task, mover, reference, lo=0.08, hi=0.20, same_z=0.04):
    """True iff `mover` rests NEXT TO `reference` on the table (not stacked): planar
    distance in [lo, hi], similar height, grippers released."""
    a = mover.get_pose().p
    b = reference.get_pose().p
    d = _planar_dist(a, b)
    return bool(lo <= d <= hi and abs(a[2] - b[2]) < same_z and _grippers_open(task))


def placed_on_top(task, mover, reference, planar=0.05, min_rise=0.02):
    """True iff `mover` sits ON TOP OF `reference`: planar distance < planar (aligned
    over B) and clearly elevated above B's center, grippers released."""
    a = mover.get_pose().p
    b = reference.get_pose().p
    return bool(_planar_dist(a, b) < planar and (a[2] - b[2]) > min_rise and _grippers_open(task))
