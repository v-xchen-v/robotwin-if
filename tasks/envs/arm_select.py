from ._base_task import Base_Task
from ._if_eval import apply_if_eval_step_limit
from .utils import *
from ._GLOBAL_CONFIGS import *
import sapien
import numpy as np


class arm_select(Base_Task):
    """IF-Arm-Select: the instruction names which arm (left vs right) grasps a
    center box; the arm word is the ONLY signal.

    By default the box sits at a FIXED center pose (x=0, axis-aligned), so geometry does not
    leak which arm to use -- native handover_block chooses the arm by box x-sign
    (``ArmTag("left" if x<0 else "right")``, the "convenient hand" prior); pinning
    x=0 puts that prior exactly on its decision boundary and the instruction has
    to override it. Legacy fixed-v1 / jitter-v2 use handover_block's tall block
    with side grasps. cube-v3 uses the native stack_blocks_three 5 cm cube and
    top-down grasp frames to reduce execution difficulty. Native oracle
    feasibility alone does not establish policy grasp reliability.

    IF wiring mirrors laptop_verb / grasp_cube_approach:
        scene_seed = seed // 2      # identical for the consecutive pair (2k, 2k+1)
        mode       = ["left","right"][seed % 2]
    The optional arm_select_scene_version="jitter-v2" config varies xy/yaw
    between pairs in the central workspace. Both modes still share exactly the
    same scene. Qualify BOTH arms before retaining a complete block; a position
    must never determine the commanded arm. cube-v3 samples a front-center
    workspace suitable for top-down grasps, with its own xy/yaw bounds. Each
    version requires its own config and qualified seed manifest.

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
    SCENE_VERSIONS = ("fixed-v1", "jitter-v2", "cube-v3")
    # Match native stack_blocks_three geometry and its top-down approach.
    CUBE_HALF = (0.025, 0.025, 0.025)
    CUBE_Z = 0.741 + CUBE_HALF[2]
    CUBE_PRE_GRASP_DIS = 0.09
    # Top-down grasps need a different shared workspace from the tall block's
    # side grasps. Strata depend on scene_seed, never the commanded arm.
    CUBE_X_BINS = ((-0.04, -0.04 / 3), (-0.04 / 3, 0.04 / 3), (0.04 / 3, 0.04))
    CUBE_Y_RANGE = (-0.08, -0.06)
    CUBE_YAW_LIMIT = np.deg2rad(15.0)
    # Three equal-width x strata, cycled by scene seed (never by arm/mode).
    # These are candidate ranges; a complete-block oracle probe qualifies them.
    V2_X_BINS = ((-0.02, -0.02 / 3), (-0.02 / 3, 0.02 / 3), (0.02 / 3, 0.02))
    V2_Y_RANGE = (0.10, 0.12)
    V2_YAW_LIMIT = np.deg2rad(3.0)
    # The "long" boxtype ships 8 side grasps: ids [0,1,2,3] = front/right/left/back
    # at the upper height, [4,5,6,7] the same at the lower height. Both arms use
    # the upper set. For a default cube, ids 0..3 instead describe four
    # top-down wrist orientations; no side grasp frames are supplied.
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
        self.scene_version = kwags.pop("arm_select_scene_version", "fixed-v1")
        if self.scene_version not in self.SCENE_VERSIONS:
            raise ValueError(f"Unknown arm_select_scene_version: {self.scene_version!r}")
        cube = self.scene_version == "cube-v3"
        self.box_half_size = self.CUBE_HALF if cube else self.BOX_HALF
        self.box_spawn_z = self.CUBE_Z if cube else self.BOX_Z
        self.box_type = "default" if cube else "long"
        self.pre_grasp_dis = self.CUBE_PRE_GRASP_DIS if cube else self.PRE_GRASP_DIS
        super()._init_task_env_(**kwags)
        apply_if_eval_step_limit(self)
        # Policy evaluation starts after setup_demo without calling play_once.
        # Capture the settled initial height for both oracle and policy paths.
        self._init_box_z = float(self.box.get_pose().p[2])
        self.info["arm_select_scene"] = dict(self._scene_spec)

    @classmethod
    def scene_pose(cls, scene_seed, version):
        """Pure, mode-independent scene sampling; leave global RNG untouched."""
        if version == "fixed-v1":
            return (*cls.FIXED_XY, 0.0, "center")
        if version not in ("jitter-v2", "cube-v3"):
            raise ValueError(f"Unknown arm_select_scene_version: {version!r}")
        rng = np.random.RandomState(scene_seed)
        cube = version == "cube-v3"
        x_bins = cls.CUBE_X_BINS if cube else cls.V2_X_BINS
        y_range = cls.CUBE_Y_RANGE if cube else cls.V2_Y_RANGE
        yaw_limit = cls.CUBE_YAW_LIMIT if cube else cls.V2_YAW_LIMIT
        stratum = scene_seed % len(x_bins)
        return (float(rng.uniform(*x_bins[stratum])),
                float(rng.uniform(*y_range)),
                float(rng.uniform(-yaw_limit, yaw_limit)),
                ("left", "center", "right")[stratum])

    def load_actors(self):
        # Scene depends only on seed//2 (a pair shares one scene); mode from
        # seed%2. Re-seed with scene_seed to override _init_task_env_'s raw-seed
        # seeding. The versioned pose sampler never receives the commanded arm.
        # ARM_OVERRIDE forces the mode (harness/testing only).
        scene_seed = self._seed // 2
        np.random.seed(scene_seed)
        self.mode = self.ARM_OVERRIDE if self.ARM_OVERRIDE in ("left", "right") \
            else ["left", "right"][self._seed % 2]

        x, y, yaw, region = self.scene_pose(scene_seed, self.scene_version)
        quat = [float(np.cos(yaw / 2)), 0, 0, float(np.sin(yaw / 2))]
        self._scene_spec = {"version": self.scene_version, "scene_seed": scene_seed,
                            "region": region, "position": [x, y, self.box_spawn_z],
                            "quaternion": quat, "yaw_degrees": float(np.rad2deg(yaw))}
        if self.scene_version == "cube-v3":
            self._scene_spec.update(half_size=list(self.box_half_size),
                                    boxtype=self.box_type, oracle_grasp="top-down")
        self.box = create_box(
            scene=self,
            pose=sapien.Pose([x, y, self.box_spawn_z], quat),
            half_size=self.box_half_size,
            color=(1, 0, 0),
            name="box",
            boxtype=self.box_type,
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

        # Use the version's native grasp frames: legacy side / cube top-down.
        self.move(
            self.grasp_actor(
                self.box,
                arm_tag=exec_tag,
                pre_grasp_dis=self.pre_grasp_dis,
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
