"""Shared grounding check for the IF pick tasks.

The "did the robot pick the ONE named object" test is identical for
operate_tabletop's pick branch and pick_diverse_object, so it lives here to keep
the two in sync (feature-03 flagged the duplication). Thresholds are typed to
RoboTwin's native grasp+lift tasks (adjust_bottle / put_object_cabinet) —
论文未确认，类推自原生任务.
"""


def named_object_lifted_and_held(task, actor, modelname, origin_z, lift_thresh=0.02):
    """True iff `actor` (the instruction's named target) is lifted clear of the
    table AND still held by a gripper.

    Lifting a distractor (or doing nothing) leaves the target at rest -> False,
    which is exactly what the target-object grounding test requires.

    - task:      the Base_Task instance (for get_gripper_actor_contact_position)
    - actor:     the target Actor
    - modelname: the target's modelname, e.g. "021_cup" (contact lookup key)
    - origin_z:  the target's resting z captured at setup, before manipulation
    """
    z = float(actor.get_pose().p[2])
    lifted = (z - origin_z) > lift_thresh
    held = len(task.get_gripper_actor_contact_position(modelname)) > 0
    return bool(lifted and held)
