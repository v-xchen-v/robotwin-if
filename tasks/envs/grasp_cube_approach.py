from ._base_task import Base_Task
from ._if_eval import apply_if_eval_step_limit
from .utils import *
from ._GLOBAL_CONFIGS import *
import sapien
import numpy as np
import transforms3d as t3d


class grasp_cube_approach(Base_Task):
    """IF-Grasp-Approach spike: grasp one cube from the top vs from the side.

    Same object, same initial pose -- the only thing that changes is the
    commanded approach direction ("从顶部拿起" vs "从侧面拿起"). Success is
    orientation-based: the cube must be lifted AND the gripper's approach axis
    must match the commanded direction (vertical for top, horizontal for side),
    so "just lifting it" with the wrong grasp fails (Layer-B counter-example).

    Feasibility notes (why this is the spike):
      - Top grasp is trivial (gripper presses straight down).
      - Side grasp is the risk: a horizontal approach to a cube sitting on the
        table drives the lower finger toward the tabletop. Mitigation (approach
        C): the cube sits on a short *static riser* so its whole body is raised
        clear of the table; the side grasp then closes at cube-center height,
        well above the table surface.

    Contact points are injected after ``create_box`` (Actor reads them live from
    ``self.config``), so the native submodule ``create_actor.py`` is untouched:
      - ids [0,1,2,3] = top_down grasps (reused from the default box).
      - ids [4,5,6,7] = side grasps (the horizontal set create_actor ships
        commented-out for the default boxtype).
    """

    TABLE_TOP = 0.741
    CUBE_HALF = 0.025
    # Short riser: just enough to lift the cube body clear of the table for the
    # side approach, while keeping the cube center near the arm's comfortable
    # reach height (~0.79, close to native tabletop objects ~0.76). Taller
    # risers (0.04+) push top-down grasps toward the workspace ceiling and the
    # motion planner starts failing -- that, not table clipping, was the initial
    # bottleneck. Side clearance below the cube = 2*RISER_HALF[2] (~0.024m).
    RISER_HALF = (0.02, 0.02, 0.012)

    TOP_IDS = [0, 1, 2, 3]
    SIDE_IDS = [4, 5, 6, 7]

    # Success thresholds.
    LIFT_THRESH = 0.05          # cube center must rise at least this much (m)
    VERT_COS = 0.7              # |approach_z| >= this  -> vertical (top) grasp
    HORIZ_COS = 0.3             # |approach_z| <= this  -> horizontal (side) grasp

    # IF wiring: the approach (mode) is derived from the SEED so one collection
    # run yields BOTH modes and the same scene is paired across them --
    #     scene_seed = seed // 2 ; mode = ["top","side"][seed % 2]
    # (mirrors laptop_verb). APPROACH here is an OVERRIDE for the spike/sweep
    # harnesses only (force one mode regardless of seed); leave it None for real
    # collection/eval so the seed drives the mode.
    APPROACH = None
    ORACLE_IDS = None           # None -> use the group matching the active mode

    # {D} approach-phrase pools -- the ONLY instruction signal of top vs side.
    # Picked deterministically from scene_seed so the instruction reproduces
    # across eval's paired setup passes (mirrors laptop_verb's {V} pools).
    TOP_PHRASES = ["from the top", "from above"]
    SIDE_PHRASES = ["from the side"]

    # The design spec fixes the cube at one central pose (only the instruction
    # word varies), so the shipped task runs with jitter OFF -- this is also the
    # config the locked SIDE_FACE=6 was verified at (side 100% / top 100%).
    # POSE_JITTER=True is a spike-only knob to measure the reachability basin;
    # note face 6 is tied to the fixed x=0/right-arm geometry and is NOT valid
    # under jitter (x flips the arm), so only sweep faces with jitter off.
    POSE_JITTER = False
    FIXED_XY = (0.0, -0.05)      # front-center, axis-aligned when jitter is off

    # Side-grasp reachability levers (swept by tests/grasp_cube_approach/sweep_side.py to
    # push the horizontal grasp from ~73% toward ~90%). All failures are
    # plan=False, so the goal is to land the grasp target inside the arm's
    # comfortable IK envelope.
    #   SIDE_FACE=None lets choose_grasp_pose pick the best-reachable of all four
    #   side faces; setting it to a single id in {4,5,6,7} forces that one face.
    # Per-face sweep at the fixed pose (x=0 -> right arm): face 6 (left) reaches
    # 100%, face 4 (front) ~87%, faces 5/7 (right/back) are 0% (out of the arm's
    # horizontal IK envelope). Auto-pick sat at ~73% because it sometimes chose
    # an unreachable face -- so we LOCK the reliable face 6. This is tied to the
    # fixed central pose + right arm; revisit if the pose or arm changes.
    SIDE_FACE = 6
    PRE_GRASP_DIS = 0.08
    LIFT_Z = 0.12

    # Top-down grasp frames (local), reused from the default box.
    _TOP_CONTACTS = [
        [[0, 0, 1, 0], [1, 0, 0, 0], [0, 1, 0, 0.0], [0, 0, 0, 1]],    # top_down(front)
        [[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0.0], [0, 0, 0, 1]],   # top_down(right)
        [[-1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0.0], [0, 0, 0, 1]],   # top_down(left)
        [[0, 0, -1, 0], [-1, 0, 0, 0], [0, 1, 0, 0.0], [0, 0, 0, 1]],  # top_down(back)
    ]
    # Side (horizontal-approach) grasp frames, contacting the cube at its center
    # height. These are the four the default boxtype ships commented-out.
    _SIDE_CONTACTS = [
        [[0, 0, 1, 0], [0, -1, 0, 0], [1, 0, 0, 0.0], [0, 0, 0, 1]],   # front
        [[0, -1, 0, 0], [0, 0, -1, 0], [1, 0, 0, 0.0], [0, 0, 0, 1]],  # right
        [[0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0.0], [0, 0, 0, 1]],    # left
        [[0, 0, -1, 0], [0, 1, 0, 0], [1, 0, 0, 0.0], [0, 0, 0, 1]],   # back
    ]

    def setup_demo(self, is_test=False, **kwags):
        # Capture the seed so mode/scene derive purely from it (IF wiring).
        self._seed = kwags.get("seed", 0)
        super()._init_task_env_(**kwags)
        apply_if_eval_step_limit(self)

    def load_actors(self):
        # IF wiring: scene depends only on seed//2 (a pair shares one scene);
        # mode comes from seed%2. Re-seed with scene_seed to override
        # _init_task_env_'s raw-seed seeding for the pose sampling, so paired
        # seeds (2k, 2k+1) get an identical scene under top vs side. APPROACH, if
        # set, forces the mode (harness/testing only).
        scene_seed = self._seed // 2
        np.random.seed(scene_seed)
        self.mode = self.APPROACH if self.APPROACH in ("top", "side") else ["top", "side"][self._seed % 2]

        riser_h = self.RISER_HALF[2]
        riser_z = self.TABLE_TOP + riser_h
        cube_z = self.TABLE_TOP + 2 * riser_h + self.CUBE_HALF

        # One shared xy + yaw for riser and cube. Jittered for the spike's
        # reachability basin; fixed to FIXED_XY / axis-aligned for the task.
        if self.POSE_JITTER:
            base = rand_pose(
                xlim=[-0.05, 0.05],
                ylim=[-0.1, 0.0],
                zlim=[cube_z],
                qpos=[1, 0, 0, 0],
                rotate_rand=True,
                rotate_lim=[0, 0, np.pi / 6],
            )
            x, y = float(base.p[0]), float(base.p[1])
            q = base.q
        else:
            x, y = self.FIXED_XY
            q = [1, 0, 0, 0]

        self.riser = create_box(
            scene=self,
            pose=sapien.Pose([x, y, riser_z], q),
            half_size=self.RISER_HALF,
            color=(0.4, 0.4, 0.4),
            name="riser",
            is_static=True,
        )
        self.cube = create_box(
            scene=self,
            pose=sapien.Pose([x, y, cube_z], q),
            half_size=(self.CUBE_HALF, self.CUBE_HALF, self.CUBE_HALF),
            color=(1, 0, 0),
            name="cube",
        )
        self.cube.set_mass(0.01)

        # Inject the full top+side contact set (native create_actor untouched).
        self.cube.config["contact_points_pose"] = self._TOP_CONTACTS + self._SIDE_CONTACTS
        self.cube.config["contact_points_group"] = [self.TOP_IDS, self.SIDE_IDS]
        self.cube.config["contact_points_mask"] = [True, True]

        self.add_prohibit_area(self.cube, padding=0.1)
        self.add_prohibit_area(self.riser, padding=0.05)

        self._init_cube_z = None
        self._approach_axis_z = 0.0

    def _approach_phrase(self):
        pool = self.TOP_PHRASES if self.mode == "top" else self.SIDE_PHRASES
        return pool[(self._seed // 2) % len(pool)]

    def play_once(self):
        self._init_cube_z = float(self.cube.get_pose().p[2])
        arm_tag = ArmTag("left" if self.cube.get_pose().p[0] < 0 else "right")
        self.arm_tag = arm_tag

        if self.ORACLE_IDS is not None:
            ids = self.ORACLE_IDS
        elif self.mode == "top":
            ids = self.TOP_IDS
        elif self.SIDE_FACE is not None:
            ids = [self.SIDE_FACE]
        else:
            ids = self.SIDE_IDS

        # Grasp with the chosen contact group.
        self.move(
            self.grasp_actor(
                self.cube,
                arm_tag=arm_tag,
                pre_grasp_dis=self.PRE_GRASP_DIS,
                grasp_dis=0.0,
                contact_point_id=ids,
            ))

        # Record the gripper approach axis (ee-frame x-axis, world z-component)
        # right after the grasp closes, before lifting.
        self._approach_axis_z = self._read_approach_axis_z(arm_tag)

        # Lift straight up.
        self.move(self.move_by_displacement(arm_tag, z=self.LIFT_Z))

        sig = self.eval_signals()
        self.info["mode"] = self.mode
        # info["info"] must contain ONLY the instruction template placeholders --
        # the renderer requires the template's {..} set to exactly match these
        # keys, so any extra field here filters out every template. Diagnostic
        # signals therefore live under a separate key.
        self.info["info"] = {
            # {A} is a plain string (not an object-description json path), so the
            # renderer substitutes it literally -- carry the article here ("the
            # block"), since it only auto-prepends "the" for json-path or arm
            # ({a}) values. {a}="right"/"left" renders as "the right arm".
            "{A}": "the block",
            "{a}": str(arm_tag),
            "{D}": self._approach_phrase(),
        }
        self.info["signals"] = {
            "orientation_match": sig["orientation_match"],
            "lifted": sig["lifted"],
            "approach_axis_z": round(sig["approach_axis_z"], 3),
        }
        return self.info

    def _read_approach_axis_z(self, arm_tag):
        ee = np.array(self.get_arm_pose(arm_tag), dtype=np.float64)
        R = t3d.quaternions.quat2mat(ee[3:7])
        return float(R[:, 0][2])  # gripper approach axis (ee x) world z-component

    def _compute_signals(self):
        """The two decoupled signals behind the metric (see the design review):
          - orientation_match = did the gripper's approach axis match the
            COMMANDED direction (vertical for top, horizontal for side). This is
            the instruction-following signal -- it is readable even when the
            grasp fails to lift, so a policy that oriented correctly but fumbled
            the lift is distinguishable from one that used the wrong approach.
          - lifted = did the cube leave the riser. This is the execution signal.
        Returned separately so eval can report each + the top-vs-side gap instead
        of collapsing them into one binary (which would make a 0 ambiguous under
        zeroshot / native-ft). Collection still gates on both via check_success.
        """
        cube_z = float(self.cube.get_pose().p[2])
        base_z = self._init_cube_z if self._init_cube_z is not None else cube_z
        lift_delta = cube_z - base_z
        az = abs(self._approach_axis_z)
        lifted = lift_delta > self.LIFT_THRESH
        if self.mode == "top":
            oriented = az >= self.VERT_COS
        else:
            oriented = az <= self.HORIZ_COS
        return lifted, oriented, lift_delta, az

    def eval_signals(self):
        """Split/directional metric for policy eval. Report orientation_match
        (the IF signal) and lifted (execution) separately, and the top-vs-side
        gap in orientation_match -- NOT the AND. See notes design-review."""
        lifted, oriented, lift_delta, az = self._compute_signals()
        return {
            "approach": self.mode,
            "orientation_match": bool(oriented),
            "lifted": bool(lifted),
            "approach_axis_z": az,
            "lift_delta": lift_delta,
        }

    def check_success(self):
        # Strict AND: a *collectable demo* must both use the commanded approach
        # and lift the cube. Eval should prefer eval_signals() (split metric).
        if self._init_cube_z is None:
            return False
        lifted, oriented, _, _ = self._compute_signals()
        return bool(lifted and oriented)
