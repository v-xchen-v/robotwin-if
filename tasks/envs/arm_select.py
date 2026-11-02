from ._base_task import Base_Task
from ._if_eval import apply_if_eval_step_limit
from ._if_grounding import ArmPickMonitor
from .utils import *
from ._GLOBAL_CONFIGS import *
import sapien
import numpy as np


class arm_select(Base_Task):
    """Lift a 5 cm cube with the instructed arm.

    Consecutive seeds share the same randomly translated/rotated scene. The
    left/right instruction selects the arm, while the oracle uses native cube
    top-down grasps. A wrong-arm lift cannot be repaired later in the episode.
    """

    CUBE_HALF = (0.025, 0.025, 0.025)
    CUBE_Z = 0.741 + CUBE_HALF[2]
    CUBE_PRE_GRASP_DIS = 0.09
    # Three equal-width strata in the shared front-center workspace.
    # Sampling depends on scene_seed, never the commanded arm.
    CUBE_X_BINS = ((-0.04, -0.04 / 3), (-0.04 / 3, 0.04 / 3), (0.04 / 3, 0.04))
    CUBE_Y_RANGE = (-0.08, -0.06)
    CUBE_YAW_LIMIT = np.deg2rad(15.0)
    GRASP_IDS = [0, 1, 2, 3]
    LIFT_Z = 0.1

    # Success thresholds (state-based).
    LIFT_THRESH = ArmPickMonitor.LIFT_THRESH  # box center must rise strictly above this (m)
    # Attribute the lifted cube to the closer TCP within this distance.
    NEAR_TCP = ArmPickMonitor.NEAR_TCP

    # IF wiring: mode derives from the SEED so one collection run yields BOTH arms
    # with a pixel-identical paired scene. ARM_OVERRIDE forces one arm for the
    # spike/sweep harnesses only; leave None for real collection/eval.
    ARM_OVERRIDE = None
    # Layer-B / spike hook: force the EXECUTING arm to differ from the commanded
    # arm (self.mode). arm_match still scores against self.mode, so a wrong-arm
    # grasp must fail even though the box lifts. None -> execute with self.mode.
    ORACLE_ARM = None

    def setup_demo(self, **kwags):
        if "arm_select_scene_version" in kwags:
            raise ValueError("arm_select_scene_version is retired; use demo_clean_arm_select")
        self._detach_pick_observer()
        self._pick_monitor = None
        # Capture the seed so mode/scene derive purely from it (IF wiring).
        self._seed = kwags.get("seed", 0)
        self.box_half_size = self.CUBE_HALF
        self.box_spawn_z = self.CUBE_Z
        self.box_type = "default"
        self.pre_grasp_dis = self.CUBE_PRE_GRASP_DIS
        super()._init_task_env_(**kwags)
        apply_if_eval_step_limit(self)
        # Policy evaluation starts after setup_demo without calling play_once.
        # Capture the settled initial height for both oracle and policy paths.
        self._init_box_z = float(self.box.get_pose().p[2])
        self.info["arm_select_scene"] = dict(self._scene_spec)
        self._pick_monitor = ArmPickMonitor(self.mode, self.LIFT_THRESH, self.NEAR_TCP)
        self._attach_pick_observer()

    def _observe_pick(self):
        if self._pick_monitor is not None:
            _, _, lift_delta, d_cmd, d_other = self._compute_signals()
            self._pick_monitor.observe(lift_delta, d_cmd, d_other,
                                       getattr(self, "take_action_cnt", 0))

    def _attach_pick_observer(self):
        scene = self.scene
        original_step = scene.step

        def observed_step():
            result = original_step()
            self._observe_pick()
            return result

        self._pick_observer = (scene, original_step, observed_step)
        scene.step = observed_step

    def _detach_pick_observer(self):
        observer = getattr(self, "_pick_observer", None)
        if observer is not None:
            scene, original_step, observed_step = observer
            if scene.step is observed_step:
                scene.step = original_step
            self._pick_observer = None

    def close_env(self, clear_cache=False):
        self._detach_pick_observer()
        return super().close_env(clear_cache=clear_cache)

    @classmethod
    def scene_pose(cls, scene_seed):
        """Mode-independent sampling; preserve draw order and global RNG state."""
        rng = np.random.RandomState(scene_seed)
        stratum = scene_seed % len(cls.CUBE_X_BINS)
        return (float(rng.uniform(*cls.CUBE_X_BINS[stratum])),
                float(rng.uniform(*cls.CUBE_Y_RANGE)),
                float(rng.uniform(-cls.CUBE_YAW_LIMIT, cls.CUBE_YAW_LIMIT)),
                ("left", "center", "right")[stratum])

    def load_actors(self):
        # Scene depends only on seed//2 (a pair shares one scene); mode from
        # seed%2. Re-seed with scene_seed to override _init_task_env_'s raw-seed
        # seeding. The pose sampler never receives the commanded arm.
        # ARM_OVERRIDE forces the mode (harness/testing only).
        scene_seed = self._seed // 2
        np.random.seed(scene_seed)
        self.mode = self.ARM_OVERRIDE if self.ARM_OVERRIDE in ("left", "right") \
            else ["left", "right"][self._seed % 2]

        x, y, yaw, region = self.scene_pose(scene_seed)
        quat = [float(np.cos(yaw / 2)), 0, 0, float(np.sin(yaw / 2))]
        self._scene_spec = {"scene_seed": scene_seed,
                            "region": region, "position": [x, y, self.box_spawn_z],
                            "quaternion": quat, "yaw_degrees": float(np.rad2deg(yaw)),
                            "half_size": list(self.box_half_size),
                            "boxtype": self.box_type, "oracle_grasp": "top-down"}
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
        # Keep the settled setup baseline and any earlier wrong-arm history.
        # The commanded arm -- NOT geometry-derived. This is the whole point of
        # the task: the instruction word decides the arm.
        arm_tag = ArmTag(self.mode)
        self.arm_tag = arm_tag
        # The arm that actually executes; equals the commanded arm unless a
        # counter-example harness forces the wrong one (ORACLE_ARM).
        exec_tag = ArmTag(self.ORACLE_ARM) if self.ORACLE_ARM in ("left", "right") else arm_tag

        # Use the native cube top-down grasp frames.
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
        self.info["signals"] = sig
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
        """Report current execution signals and irreversible wrong-arm history."""
        self._observe_pick()
        return self._pick_monitor.signals()

    def check_success(self):
        if self._pick_monitor is None:
            return False
        self._observe_pick()
        return bool(self._pick_monitor.success)
