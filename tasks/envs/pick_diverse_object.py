import numpy as np
import sapien.core as sapien
import transforms3d as t3d

from ._base_task import Base_Task
from ._if_grounding import named_object_lifted_and_held
from .utils import *
from ._GLOBAL_CONFIGS import *


class pick_diverse_object(Base_Task):
    """Pick-Diverse-Object IF task: target-object grounding by color + noun.

    Four objects are sampled from a 12-category pool; the instruction names ONE
    of them by "{color} {noun}" (e.g. "the red cup") and the robot must lift that
    one, single-arm, among three distractors. Tests whether the policy grounds
    BOTH attributes: the scene is always built so that neither color nor noun
    alone disambiguates the target (see load_actors).

    Pool + colors are self-designed (the paper gives no 12-item list) and the
    colors were eyeball-verified against the real baseColor textures — see
    docs/features/04-Pick-Diverse-Object.md for the locked table.

    check_success reuses named_object_lifted_and_held (shared with
    operate_tabletop's pick branch): the named target lifted clear of the table
    AND still held. Lifting a distractor leaves the target at rest -> False.
    Lift threshold 0.02 类推自 operate_tabletop / adjust_bottle，论文未确认.
    """

    # Locked pool: noun -> list of (obj, model_id, color). Mirrors the doc table.
    # TARGET variants (bottle/cup/shoe, grasped by the oracle) must have grasp
    # annotations (non-empty contact_points_group) — the color-cleanest cup variants
    # base8/base12 lack them, so cup uses the grasp-annotated base0(blue)/base3(green).
    POOL = {
        "bottle": [("001_bottle", 0, "red"), ("001_bottle", 22, "green"), ("001_bottle", 5, "orange")],
        "cup": [("021_cup", 0, "blue"), ("021_cup", 3, "green")],
        "shoe": [("041_shoe", 8, "red"), ("041_shoe", 4, "green")],
        "mug": [("039_mug", 0, "black")],
        "can": [("071_can", 3, "red")],
        "toycar": [("057_toycar", 3, "green")],
        "phone": [("077_phone", 4, "black")],
        "soap": [("107_soap", 2, "blue")],
        "hamburg": [("006_hamburg", 4, "yellow")],
        "bread": [("075_bread", 4, "golden")],
        "coffee-box": [("113_coffee-box", 0, "brown")],
        "mouse": [("047_mouse", 0, "gray")],
    }

    # Per-object resting orientation, copied from the native task that grasps each
    # object (proven to settle stably): bottle lies down (adjust_bottle), cup/can
    # stand upright (place_empty_cup / place_cans_plasticbox), the rest lie flat
    # (put_object_cabinet / place_shoe / hanging_mug / ...).
    REST_QPOS = {
        "001_bottle": [0.707, 0.0, 0.0, 0.707],
        "021_cup": [0.5, 0.5, 0.5, 0.5],
        "071_can": [0.5, 0.5, 0.5, 0.5],
        "077_phone": [0.5, -0.5, 0.5, -0.5],   # place_phone_stand ori_quat for base4
        "_default": [0.707, 0.707, 0.0, 0.0],
    }

    # Per-object random yaw (rotate_rand, rotate_lim), copied from each object's native
    # placement so orientation varies episode-to-episode while still resting stably and
    # stays graspable: the [0.707,0.707,0,0] group gets ±60° yaw (put_object_cabinet uses
    # [0,pi/3,0] for exactly these objects — full [0,pi] makes thin/handled objects like
    # phone/mug land un-graspable); cup/can are radially symmetric so native leaves them
    # unrotated; the lying bottle gets a small ±0.4 jitter on top of its arm-directed base
    # orientation (adjust_bottle), handled explicitly in load_actors.
    ROTATE = {
        "021_cup": (False, [0.0, 0.0, 0.0]),
        "071_can": (False, [0.0, 0.0, 0.0]),
        "001_bottle": (False, [0.0, 0.0, 0.0]),  # base+jitter set explicitly below
        "077_phone": (True, [0.0, 0.7, 0.0]),    # thin -> small yaw (place_phone_stand)
        "_default": (True, [0.0, np.pi / 3, 0.0]),
    }

    def setup_demo(self, **kwags):
        # Capture seed so the episode composition is derived purely from it: eval
        # calls setup_demo twice with the same seed (expert-check + rollout) and
        # both must produce the same instruction + grader.
        self._seed = kwags.get("seed", 0)
        super()._init_task_env_(**kwags)

    # ---- placement helper (same as operate_tabletop) -------------------------
    def _sample_pose(self, occupied, xlim, ylim, qpos, rotate_rand=False,
                     rotate_lim=(0, 0, 0), center_gap=0.0, min_sep=0.13):
        for _ in range(80):
            cand = rand_pose(xlim=list(xlim), ylim=list(ylim), qpos=list(qpos),
                             rotate_rand=rotate_rand, rotate_lim=list(rotate_lim))
            if center_gap and abs(cand.p[0]) < center_gap:
                continue
            if all(np.hypot(cand.p[0] - o[0], cand.p[1] - o[1]) > min_sep for o in occupied):
                return cand
        return None

    def load_actors(self):
        rng = np.random.default_rng(self._seed)

        # --- deterministic episode composition (before any global-np pose RNG) ---
        # Target: noun uniform over ALL 12 categories (seed % 12), color cycles within
        # the noun (seed // 12). seed%N cycling (like operate_tabletop's mode = seed % 3)
        # keeps the target distribution uniform over ANY consecutive seed range;
        # default_rng(seed).integers clusters for small consecutive seeds. Every category
        # is equally likely to be the target — all 12 are grasp-annotated with per-object
        # grasp params in play_once.
        all_nouns = list(self.POOL.keys())
        t_noun = all_nouns[self._seed % len(all_nouns)]
        _nv = self.POOL[t_noun]
        t_obj, t_mid, t_color = _nv[(self._seed // len(all_nouns)) % len(_nv)]
        target_v = (t_noun, t_obj, t_mid, t_color)
        # Distractors: 3 distinct categories sampled ~uniformly from all 12 nouns (the
        # target noun may recur -> a same-noun different-color distractor). Each picks a
        # random color variant that isn't the exact target variant. This keeps the scene
        # a near-uniform 4-of-12 sample; color/noun grounding arises naturally when a
        # same-noun or same-color distractor happens to be drawn.
        shuffled = [all_nouns[i] for i in rng.permutation(len(all_nouns))]
        distractor_vs = []
        for noun in shuffled:
            if len(distractor_vs) >= 3:
                break
            cands = [(noun, obj, mid, color) for (obj, mid, color) in self.POOL[noun]
                     if not (noun == t_noun and color == t_color)]
            if cands:
                distractor_vs.append(cands[int(rng.integers(len(cands)))])
        scene_variants = [target_v] + distractor_vs

        # Role of each distractor relative to the target (post-hoc; NOT guaranteed to
        # exist every episode under option B). Used by the Layer-B teleport tests.
        def _role(v):
            if v == target_v:
                return "target"
            if v[0] == t_noun:
                return "same_noun"
            if v[3] == t_color:
                return "same_color"
            return "other"
        role_of = {v: _role(v) for v in scene_variants}
        order = list(rng.permutation(len(scene_variants)))  # randomize placement, seed-derived

        self.target_noun, self.target_color = t_noun, t_color
        self.distractor_info = []
        self.distractors = []   # [{actor, noun, color, modelname, role}] for Layer-B teleport tests
        self.target = None

        occupied = []
        self._target_bottle_upright = False
        for idx in order:
            noun, obj, mid, color = scene_variants[idx]
            qpos = self.REST_QPOS.get(obj, self.REST_QPOS["_default"])
            rot_rand, rot_lim = self.ROTATE.get(obj, self.ROTATE["_default"])
            pose = self._sample_pose(occupied, xlim=[-0.25, 0.25], ylim=[-0.2, 0.05],
                                     qpos=qpos, rotate_rand=rot_rand, rotate_lim=rot_lim)
            if pose is None:
                raise UnStableError(f"pick_diverse_object: no free spot for {obj} (crowded table)")
            # Bottle: 50/50 upright vs lying (seed-derived coin, reproducible). Upright uses
            # pick_dual_bottles' qpos [0.66,0.66,-0.25,-0.25] (base sits flat -> stable at
            # default z; grasp with pre_grasp_dis=0.08); lying uses adjust_bottle's qpos and
            # must point toward the grasp arm (arm = x-sign in play_once) or the single-arm
            # grasp is unreachable (grasp 0.1). Small yaw jitter on top for variety.
            if obj == "001_bottle":
                upright = rng.random() < 0.5
                if upright:
                    base = [0.66, 0.66, -0.25, -0.25]
                    jit = t3d.euler.euler2quat(0, np.random.uniform(-1, 1), 0)
                else:
                    base = [0.707, 0.0, 0.0, 0.707] if pose.p[0] > 0 else [0.707, 0.0, 0.0, -0.707]
                    jit = t3d.euler.euler2quat(0, 0, np.random.uniform(-0.4, 0.4))
                q = t3d.quaternions.qmult(base, jit)
                pose = sapien.Pose([float(pose.p[0]), float(pose.p[1]), float(pose.p[2])], q)
                if role_of[scene_variants[idx]] == "target":
                    self._target_bottle_upright = upright
            actor = create_actor(self, pose=pose, modelname=obj, convex=True,
                                 model_id=mid, is_static=False)
            if actor is None:
                raise UnStableError(f"pick_diverse_object: failed to place {obj}")
            occupied.append(pose.p[:2])
            self.add_prohibit_area(actor if actor.config is not None else actor.get_pose(), padding=0.05)
            tag = f"{noun}/{color}/{obj}base{mid}"
            if role_of[scene_variants[idx]] == "target":
                self.target = actor
                self.target_modelname = obj
                self.target_id = mid
            else:
                self.distractor_info.append(tag)
                self.distractors.append({"actor": actor, "noun": noun, "color": color,
                                         "modelname": obj, "role": role_of[scene_variants[idx]]})

        # Baseline height for the lift-check, captured after physics settles (eval
        # never calls play_once, so it cannot live there).
        self.delay(2)
        self.target_origin_z = float(self.target.get_pose().p[2])

    def play_once(self):
        # Top-level info (NOT info["info"], the placeholder set) so the reporter can
        # split grounding success by target noun / color / distractor makeup.
        self.info["target"] = f"{self.target_noun}/{self.target_color}/{self.target_modelname}base{self.target_id}"
        self.info["target_noun"] = self.target_noun
        self.info["target_color"] = self.target_color
        self.info["distractors"] = list(self.distractor_info)

        arm_tag = ArmTag("right" if self.target.get_pose().p[0] > 0 else "left")
        # Grasp the named object and lift it clear of the table. Grasp params are
        # object-specific, copied from each object's native grasp task (any of the 12
        # can be the target): cup needs an arm-dependent contact point (place_empty_cup),
        # shoe needs gripper_pos=0 (place_shoe), mug/phone use a closer pre-grasp
        # (hanging_mug / place_phone_stand), bottle uses 0.08 upright (pick_dual_bottles)
        # / 0.1 lying (adjust_bottle). The rest — can (place_cans), hamburg
        # (place_burger_fries) and the put_object_cabinet group (mouse/toycar/soap/
        # coffee-box/bread) — grasp with the default pre_grasp_dis=0.1. Then lift.
        if self.target_modelname == "021_cup":
            cid = [0, 2][int(arm_tag == "left")]
            grasp = self.grasp_actor(self.target, arm_tag=arm_tag, pre_grasp_dis=0.1, contact_point_id=cid)
        elif self.target_modelname == "041_shoe":
            grasp = self.grasp_actor(self.target, arm_tag=arm_tag, pre_grasp_dis=0.1, gripper_pos=0)
        elif self.target_modelname == "039_mug":
            grasp = self.grasp_actor(self.target, arm_tag=arm_tag, pre_grasp_dis=0.05)
        elif self.target_modelname == "077_phone":
            grasp = self.grasp_actor(self.target, arm_tag=arm_tag, pre_grasp_dis=0.08)
        elif self.target_modelname == "001_bottle":
            grasp = self.grasp_actor(self.target, arm_tag=arm_tag,
                                     pre_grasp_dis=0.08 if self._target_bottle_upright else 0.1)
        else:  # can + hamburg + cabinet group: default
            grasp = self.grasp_actor(self.target, arm_tag=arm_tag, pre_grasp_dis=0.1)
        self.move(grasp)
        # Lift straight up in WORLD frame: move_axis="arm" lifts along the gripper approach
        # axis, which is ~vertical for a top grasp but ~horizontal for a side grasp (upright
        # bottle) -> a side-grasped object wouldn't rise. World-z lifts every grasp clear.
        self.move(self.move_by_displacement(arm_tag, z=0.12))

        # {A} = the named object as a literal "the {color} {noun}" (no '/', so the
        # native replace_placeholders substitutes it verbatim instead of drawing a
        # random objects_description) -> color+noun is controlled and always present.
        self.info["info"] = {"{A}": f"the {self.target_color} {self.target_noun}", "{a}": str(arm_tag)}
        return self.info

    def check_success(self):
        return named_object_lifted_and_held(self, self.target, self.target_modelname,
                                            self.target_origin_z)
