import json
import re
from pathlib import Path

from ._base_task import Base_Task
from .utils import *
from ._GLOBAL_CONFIGS import *


class operate_tabletop(Base_Task):
    """Operate-Tabletop IF task: three-way verb-and-target discrimination.

    Same scene every episode (bell + stapler + 1-2 graspable objects). The
    instruction verb selects one of three modes:
      - click : touch the bell's top center   (reuses click_bell)
      - press : press the stapler in place     (reuses press_stapler)
      - pick  : pick up the ONE named object   (reuses adjust_bottle's single-arm
                grasp+lift + put_object_cabinet's pooled-graspable pattern)

    Routing (see operate_tabletop.json schema): each mode fills exactly one
    non-arm placeholder — {A}=bell, {B}=stapler, {C}=picked object — so the
    native filter_instructions routes 3-way by placeholder-set alone, unchanged.

    check_success is target-specific per mode (a wrong action fails the mode's
    own condition); this mirrors operate_stapler. Reason: contact/lift thresholds
    below are typed to RoboTwin's native click_bell / press_stapler / put_object_
    cabinet checks —论文未确认，类推自原生任务.
    """

    # Graspable, desk-appropriate objects for the "pick" branch (and graspable
    # distractors in click/press modes). Each has a default authored grasp pose
    # (RoboTwin's put_object_cabinet grasps these) AND >=1 "stable" model_id that
    # rests flat under the glb resting qpos. 048_stapler is excluded on purpose —
    # it is the press target, never a pick candidate.
    GRASPABLE_NAMES = [
        "047_mouse",
        "057_toycar",
        "073_rubikscube",
        "077_phone",
        "081_playingcards",
        "107_soap",
        "112_tea-box",
        "113_coffee-box",
        "075_bread",
    ]
    _valid_ids_cache = {}

    @classmethod
    def _valid_model_ids(cls, modelname):
        # Ids that (a) are marked "stable" in model_data{N}.json (rest flat under
        # the glb resting qpos), (b) have a mesh, AND (c) have a matching
        # objects_description/{name}/base{N}.json — without (c), replace_placeholders
        # in description-gen hard-exits when {C} resolves this object.
        if modelname not in cls._valid_ids_cache:
            d = Path("assets/objects") / modelname
            desc = Path("description/objects_description") / modelname
            ids = []
            for p in d.glob("model_data*.json"):
                m = re.search(r"model_data(\d+)\.json", p.name)
                if m is None:
                    continue
                n = int(m.group(1))
                try:
                    cfg = json.load(open(p))
                except Exception:
                    continue
                if not cfg.get("stable", False):
                    continue
                mesh_ok = (any((d / sub / f"base{n}.glb").exists() for sub in ("collision", "visual"))
                           or (d / f"base{n}.glb").exists() or (d / f"textured{n}.obj").exists())
                if mesh_ok and (desc / f"base{n}.json").exists():
                    ids.append(n)
            cls._valid_ids_cache[modelname] = sorted(ids)
        return cls._valid_ids_cache[modelname]

    def setup_demo(self, **kwags):
        # Capture seed so mode is derived purely from it (see load_actors): eval
        # calls setup_demo twice with the same seed (expert-check + policy-rollout),
        # and both must produce the same instruction+grader. Deriving mode from the
        # seed (not RNG draw order) makes that reproducible.
        self._seed = kwags.get("seed", 0)
        super()._init_task_env_(**kwags)

    # ---- placement helper ----------------------------------------------------
    def _sample_pose(self, occupied, xlim, ylim, qpos, rotate_rand=False,
                     rotate_lim=(0, 0, 0), center_gap=0.0, min_sep=0.13):
        # Rejection-sample a rand_pose keeping |x| >= center_gap (avoid the arm
        # base column) and >= min_sep from every already-placed object.
        for _ in range(80):
            cand = rand_pose(xlim=list(xlim), ylim=list(ylim), qpos=list(qpos),
                             rotate_rand=rotate_rand, rotate_lim=list(rotate_lim))
            if center_gap and abs(cand.p[0]) < center_gap:
                continue
            if all(np.hypot(cand.p[0] - o[0], cand.p[1] - o[1]) > min_sep for o in occupied):
                return cand
        return None  # caller decides how to handle a crowded table

    def load_actors(self):
        self.mode = ["click", "press", "pick"][self._seed % 3]
        occupied = []

        # --- bell (static in every mode; click target) ---
        bell_pose = self._sample_pose(occupied, xlim=[-0.25, 0.25], ylim=[-0.2, 0.0],
                                      qpos=[0.5, 0.5, 0.5, 0.5], center_gap=0.05)
        self.bell_id = int(np.random.choice([0, 1]))
        self.bell = create_actor(self, pose=bell_pose, modelname="050_bell", convex=True,
                                 model_id=self.bell_id, is_static=True)
        occupied.append(bell_pose.p[:2])
        self.add_prohibit_area(self.bell, padding=0.07)
        # click_bell requires the acting gripper to be closed at the bell top.
        self.check_arm_function = (self.is_left_gripper_close
                                   if self.bell.get_pose().p[0] < 0 else self.is_right_gripper_close)

        # --- stapler (static in every mode; press target) ---
        stapler_pose = self._sample_pose(occupied, xlim=[-0.25, 0.25], ylim=[-0.2, 0.0],
                                         qpos=[0.5, 0.5, 0.5, 0.5], rotate_rand=True,
                                         rotate_lim=[0, np.pi, 0], center_gap=0.05)
        self.stapler_id = int(np.random.choice([0, 1, 2, 3, 4, 5, 6]))
        self.stapler = create_actor(self, pose=stapler_pose, modelname="048_stapler", convex=True,
                                    model_id=self.stapler_id, is_static=True)
        occupied.append(stapler_pose.p[:2])
        self.add_prohibit_area(self.stapler, padding=0.05)

        # --- 1-2 graspable objects (dynamic; scene identical across all modes) ---
        self._load_graspables(occupied)

        # Baseline height for the pick lift-check, captured at setup (eval never
        # calls play_once, so this cannot live there). Let physics settle first.
        self.delay(2)
        if self.mode == "pick":
            self.target = self.graspables[0]
            self.target_modelname = self.graspable_names[0]
            self.target_id = self.graspable_ids[0]
            self.target_origin_z = float(self.target.get_pose().p[2])

    def _load_graspables(self, occupied):
        num = int(np.random.choice([1, 2]))
        names = list(self.GRASPABLE_NAMES)
        np.random.shuffle(names)
        self.graspables = []
        self.graspable_names = []
        self.graspable_ids = []
        for name in names:
            if len(self.graspables) >= num:
                break
            valid_ids = self._valid_model_ids(name)
            if not valid_ids:
                continue
            model_id = int(np.random.choice(valid_ids))
            pose = self._sample_pose(occupied, xlim=[-0.25, 0.25], ylim=[-0.2, 0.05],
                                     # Canonical glb resting orientation (90deg about x
                                     # lays the authored up-axis flat) + random yaw; valid
                                     # only for "stable" ids, which _valid_model_ids enforces.
                                     qpos=[0.707107, 0.707107, 0, 0], rotate_rand=True,
                                     rotate_lim=[0, np.pi, 0], center_gap=0.0)
            if pose is None:
                continue
            actor = create_actor(self, pose=pose, modelname=name, convex=True,
                                 model_id=model_id, is_static=False)
            if actor is None:
                continue
            occupied.append(pose.p[:2])
            # Some assets ship model_data without a "scale" key -> actor.config is None;
            # add_prohibit_area reads config, so fall back to a pose-based keep-out box.
            self.add_prohibit_area(actor if actor.config is not None else actor.get_pose(), padding=0.05)
            self.graspables.append(actor)
            self.graspable_names.append(name)
            self.graspable_ids.append(model_id)

        # The pick branch needs at least one graspable target; retry-friendly setups
        # in RoboTwin raise on unsatisfiable scenes rather than silently degrading.
        if self.mode == "pick" and not self.graspables:
            raise UnStableError("operate_tabletop: no graspable object could be placed for pick mode")

    def play_once(self):
        # Top-level info keys (NOT info["info"], the placeholder set) so the reporter
        # can split success by mode / scene composition without extra logging.
        self.info["mode"] = self.mode
        self.info["objects"] = [f"{n}/base{i}" for n, i in zip(self.graspable_names, self.graspable_ids)]

        if self.mode == "click":
            arm_tag = ArmTag("right" if self.bell.get_pose().p[0] > 0 else "left")
            # Touch the bell top center and click (reuses click_bell).
            self.move(self.grasp_actor(self.bell, arm_tag=arm_tag, pre_grasp_dis=0.1,
                                       grasp_dis=0.1, contact_point_id=0))
            self.move(self.move_by_displacement(arm_tag, z=-0.045))
            self.check_success()
            self.move(self.move_by_displacement(arm_tag, z=0.045))
            self.check_success()
            self.info["info"] = {"{A}": f"050_bell/base{self.bell_id}", "{a}": str(arm_tag)}

        elif self.mode == "press":
            arm_tag = ArmTag("left" if self.stapler.get_pose().p[0] < 0 else "right")
            # Press the stapler head down (reuses press_stapler).
            self.move(self.grasp_actor(self.stapler, arm_tag=arm_tag, pre_grasp_dis=0.1,
                                       grasp_dis=0.1, contact_point_id=2))
            self.move(self.close_gripper(arm_tag=arm_tag))
            self.move(self.grasp_actor(self.stapler, arm_tag=arm_tag, pre_grasp_dis=0.02,
                                       grasp_dis=0.02, contact_point_id=2))
            self.info["info"] = {"{B}": f"048_stapler/base{self.stapler_id}", "{a}": str(arm_tag)}

        else:  # pick
            arm_tag = ArmTag("right" if self.target.get_pose().p[0] > 0 else "left")
            # Grasp the named object and lift it clear of the table (reuses the
            # put_object_cabinet grasp+lift; we stop after the lift, still holding).
            self.move(self.grasp_actor(self.target, arm_tag=arm_tag, pre_grasp_dis=0.1))
            self.move(self.move_by_displacement(arm_tag, z=0.1, move_axis="arm"))
            self.info["info"] = {"{C}": f"{self.target_modelname}/base{self.target_id}", "{a}": str(arm_tag)}

        return self.info

    def check_success(self):
        if self.mode == "click":
            if self.stage_success_tag:
                return True
            if not self.check_arm_function():
                return False
            bell_pose = self.bell.get_contact_point(0)[:3]
            positions = self.get_gripper_actor_contact_position("050_bell")
            eps = [0.025, 0.025]
            for position in positions:
                if (np.all(np.abs(position[:2] - bell_pose[:2]) < eps) and abs(position[2] - bell_pose[2]) < 0.03):
                    self.stage_success_tag = True
                    return True
            return False

        if self.mode == "press":
            if self.stage_success_tag:
                return True
            stapler_pose = self.stapler.get_contact_point(2)[:3]
            positions = self.get_gripper_actor_contact_position("048_stapler")
            eps = [0.03, 0.03]
            for position in positions:
                if (np.all(np.abs(position[:2] - stapler_pose[:2]) < eps) and abs(position[2] - stapler_pose[2]) < 0.03):
                    self.stage_success_tag = True
                    return True
            return False

        # pick: the NAMED object is lifted clear of the table AND still held by a
        # gripper. Lifting a distractor (or clicking/pressing) leaves the target at
        # rest -> False, which is what the IF benchmark tests.
        target_z = float(self.target.get_pose().p[2])
        lifted = (target_z - self.target_origin_z) > 0.02
        held = len(self.get_gripper_actor_contact_position(self.target_modelname)) > 0
        return bool(lifted and held)
