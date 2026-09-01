import json
import os

import numpy as np
import sapien.core as sapien

from ._base_task import Base_Task
from ._if_relative import DIRECTIONS, placed_in_direction, placed_on_top
from .utils import *
from ._GLOBAL_CONFIGS import *


class place_relative(Base_Task):
    """Place-Relative IF task: spatial-DIRECTION understanding (IF-Spatial-Direction).

    A mover A and a reference/receiver B (flat-top base) plus ONE distractor are on the
    table. The instruction tells the robot to pick up A and place it in a spatial
    DIRECTION relative to B: one of five values -- left / right / front / back / on top.
    The direction word is the SOLE scored axis: the SAME physical scene is used for all
    five, so nothing in the pixels leaks which direction is asked -- only the instruction
    decides.

    Scene and direction are DECOUPLED through the seed so the same scene appears under
    ALL five directions:

        scene_seed = seed // 5            # identical for the 5-tuple (5k..5k+4)
        direction  = [left,right,front,back,on_top][seed % 5]

    So eval seeds (0..4),(5..9),... give scene #0,#1,... each once per direction, with
    pixel-identical initial frames -- the only difference the policy sees is the
    direction phrase {D}. Mirrors laptop_verb ({V}) / grasp_cube_approach ({D}).

    Axis convention (native place_a2b_left): left/right = signed world x, front/back =
    signed world y (FRONT_SIGN in _if_relative pins which y points at the robot),
    on-top = elevation. Objects/colors are self-designed (texture-verified); color is a
    grounding aid, not a scored axis.
    """

    ORDER = ["left", "right", "front", "back", "on_top"]

    # Placement offset from B along the commanded axis. 0.11 (native place_a2b uses
    # 0.13) so that BOTH front (+y) and back (-y) targets fall inside the reachable
    # placement band y in [-0.28, -0.01] (measured): with B centered near y=-0.14,
    # front -> ~-0.03 and back -> ~-0.25, both well within reach. Still lands in the
    # lateral check band [0.08, 0.20].
    OFFSET = 0.11

    # {D} direction-phrase pools -- the ONLY instruction signal of the placement
    # direction. Picked deterministically from scene_seed so the phrase reproduces
    # across eval's paired setup passes (mirrors grasp_cube_approach's {D} pools).
    PHRASES = {
        "left":   ["to the left of"],
        "right":  ["to the right of"],
        "front":  ["in front of"],
        "back":   ["behind"],
        "on_top": ["on top of"],
    }

    # Harness/testing override: force one direction regardless of seed (leave None for
    # real collection/eval so the seed drives it), like grasp_cube_approach.APPROACH.
    DIRECTION = None

    # noun -> (modelname, model_id, color). One locked variant per noun (color = grounding
    # aid, not a scored axis). Movers are grasped and moved; bases are flat-top receivers
    # that stay put (needed so the on-top direction can stack onto them).
    MOVERS = {
        "mouse": ("047_mouse", 0, "gray"),
        "toycar": ("057_toycar", 3, "green"),
        "stapler": ("048_stapler", 4, "red"),
        "remotecontrol": ("079_remotecontrol", 0, "black"),
        "can": ("071_can", 3, "red"),
        "soap": ("107_soap", 2, "blue"),
    }
    BASES = {
        "coffee-box": ("113_coffee-box", 0, "brown"),
        "tea-box": ("112_tea-box", 1, "red"),
    }

    # Resting orientation: can stands upright (pick pool); everything else lies on the
    # [0.707,0.707,0,0] face used by place_object_stand / coffee-box in the pick pool.
    REST_QPOS = {
        "071_can": [0.5, 0.5, 0.5, 0.5],
        "_default": [0.707, 0.707, 0.0, 0.0],
    }
    ROTATE = {
        "071_can": (False, [0.0, 0.0, 0.0]),           # radially symmetric
        "_default": (True, [0.0, np.pi / 3, 0.0]),     # ±60° yaw (place_object_stand)
    }

    def setup_demo(self, **kwags):
        # Capture seed so episode composition is a pure function of it (eval calls
        # setup_demo twice with the same seed and both must match).
        self._seed = kwags.get("seed", 0)
        super()._init_task_env_(**kwags)

    def _sample_pose(self, occupied, xlim, ylim, qpos, rotate_rand=False,
                     rotate_lim=(0, 0, 0), min_sep=0.15, min_abs_x=0.0, avoid=None,
                     avoid_sep=0.0):
        for _ in range(120):
            cand = rand_pose(xlim=list(xlim), ylim=list(ylim), qpos=list(qpos),
                             rotate_rand=rotate_rand, rotate_lim=list(rotate_lim))
            if min_abs_x and abs(cand.p[0]) < min_abs_x:
                continue
            if avoid is not None and np.hypot(cand.p[0] - avoid[0], cand.p[1] - avoid[1]) < avoid_sep:
                continue
            if all(np.hypot(cand.p[0] - o[0], cand.p[1] - o[1]) > min_sep for o in occupied):
                return cand
        return None

    def _base_half_height_z(self, actor, modelname, model_id):
        """World-space half-height of `actor` along z, from its mesh extents*scale rotated
        by its settled orientation (boxes have no functional point to place onto)."""
        md = json.load(open(os.path.join("assets/objects", modelname, f"model_data{model_id}.json")))
        half = np.asarray(md["extents"], float) * np.asarray(md["scale"], float) / 2.0
        R = actor.get_pose().to_transformation_matrix()[:3, :3]
        return float(np.sum(np.abs(R[2, :]) * half))

    def load_actors(self):
        # Decouple scene from direction: the scene depends only on seed//5 so the
        # 5-tuple (5k..5k+4) share ONE scene; the direction comes from seed%5. Re-seed
        # here so paired seeds get an identical scene under every direction. DIRECTION,
        # if set, forces the mode (harness/testing only).
        scene_seed = self._seed // 5
        np.random.seed(scene_seed)
        rng = np.random.default_rng(scene_seed)
        self.direction = self.DIRECTION if self.DIRECTION in self.ORDER else self.ORDER[self._seed % 5]

        mover_nouns = list(self.MOVERS.keys())
        base_nouns = list(self.BASES.keys())

        # Deterministic (A, B) from scene_seed so consecutive scenes cover them uniformly.
        a_noun = mover_nouns[scene_seed % len(mover_nouns)]
        b_noun = base_nouns[(scene_seed // len(mover_nouns)) % len(base_nouns)]
        a_obj, a_mid, a_color = self.MOVERS[a_noun]
        b_obj, b_mid, b_color = self.BASES[b_noun]

        # ONE distractor (space is reserved on all four sides of B for any direction, so
        # keep the table clear -- see min_sep below). Chosen from the remaining pool.
        pool = [(n, *self.MOVERS[n]) for n in mover_nouns] + [(n, *self.BASES[n]) for n in base_nouns]
        pool = [p for p in pool if p[0] not in (a_noun, b_noun)]
        d_noun, d_obj, d_mid, d_color = pool[rng.integers(len(pool))]

        self.mover_noun, self.mover_color = a_noun, a_color
        self.reference_noun, self.reference_color = b_noun, b_color
        self.distractor_info = []
        self.distractors = []           # [{actor, noun, color, modelname}] for Layer-B tests
        self.mover = None
        self.reference = None

        occupied = []

        def _spawn(obj, mid, xlim, ylim, min_sep, min_abs_x, avoid=None, avoid_sep=0.0):
            qpos = self.REST_QPOS.get(obj, self.REST_QPOS["_default"])
            rr, rl = self.ROTATE.get(obj, self.ROTATE["_default"])
            pose = self._sample_pose(occupied, xlim=xlim, ylim=ylim, qpos=qpos,
                                     rotate_rand=rr, rotate_lim=rl, min_sep=min_sep,
                                     min_abs_x=min_abs_x, avoid=avoid, avoid_sep=avoid_sep)
            if pose is None:
                raise UnStableError(f"place_relative: no free spot for {obj} (crowded table)")
            actor = create_actor(self, pose=pose, modelname=obj, convex=True,
                                 model_id=mid, is_static=False)
            if actor is None:
                raise UnStableError(f"place_relative: failed to place {obj}")
            occupied.append(pose.p[:2])
            self.add_prohibit_area(actor, padding=0.05)
            return actor

        # Reference B: CENTRAL in x and set DEEP in y (toward the far side) so that both
        # the front (+y) and back (-y) placement targets stay inside the reachable band
        # y in [-0.28, -0.01] (measured). Centering at y~-0.14 with OFFSET 0.11 puts
        # front at ~-0.03 (near the reachable front edge) and back at ~-0.25 (far), both
        # plannable; a shallower B would push the front target past +y into unreachable
        # space. Tight limits keep it near the middle in x.
        self.reference = _spawn(b_obj, b_mid, xlim=[-0.08, 0.08], ylim=[-0.15, -0.13],
                                min_sep=0.0, min_abs_x=0.0)
        self.reference_modelname, self.reference_id = b_obj, b_mid
        b_p = self.reference.get_pose().p

        # Mover A: off to a side (|x|>0.18) and clear of B, so it is graspable and a
        # do-nothing policy can't satisfy any direction band from the spawn alone -- A
        # MUST actually be moved to succeed.
        b_x = b_p[0]
        a_xlim = [0.18, 0.30] if b_x >= 0 else [-0.30, -0.18]
        self.mover = _spawn(a_obj, a_mid, xlim=a_xlim, ylim=[-0.2, 0.05],
                            min_sep=0.22, min_abs_x=0.0)
        self.mover_modelname, self.mover_id = a_obj, a_mid

        # Distractor: kept FAR from B (> OFFSET + clearance) so it never occupies any of
        # the four lateral placement bands -- the commanded band is always free.
        self.distractor = _spawn(d_obj, d_mid, xlim=[-0.28, 0.28], ylim=[-0.2, 0.05],
                                 min_sep=0.15, min_abs_x=0.0, avoid=b_p[:2], avoid_sep=0.26)
        self.distractor_info.append(f"{d_noun}/{d_color}/{d_obj}base{d_mid}")
        self.distractors.append({"actor": self.distractor, "noun": d_noun,
                                 "color": d_color, "modelname": d_obj})

        self.delay(2)
        # B's top surface (for the on-top oracle target) after physics settles.
        self.base_half_z = self._base_half_height_z(self.reference, self.reference_modelname, self.reference_id)

    def _direction_phrase(self):
        pool = self.PHRASES[self.direction]
        return pool[(self._seed // 5) % len(pool)]

    def play_once(self):
        # Top-level info for the reporter (NOT info["info"], the placeholder set).
        self.info["direction"] = self.direction
        self.info["mover"] = f"{self.mover_color}/{self.mover_noun}"
        self.info["reference"] = f"{self.reference_color}/{self.reference_noun}"
        self.info["distractors"] = list(self.distractor_info)

        b = self.reference.get_pose().p

        # Arm = the MOVER's side, for every direction. The grasp must be same-side to
        # plan (a cross-body grasp fails); the subsequent place only reaches ~OFFSET
        # across center, which is inside both arms' envelope (measured). Choosing the
        # arm by the target side instead makes the grasp cross-body whenever the
        # commanded lateral direction points away from where the mover spawned.
        arm_tag = ArmTag("right" if self.mover.get_pose().p[0] > 0 else "left")

        if self.direction in DIRECTIONS:
            axis, sign = DIRECTIONS[self.direction]
            target = [float(b[0]), float(b[1]), float(b[2])]
            target[0 if axis == "x" else 1] += sign * self.OFFSET

        # Grasp the mover (uniform pre_grasp_dis=0.1, per place_object_stand) and lift it
        # clear in WORLD z (robust for any grasp direction, per pick_diverse's lesson).
        self.move(self.grasp_actor(self.mover, arm_tag=arm_tag, pre_grasp_dis=0.1))
        self.move(self.move_by_displacement(arm_tag, z=0.12))

        if self.direction in DIRECTIONS:
            # Place next to B, offset along the commanded axis (band is kept clear).
            self.move(self.place_actor(self.mover, arm_tag=arm_tag, target_pose=target))
        else:  # on_top: place aligned over B, just above its top surface, then release.
            target = [float(b[0]), float(b[1]), float(b[2] + self.base_half_z + 0.03)]
            self.move(self.place_actor(self.mover, arm_tag=arm_tag, target_pose=target,
                                       constrain="free", pre_dis=0.07))

        desc_a = f"the {self.mover_color} {self.mover_noun}"
        desc_b = f"the {self.reference_color} {self.reference_noun}"
        self.info["info"] = {"{A}": desc_a, "{B}": desc_b, "{a}": str(arm_tag),
                             "{D}": self._direction_phrase()}
        return self.info

    def check_success(self):
        if self.direction in DIRECTIONS:
            axis, sign = DIRECTIONS[self.direction]
            return placed_in_direction(self, self.mover, self.reference, axis, sign)
        return placed_on_top(self, self.mover, self.reference)
