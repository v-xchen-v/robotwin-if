import json
import os

import numpy as np
import sapien.core as sapien

from ._base_task import Base_Task
from ._if_relative import placed_beside, placed_on_top
from .utils import *
from ._GLOBAL_CONFIGS import *


class place_relative(Base_Task):
    """Place-Relative IF task: spatial-relation understanding.

    Two named objects (A the mover, B the reference/receiver) plus 1-3 distractors are
    on the table. The instruction tells the robot to pick up A and place it in a spatial
    relation to B: 'beside' (next to, on the table) or 'on top of' (stacked onto B). The
    relation word is the SCORED axis: the SAME object set is used for both relations, so
    the scene never leaks whether it's beside or on-top — only the instruction decides.

    The reference is exposed under a relation-specific placeholder ({B} for beside, {C}
    for on-top) so RoboTwin's filter_instructions routes each episode to the matching
    template family (see tasks/task_instruction/place_relative.json).

    Objects/colors are self-designed (texture-verified, see
    notes/2026-08-24-place-relative/evidence/pool/POOL.md); movers reuse
    place_object_stand's grasp; on-top target = B's AABB top; beside offset 类推自
    place_a2b; success thresholds 类推自 place_a2b / stack_blocks_two，论文未确认.
    """

    # noun -> (modelname, model_id, color). One locked variant per noun (color = grounding
    # aid, not a scored axis; cross-noun color collisions are fine). Movers are grasped and
    # moved; bases are flat-top receivers that stay put.
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
                     rotate_lim=(0, 0, 0), min_sep=0.15, min_abs_x=0.0):
        for _ in range(120):
            cand = rand_pose(xlim=list(xlim), ylim=list(ylim), qpos=list(qpos),
                             rotate_rand=rotate_rand, rotate_lim=list(rotate_lim))
            if min_abs_x and abs(cand.p[0]) < min_abs_x:
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

    def _beside_target(self, b, arm_tag):
        """Pick a spot ~0.13 from B (inside the beside band) that is CLEAR of distractors,
        so the placed mover never lands on top of an existing object. Try the grasp-arm side
        first (reachable, usually toward the table edge), then the opposite side, then
        front/back; fall back to the arm side if every candidate is cluttered."""
        dists = [d["actor"].get_pose().p for d in self.distractors]
        s = 1.0 if str(arm_tag) == "right" else -1.0
        r = 0.13
        for dx, dy in [(s * r, 0.0), (-s * r, 0.0), (0.0, -r), (0.0, r)]:
            tx, ty = b[0] + dx, b[1] + dy
            if abs(tx) > 0.30 or not (-0.28 <= ty <= 0.10):
                continue
            if all(np.hypot(tx - p[0], ty - p[1]) > 0.10 for p in dists):
                return [float(tx), float(ty), float(b[2])]
        return [float(b[0] + s * r), float(b[1]), float(b[2])]

    def load_actors(self):
        rng = np.random.default_rng(self._seed)
        mover_nouns = list(self.MOVERS.keys())
        base_nouns = list(self.BASES.keys())

        # Deterministic (relation, A, B) so consecutive seeds cover them uniformly
        # (seed%N cycling, per pick_diverse's lesson that default_rng clusters small seeds).
        self.relation = ["beside", "on_top"][self._seed % 2]
        a_noun = mover_nouns[(self._seed // 2) % len(mover_nouns)]
        b_noun = base_nouns[(self._seed // (2 * len(mover_nouns))) % len(base_nouns)]
        a_obj, a_mid, a_color = self.MOVERS[a_noun]
        b_obj, b_mid, b_color = self.BASES[b_noun]

        # 1-3 distractors. Count uses a MIXED-seed stream (default_rng([seed, const])), NOT
        # default_rng(seed).integers — the latter's FIRST draw clusters hard on small
        # consecutive seeds (10/16 low seeds returned 3, so it looked like "always 3"; the
        # same first-draw clustering pick_diverse hit). This form is reproducible, uniform
        # over 1/2/3, and decorrelated from mover/relation.
        pool = [(n, *self.MOVERS[n]) for n in mover_nouns] + [(n, *self.BASES[n]) for n in base_nouns]
        pool = [p for p in pool if p[0] not in (a_noun, b_noun)]
        n_dist = 1 + int(np.random.default_rng([self._seed, 0xC0FFEE]).integers(3))
        idx = rng.permutation(len(pool))[:n_dist]
        distractor_vs = [pool[i] for i in idx]

        self.mover_noun, self.mover_color = a_noun, a_color
        self.reference_noun, self.reference_color = b_noun, b_color
        self.distractor_info = []
        self.distractors = []           # [{actor, noun, color, modelname}] for Layer-B tests
        self.mover = None
        self.reference = None

        occupied = []

        def _spawn(obj, mid, xlim, ylim, min_sep, min_abs_x):
            qpos = self.REST_QPOS.get(obj, self.REST_QPOS["_default"])
            rr, rl = self.ROTATE.get(obj, self.ROTATE["_default"])
            pose = self._sample_pose(occupied, xlim=xlim, ylim=ylim, qpos=qpos,
                                     rotate_rand=rr, rotate_lim=rl, min_sep=min_sep, min_abs_x=min_abs_x)
            if pose is None:
                raise UnStableError(f"place_relative: no free spot for {obj} (crowded table)")
            actor = create_actor(self, pose=pose, modelname=obj, convex=True,
                                 model_id=mid, is_static=False)
            if actor is None:
                raise UnStableError(f"place_relative: failed to place {obj}")
            occupied.append(pose.p[:2])
            self.add_prohibit_area(actor, padding=0.05)
            return actor

        # Reference B: central & reachable. Placing a HELD object ON TOP of B at height only
        # plans reliably when B is within comfortable arm reach (native place_object_stand
        # spawns its receiver near center). The SAME region is used for both relations, so
        # the layout never leaks beside vs on-top.
        self.reference = _spawn(b_obj, b_mid, xlim=[-0.13, 0.13], ylim=[-0.15, -0.03],
                                min_sep=0.0, min_abs_x=0.0)
        self.reference_modelname, self.reference_id = b_obj, b_mid

        # Mover A: off to the side (|x|>0.18) and > beside-hi (0.20) from B. Keeps A graspable
        # AND guarantees a do-nothing policy can't satisfy beside's [0.08,0.20] band from the
        # spawn alone — the mover MUST actually be moved to succeed. Spawn it on the SAME side
        # as B (same x-sign) so the near-arm (chosen by A's side) places onto B without a
        # cross-body reach — the main on-top place-plan failure mode.
        b_x = self.reference.get_pose().p[0]
        a_xlim = [0.18, 0.30] if b_x >= 0 else [-0.30, -0.18]
        self.mover = _spawn(a_obj, a_mid, xlim=a_xlim, ylim=[-0.2, 0.05],
                            min_sep=0.22, min_abs_x=0.0)
        self.mover_modelname, self.mover_id = a_obj, a_mid

        # Distractors: fill the remaining space, separated from everything.
        for noun, obj, mid, color in distractor_vs:
            actor = _spawn(obj, mid, xlim=[-0.28, 0.28], ylim=[-0.2, 0.05], min_sep=0.15, min_abs_x=0.0)
            self.distractor_info.append(f"{noun}/{color}/{obj}base{mid}")
            self.distractors.append({"actor": actor, "noun": noun, "color": color, "modelname": obj})

        self.delay(2)
        # B's top surface (for the on-top oracle target) after physics settles.
        self.base_half_z = self._base_half_height_z(self.reference, self.reference_modelname, self.reference_id)

    def play_once(self):
        # Top-level info for the reporter (NOT info["info"], the placeholder set).
        self.info["relation"] = self.relation
        self.info["mover"] = f"{self.mover_color}/{self.mover_noun}"
        self.info["reference"] = f"{self.reference_color}/{self.reference_noun}"
        self.info["distractors"] = list(self.distractor_info)

        arm_tag = ArmTag("right" if self.mover.get_pose().p[0] > 0 else "left")

        # Grasp the mover (uniform pre_grasp_dis=0.1, per place_object_stand) and lift it
        # clear in WORLD z (robust for any grasp direction, per pick_diverse's lesson).
        self.move(self.grasp_actor(self.mover, arm_tag=arm_tag, pre_grasp_dis=0.1))
        self.move(self.move_by_displacement(arm_tag, z=0.12))

        b = self.reference.get_pose().p
        if self.relation == "beside":
            # Place next to B on a side that is CLEAR of distractors (never drop onto an
            # existing object).
            target = self._beside_target(b, arm_tag)
            self.move(self.place_actor(self.mover, arm_tag=arm_tag, target_pose=target))
        else:  # on_top: place aligned over B, just above its top surface, then release.
            target = [float(b[0]), float(b[1]), float(b[2] + self.base_half_z + 0.03)]
            self.move(self.place_actor(self.mover, arm_tag=arm_tag, target_pose=target,
                                       constrain="free", pre_dis=0.07))

        desc_a = f"the {self.mover_color} {self.mover_noun}"
        desc_b = f"the {self.reference_color} {self.reference_noun}"
        ref_key = "{B}" if self.relation == "beside" else "{C}"
        self.info["info"] = {"{A}": desc_a, ref_key: desc_b, "{a}": str(arm_tag)}
        return self.info

    def check_success(self):
        if self.relation == "beside":
            return placed_beside(self, self.mover, self.reference)
        return placed_on_top(self, self.mover, self.reference)
