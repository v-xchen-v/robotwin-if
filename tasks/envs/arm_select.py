from ._base_task import Base_Task
from ._if_eval import apply_if_eval_step_limit
from .utils import *
from ._GLOBAL_CONFIGS import *
import sapien
import numpy as np


class arm_select(Base_Task):
    """IF-Arm-Select: the instruction names which arm (left vs right) grasps a
    center box; the arm word is the ONLY signal.

    The box sits at a FIXED center pose (x=0, axis-aligned), so geometry does not
    leak which arm to use -- native handover_block chooses the arm by box x-sign
    (``ArmTag("left" if x<0 else "right")``, the "convenient hand" prior); pinning
    x=0 puts that prior exactly on its decision boundary and the instruction has
    to override it. The reused box is handover_block's proven both-arm-graspable
    ``boxtype="long"`` block (choose_grasp_pose picks a reachable side face per
    arm), so both left and right grasps are in the native repertoire -- this task
    is NOT action-OOD (unlike close-laptop), so it stays clean under
    zeroshot / native-ft.

    IF wiring mirrors laptop_verb / grasp_cube_approach:
        scene_seed = seed // 2      # identical for the consecutive pair (2k, 2k+1)
        mode       = ["left","right"][seed % 2]
    The box is fully fixed, so a pair (2k, 2k+1) is pixel-identical and the ONLY
    difference the policy sees is the commanded arm word ({a}).

    Success is STATE-BASED (invariant 3): policy eval cannot trust the oracle's
    ArmTag, so we infer the executing arm from the end state -- the box must be
    lifted AND end near the COMMANDED arm's TCP (and strictly nearer it than the
    idle arm's TCP). An oracle that grasps with the wrong arm therefore fails even
    though the box is lifted (Layer-B counter-example).
    """

    # Reused handover_block box: tall block, both arms proven to grasp it.
    BOX_HALF = (0.03, 0.03, 0.1)
    BOX_Z = 0.842                    # sits on the table (top ~0.741 + half-z 0.1)
    # x=0 -> the arm-choice decision boundary (geometry can't leak the answer).
    # y=0.10 is inside handover_block's proven grasp band ylim=[0,0.25]; a probe
    # over x=0 x {both arms} x heights found both arms grasp reliably here (a
    # near-robot y like -0.05 was the original reach failure, not x=0 itself).
    FIXED_XY = (0.0, 0.10)
    # The "long" boxtype ships 8 side grasps: ids [0,1,2,3] = front/right/left/back
    # at the upper height, [4,5,6,7] the same at the lower height. Both arms use
    # the upper set; choose_grasp_pose picks each arm's reachable face.
    GRASP_IDS = [0, 1, 2, 3]
    PRE_GRASP_DIS = 0.07
    LIFT_Z = 0.1

    # Success thresholds (state-based).
    LIFT_THRESH = 0.05              # box center must rise at least this much (m)
    # The "long" box is tall: a side grasp holds it near the top, so even a clean
    # grasp leaves the box CENTER ~0.14m from the TCP (measured). NEAR_TCP just
    # rules out "no arm holds it" (box knocked away / idle arm at origin ~0.56m);
    # the real arm-identity signal is d_cmd < d_other, which has a huge margin.
    NEAR_TCP = 0.20                 # box must end within this of the commanded TCP

    # IF wiring: mode derives from the SEED so one collection run yields BOTH arms
    # with a pixel-identical paired scene. ARM_OVERRIDE forces one arm for the
    # spike/sweep harnesses only; leave None for real collection/eval.
    ARM_OVERRIDE = None
    # Layer-B / spike hook: force the EXECUTING arm to differ from the commanded
    # arm (self.mode). arm_match still scores against self.mode, so a wrong-arm
    # grasp must fail even though the box lifts. None -> execute with self.mode.
    ORACLE_ARM = None

    def setup_demo(self, **kwags):
        # Capture the seed so mode/scene derive purely from it (IF wiring).
        self._seed = kwags.get("seed", 0)
        super()._init_task_env_(**kwags)
        apply_if_eval_step_limit(self)
        # Policy evaluation starts after setup_demo without calling play_once.
        # Capture the settled initial height for both oracle and policy paths.
        self._init_box_z = float(self.box.get_pose().p[2])

    def load_actors(self):
        # Scene depends only on seed//2 (a pair shares one scene); mode from
        # seed%2. Re-seed with scene_seed to override _init_task_env_'s raw-seed
        # seeding. The box pose is fixed, so every scene is identical -- the pair
        # (2k, 2k+1) differs only in the commanded arm. ARM_OVERRIDE forces the
        # mode (harness/testing only).
        scene_seed = self._seed // 2
        np.random.seed(scene_seed)
        self.mode = self.ARM_OVERRIDE if self.ARM_OVERRIDE in ("left", "right") \
            else ["left", "right"][self._seed % 2]

        x, y = self.FIXED_XY
        self.box = create_box(
            scene=self,
            pose=sapien.Pose([x, y, self.BOX_Z], [1, 0, 0, 0]),
            half_size=self.BOX_HALF,
            color=(1, 0, 0),
            name="box",
            boxtype="long",
        )
        self.add_prohibit_area(self.box, padding=0.1)
        self._init_box_z = None

    def play_once(self):
        self._init_box_z = float(self.box.get_pose().p[2])
        # The commanded arm -- NOT geometry-derived. This is the whole point of
        # the task: the instruction word decides the arm.
        arm_tag = ArmTag(self.mode)
        self.arm_tag = arm_tag
        # The arm that actually executes; equals the commanded arm unless a
        # counter-example harness forces the wrong one (ORACLE_ARM).
        exec_tag = ArmTag(self.ORACLE_ARM) if self.ORACLE_ARM in ("left", "right") else arm_tag

        # Grasp the box with the executing arm; the planner picks its reachable
        # side face out of the upper set.
        self.move(
            self.grasp_actor(
                self.box,
                arm_tag=exec_tag,
                pre_grasp_dis=self.PRE_GRASP_DIS,
                grasp_dis=0.0,
                contact_point_id=self.GRASP_IDS,
            ))
        # Lift straight up.
        self.move(self.move_by_displacement(exec_tag, z=self.LIFT_Z))

        sig = self.eval_signals()
        self.info["mode"] = self.mode
        # info["info"] must contain only instruction-template placeholders.
        # Extra diagnostic keys make RoboTwin reject every template because its
        # renderer requires an exact placeholder/parameter match.
        self.info["info"] = {
            "{A}": "the block",
            "{a}": str(arm_tag),
        }
        self.info["signals"] = {
            "arm_match": sig["arm_match"],
            "lifted": sig["lifted"],
        }
        return self.info

    def _tcp_xyz(self, arm_tag):
        return np.array(self.get_arm_pose(arm_tag)[:3], dtype=np.float64)

    def _compute_signals(self):
        """Two decoupled signals behind the metric:
          - arm_match = did the box end held by the COMMANDED arm -- i.e. within
            NEAR_TCP of that arm's TCP AND strictly nearer it than the idle arm's
            TCP. This is the instruction-following signal, readable from the end
            state alone (no reliance on the oracle's ArmTag).
          - lifted = did the box leave the table. This is the execution signal.
        Returned separately so eval can report each + the left-vs-right gap
        instead of collapsing them into one binary (keeps a 0 attributable).
        """
        box_xyz = np.array(self.box.get_pose().p, dtype=np.float64)
        base_z = self._init_box_z if self._init_box_z is not None else box_xyz[2]
        lift_delta = box_xyz[2] - base_z
        lifted = lift_delta > self.LIFT_THRESH

        cmd = ArmTag(self.mode)
        d_cmd = float(np.linalg.norm(box_xyz - self._tcp_xyz(cmd)))
        d_other = float(np.linalg.norm(box_xyz - self._tcp_xyz(cmd.opposite)))
        arm_match = (d_cmd < self.NEAR_TCP) and (d_cmd < d_other)
        return lifted, arm_match, lift_delta, d_cmd, d_other

    def eval_signals(self):
        """Split/directional metric for policy eval: report arm_match (the IF
        signal) and lifted (execution) separately, plus the distances -- NOT the
        AND. Collection still gates on both via check_success."""
        lifted, arm_match, lift_delta, d_cmd, d_other = self._compute_signals()
        return {
            "arm": self.mode,
            "arm_match": bool(arm_match),
            "lifted": bool(lifted),
            "lift_delta": lift_delta,
            "dist_cmd_tcp": d_cmd,
            "dist_other_tcp": d_other,
        }

    def check_success(self):
        # Strict AND: a *collectable demo* must use the commanded arm AND lift the
        # box. Eval should prefer eval_signals() (split metric).
        if self._init_box_z is None:
            return False
        lifted, arm_match, _, _, _ = self._compute_signals()
        return bool(lifted and arm_match)
