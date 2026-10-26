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


class AttributePickMonitor:
    """A distractor lift permanently invalidates an Attribute-Select episode.

    Observe both objects after every physics step, including oracle moves. A pick
    uses the existing relative lift threshold; touching or nudging an object on
    the table is not a pick. Success still requires the target to be lifted now.
    """

    VERSION = "target-only-lift-v2"
    LIFT_THRESH = 0.05

    def __init__(self, initial_z, lift_thresh=LIFT_THRESH):
        self.initial_z = dict(initial_z)
        self.lift_thresh = lift_thresh
        self.lift = dict(target=0.0, distractor=0.0)
        self.peak_lift = dict(self.lift)
        self.first_lifted = None
        self.distractor_lifted_ever = False
        self.first_distractor_lift_action = None

    def observe(self, target_z, distractor_z, action_count=0):
        for name, z in (("target", target_z), ("distractor", distractor_z)):
            self.lift[name] = float(z) - self.initial_z[name]
            self.peak_lift[name] = max(self.peak_lift[name], self.lift[name])
        lifted = self.lifted
        if self.first_lifted is None and lifted is not None:
            self.first_lifted = lifted
        if self.lift["distractor"] > self.lift_thresh:
            if not self.distractor_lifted_ever:
                self.first_distractor_lift_action = int(action_count)
            self.distractor_lifted_ever = True

    @property
    def lifted(self):
        names = [name for name, lift in self.lift.items() if lift > self.lift_thresh]
        return "both" if len(names) == 2 else (names[0] if names else None)

    @property
    def success(self):
        return self.lift["target"] > self.lift_thresh and not self.distractor_lifted_ever

    def signals(self):
        return dict(checker_version=self.VERSION, thresholds={"lift_m": self.lift_thresh},
                    grasped_target=bool(self.success), lifted=self.lifted,
                    target_lifted=self.lift["target"] > self.lift_thresh,
                    distractor_lifted_ever=self.distractor_lifted_ever,
                    first_lifted=self.first_lifted,
                    first_distractor_lift_action=self.first_distractor_lift_action,
                    lift_m=dict(self.lift), peak_lift_m=dict(self.peak_lift))


class ArmPickMonitor:
    """A lift attributed to the non-commanded arm invalidates the episode.

    Keep Arm-Select's existing height and nearest-TCP definition of a grasp,
    but apply it symmetrically to both arms throughout the physical trajectory.
    """

    VERSION = "target-arm-only-lift-v2"
    LIFT_THRESH = 0.05
    NEAR_TCP = 0.20

    def __init__(self, arm, lift_thresh=LIFT_THRESH, near_tcp=NEAR_TCP):
        self.arm = arm
        self.other_arm = "right" if arm == "left" else "left"
        self.lift_thresh = lift_thresh
        self.near_tcp = near_tcp
        self.lift_delta = 0.0
        self.d_cmd = self.d_other = None
        self.arm_match = False
        self.lifted = False
        self.lifted_by = None
        self.first_lifted_arm = None
        self.wrong_arm_lifted_ever = False
        self.first_wrong_arm_lift_action = None

    def observe(self, lift_delta, d_cmd, d_other, action_count=0):
        self.lift_delta = float(lift_delta)
        self.d_cmd, self.d_other = float(d_cmd), float(d_other)
        self.lifted = self.lift_delta > self.lift_thresh
        self.arm_match = self.d_cmd < self.near_tcp and self.d_cmd < self.d_other
        other_match = self.d_other < self.near_tcp and self.d_other < self.d_cmd
        self.lifted_by = None
        if self.lifted:
            if self.arm_match:
                self.lifted_by = self.arm
            elif other_match:
                self.lifted_by = self.other_arm
                if not self.wrong_arm_lifted_ever:
                    self.first_wrong_arm_lift_action = int(action_count)
                self.wrong_arm_lifted_ever = True
        if self.first_lifted_arm is None and self.lifted_by is not None:
            self.first_lifted_arm = self.lifted_by

    @property
    def success(self):
        return self.lifted and self.arm_match and not self.wrong_arm_lifted_ever

    def signals(self):
        return dict(arm=self.arm, arm_match=self.arm_match, lifted=self.lifted,
                    lift_delta=self.lift_delta, dist_cmd_tcp=self.d_cmd,
                    dist_other_tcp=self.d_other, checker_version=self.VERSION,
                    thresholds={"lift_m": self.lift_thresh, "near_tcp_m": self.near_tcp},
                    lifted_by=self.lifted_by, first_lifted_arm=self.first_lifted_arm,
                    wrong_arm_lifted_ever=self.wrong_arm_lifted_ever,
                    first_wrong_arm_lift_action=self.first_wrong_arm_lift_action,
                    target_arm_only_success=self.success)
