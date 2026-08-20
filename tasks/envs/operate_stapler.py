import json
import re
from pathlib import Path

from ._base_task import Base_Task
from .utils import *
from ._GLOBAL_CONFIGS import *


class operate_stapler(Base_Task):
    # Office/stationery-themed graspable distractors (fits the stapler desk context).
    # Every listed asset has >=1 model_id marked "stable": true, so it rests flat on the
    # table with the glb resting qpos and needs no per-object orientation tuning.
    # Deliberately excludes non-stable assets (035_apple sphere, 058_markpen / 010_pen /
    # 083_brush / 116_keyboard cylinders-or-thin) that never rest naturally.
    DISTRACTOR_NAMES = [
        "077_phone",
        "078_phonestand",
        "079_remotecontrol",
        "059_pencup",
        "093_brush-pen",
        "092_notebook",
        "095_glue",
        "081_playingcards",
        "100_seal",
        "024_scanner",
        "047_mouse",
        "021_cup",
    ]
    _stable_ids_cache = {}

    @classmethod
    def _stable_model_ids(cls, modelname):
        # Ids whose model_data{N}.json is marked "stable": true AND a mesh exists.
        # RoboTwin's own cluttered-table pool uses exactly this filter — a stable id is
        # validated to rest flat under the glb resting qpos [0.707107, 0.707107, 0, 0].
        # This also drops non-existent ids (e.g. 071_can skips 4) since they aren't stable.
        if modelname not in cls._stable_ids_cache:
            d = Path("assets/objects") / modelname
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
                if mesh_ok:
                    ids.append(n)
            cls._stable_ids_cache[modelname] = sorted(ids)
        return cls._stable_ids_cache[modelname]

    def setup_demo(self, **kwags):
        # Capture seed so mode can be derived purely from it (see load_actors).
        self._seed = kwags.get("seed", 0)
        super()._init_task_env_(**kwags)

    def load_actors(self):
        # Pure seed derivation: mode must reproduce identically across eval's two
        # setup_demo(same seed) calls (expert-check pass vs policy-rollout pass),
        # otherwise the generated instruction and check_success would grade different
        # verbs. Deriving from the seed directly makes this immune to RNG draw order.
        self.mode = ["press", "move"][self._seed % 2]

        # --- stapler (graspable-zone sampling shared by both modes) ---
        rand_pos = rand_pose(
            xlim=[-0.25, 0.25],
            ylim=[-0.2, 0.0],
            qpos=[0.5, 0.5, 0.5, 0.5],
            rotate_rand=True,
            rotate_lim=[0, np.pi, 0],
        )
        while abs(rand_pos.p[0]) < 0.05:
            rand_pos = rand_pose(
                xlim=[-0.25, 0.25],
                ylim=[-0.2, 0.0],
                qpos=[0.5, 0.5, 0.5, 0.5],
                rotate_rand=True,
                rotate_lim=[0, np.pi, 0],
            )
        self.stapler_id = np.random.choice([0, 1, 2, 3, 4, 5, 6], 1)[0]
        # Static only in press mode so pressing does not topple it; movable in move
        # mode so it can be grasped. Visually indistinguishable at rest.
        self.stapler = create_actor(
            self,
            pose=rand_pos,
            modelname="048_stapler",
            convex=True,
            model_id=self.stapler_id,
            is_static=(self.mode == "press"),
        )

        # --- colored pad (present in BOTH modes; same-side sampling for both) ---
        if rand_pos.p[0] > 0:
            pad_xlim = [0.05, 0.25]
        else:
            pad_xlim = [-0.25, -0.05]
        pad_pose = rand_pose(xlim=pad_xlim, ylim=[-0.2, 0.0], qpos=[1, 0, 0, 0], rotate_rand=False)
        while (np.sqrt((pad_pose.p[0] - rand_pos.p[0])**2 + (pad_pose.p[1] - rand_pos.p[1])**2) < 0.1):
            pad_pose = rand_pose(xlim=pad_xlim, ylim=[-0.2, 0.0], qpos=[1, 0, 0, 0], rotate_rand=False)

        colors = {
            "Red": (1, 0, 0),
            "Green": (0, 1, 0),
            "Blue": (0, 0, 1),
            "Yellow": (1, 1, 0),
            "Cyan": (0, 1, 1),
            "Magenta": (1, 0, 1),
            "Black": (0, 0, 0),
            "Gray": (0.5, 0.5, 0.5),
        }
        color_items = list(colors.items())
        color_index = np.random.choice(len(color_items))
        self.color_name, self.color_value = color_items[color_index]

        self.pad = create_box(
            scene=self.scene,
            pose=pad_pose,
            half_size=[0.055, 0.03, 0.0005],
            color=self.color_value,
            name="box",
        )
        self.pad_pose = self.pad.get_pose().p.tolist() + [0.707, 0, 0, 0.707]

        self.add_prohibit_area(self.stapler, padding=0.1)
        self.add_prohibit_area(self.pad, padding=0.15)

        self._load_distractors(avoid=[rand_pos.p[:2], pad_pose.p[:2]])

    def _load_distractors(self, avoid):
        num = int(np.random.choice([1, 2]))
        names = list(self.DISTRACTOR_NAMES)
        np.random.shuffle(names)
        occupied = [np.asarray(p, dtype=float) for p in avoid]
        self.distractors = []
        self.distractor_info = []
        for name in names[:num]:
            stable_ids = self._stable_model_ids(name)
            if not stable_ids:
                continue
            model_id = int(np.random.choice(stable_ids))
            pose = None
            for _ in range(50):
                cand = rand_pose(
                    xlim=[-0.25, 0.25],
                    ylim=[-0.2, 0.05],
                    # RoboTwin's canonical resting orientation for glb library objects
                    # (90 deg about x lays the authored up-axis flat on the table), plus a
                    # random yaw about vertical. Correct only for "stable"-marked ids, which
                    # is why _stable_model_ids filters on that flag.
                    qpos=[0.707107, 0.707107, 0, 0],
                    rotate_rand=True,
                    rotate_lim=[0, np.pi, 0],
                )
                if all(np.hypot(cand.p[0] - o[0], cand.p[1] - o[1]) > 0.12 for o in occupied):
                    pose = cand
                    break
            if pose is None:
                continue
            actor = create_actor(
                self,
                pose=pose,
                modelname=name,
                convex=True,
                model_id=model_id,
                is_static=True,
            )
            if actor is None:
                continue
            occupied.append(pose.p[:2])
            # Some assets (e.g. 108_block) ship model_data without a "scale" key, so
            # create_actor leaves actor.config None. add_prohibit_area reads config, so
            # fall back to a pose-based keep-out box (default extents) when config is None.
            self.add_prohibit_area(actor if actor.config is not None else actor.get_pose(), padding=0.05)
            self.distractors.append(actor)
            self.distractor_info.append(f"{name}/base{model_id}")

    def play_once(self):
        # Single-arm: pick by stapler side (left if negative x, right otherwise).
        arm_tag = ArmTag("left" if self.stapler.get_pose().p[0] < 0 else "right")

        # Top-level info key (NOT info["info"], which is the placeholder param set)
        # so per-mode success can be split in logs without breaking instruction filtering.
        self.info["mode"] = self.mode
        self.info["distractors"] = self.distractor_info

        if self.mode == "press":
            # Grasp over the stapler head and press down (reuses press_stapler).
            self.move(
                self.grasp_actor(self.stapler, arm_tag=arm_tag, pre_grasp_dis=0.1, grasp_dis=0.1, contact_point_id=2))
            self.move(self.close_gripper(arm_tag=arm_tag))
            self.move(
                self.grasp_actor(self.stapler, arm_tag=arm_tag, pre_grasp_dis=0.02, grasp_dis=0.02, contact_point_id=2))
            # No {B}: instruction filter routes to press-verb templates only.
            self.info["info"] = {
                "{A}": f"048_stapler/base{self.stapler_id}",
                "{a}": str(arm_tag),
            }
        else:  # move
            # Grasp, lift, place onto the pad with alignment (reuses move_stapler_pad).
            self.move(self.grasp_actor(self.stapler, arm_tag=arm_tag, pre_grasp_dis=0.1))
            self.move(self.move_by_displacement(arm_tag, z=0.1, move_axis="arm"))
            self.move(
                self.place_actor(
                    self.stapler,
                    target_pose=self.pad_pose,
                    arm_tag=arm_tag,
                    pre_dis=0.1,
                    dis=0.0,
                    constrain="align",
                ))
            # With {B}=pad color: instruction filter routes to move-verb templates only.
            self.info["info"] = {
                "{A}": f"048_stapler/base{self.stapler_id}",
                "{B}": self.color_name,
                "{a}": str(arm_tag),
            }
        return self.info

    def check_success(self):
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
        else:  # move
            stapler_pose = self.stapler.get_pose().p
            stapler_qpose = np.abs(self.stapler.get_pose().q)
            target_pos = self.pad.get_pose().p
            eps = [0.02, 0.02, 0.01]
            return (np.all(abs(stapler_pose - target_pos) < np.array(eps))
                    and (stapler_qpose.max() - stapler_qpose.min()) < 0.02 and self.robot.is_left_gripper_open()
                    and self.robot.is_right_gripper_open())
