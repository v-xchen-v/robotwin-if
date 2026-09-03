from copy import deepcopy

import numpy as np
import sapien.core as sapien
import transforms3d as t3d

from ._base_task import Base_Task
from ._if_eval import apply_if_eval_step_limit
from ._if_grounding import named_object_lifted_and_held
from ._pick_diverse_object_pool import (
    SEEN_POOL,
    UNSEEN_CANDIDATES,
    UNSEEN_POOL,
    familiarity_for_seed,
    target_for_seed,
)
from .utils import *
from ._GLOBAL_CONFIGS import *


class pick_diverse_object(Base_Task):
    """Pick one noun-named object from a familiarity-homogeneous scene.

    Even raw seeds create four-object all-Seen scenes; odd raw seeds create
    four-object all-Unseen scenes. Every scene contains four distinct nouns, so the
    noun-only instruction uniquely identifies the target. This is a scene-level
    object-familiarity split, not a same-scene target-only causal contrast.
    """

    # Probe-only overrides. Production behavior requires every value to remain None.
    FAMILIARITY_OVERRIDE = None
    TARGET_NOUN_OVERRIDE = None
    TARGET_MODEL_ID_OVERRIDE = None
    TARGET_SIDE_OVERRIDE = None
    POOL_OVERRIDE = None
    DISTRACTOR_NOUNS_OVERRIDE = None
    PLACEMENT_ORDER_OVERRIDE = None

    def setup_demo(self, **kwags):
        # Eval calls setup_demo twice with the same seed (expert check + rollout).
        self._seed = int(kwags.get("seed", 0))
        super()._init_task_env_(**kwags)
        apply_if_eval_step_limit(self)

    @staticmethod
    def _production_pool(familiarity):
        if familiarity == "seen":
            return SEEN_POOL
        if familiarity == "unseen":
            if len(UNSEEN_POOL) < 4:
                raise RuntimeError(
                    "pick_diverse_object UNSEEN_POOL is not locked: run the real "
                    "SAPIEN candidate probe and retain at least four passing nouns"
                )
            return UNSEEN_POOL
        raise ValueError(f"unknown object familiarity: {familiarity!r}")

    def _active_pool(self):
        familiarity = self.FAMILIARITY_OVERRIDE or familiarity_for_seed(self._seed)
        pool = self.POOL_OVERRIDE or self._production_pool(familiarity)
        if len(pool) < 4:
            raise RuntimeError(
                f"pick_diverse_object {familiarity} pool has {len(pool)} nouns; "
                "four distinct nouns are required"
            )
        return familiarity, pool

    def _target_variant(self, pool):
        if self.TARGET_NOUN_OVERRIDE is None:
            return target_for_seed(self._seed, pool)

        noun = self.TARGET_NOUN_OVERRIDE
        if noun not in pool:
            raise ValueError(f"target noun {noun!r} is not in the active pool")
        entry = pool[noun]
        model_ids = entry["model_ids"]
        if self.TARGET_MODEL_ID_OVERRIDE is None:
            group_index = self._seed // 2
            model_id = model_ids[(group_index // len(pool)) % len(model_ids)]
        else:
            model_id = int(self.TARGET_MODEL_ID_OVERRIDE)
            if model_id not in model_ids:
                raise ValueError(
                    f"model id {model_id} is not listed for target noun {noun!r}"
                )
        return noun, entry["asset"], model_id

    @staticmethod
    def _sample_pose(occupied, radius, xlim, ylim, qpos, rotate_rand=False,
                     rotate_lim=(0, 0, 0), center_gap=0.0):
        """Sample a collision-aware center using manifest placement radii."""
        for _ in range(120):
            cand = rand_pose(
                xlim=list(xlim),
                ylim=list(ylim),
                qpos=list(qpos),
                rotate_rand=rotate_rand,
                rotate_lim=list(rotate_lim),
            )
            if center_gap and abs(cand.p[0]) < center_gap:
                continue
            if all(
                np.hypot(cand.p[0] - xy[0], cand.p[1] - xy[1])
                > radius + other_radius + 0.025
                for xy, other_radius in occupied
            ):
                return cand
        return None

    def _distractor_nouns(self, pool, target_noun, rng):
        if self.DISTRACTOR_NOUNS_OVERRIDE is None:
            candidates = [noun for noun in pool if noun != target_noun]
            order = rng.permutation(len(candidates))
            return [candidates[int(i)] for i in order[:3]]

        nouns = list(self.DISTRACTOR_NOUNS_OVERRIDE)
        if len(nouns) != 3 or len(set(nouns)) != 3:
            raise ValueError("DISTRACTOR_NOUNS_OVERRIDE must contain three distinct nouns")
        if target_noun in nouns:
            raise ValueError("target noun cannot also be a distractor noun")
        missing = [noun for noun in nouns if noun not in pool]
        if missing:
            raise ValueError(f"distractor nouns are not in the active pool: {missing}")
        return nouns

    def _placement_indices(self, variants, pool, rng):
        policy = self.PLACEMENT_ORDER_OVERRIDE
        if policy is None:
            policy = (
                "target-first"
                if self.TARGET_NOUN_OVERRIDE is not None
                else "radius-first"
            )
        if policy not in {"target-first", "radius-first"}:
            raise ValueError(f"unknown placement order policy: {policy!r}")

        self.placement_policy = policy
        if policy == "target-first":
            if self.TARGET_NOUN_OVERRIDE is None:
                raise ValueError("target-first placement requires a forced target")
            distractor_order = [int(i) + 1 for i in rng.permutation(3)]
            return [0] + distractor_order

        tie_breakers = rng.random(len(variants))
        return sorted(
            range(len(variants)),
            key=lambda i: (-pool[variants[i][0]]["placement_radius"], tie_breakers[i]),
        )

    def load_actors(self):
        rng = np.random.default_rng(self._seed)
        familiarity, pool = self._active_pool()
        target_noun, target_asset, target_model_id = self._target_variant(pool)
        distractor_nouns = self._distractor_nouns(pool, target_noun, rng)

        variants = [(target_noun, target_asset, target_model_id, True)]
        for noun in distractor_nouns:
            entry = pool[noun]
            model_ids = entry["model_ids"]
            model_id = int(model_ids[int(rng.integers(len(model_ids)))])
            variants.append((noun, entry["asset"], model_id, False))
        # Historical forced-target probes stay target-first. Production and the
        # explicitly bound Apple rescue use the same largest-footprint-first ordering.
        order = self._placement_indices(variants, pool, rng)

        self.target_familiarity = familiarity
        self.scene_familiarity = familiarity
        self.target_noun = target_noun
        self.target = None
        self.distractors = []
        self.distractor_info = []
        self.scene_objects = []
        self._target_bottle_upright = False

        occupied = []
        for idx in order:
            noun, asset, model_id, is_target = variants[idx]
            entry = pool[noun]
            radius = entry["placement_radius"]
            xlim = (-0.27, 0.27)
            if is_target and self.TARGET_SIDE_OVERRIDE is not None:
                if self.TARGET_SIDE_OVERRIDE == "left":
                    xlim = (-0.27, -0.08)
                elif self.TARGET_SIDE_OVERRIDE == "right":
                    xlim = (0.08, 0.27)
                else:
                    raise ValueError(
                        "TARGET_SIDE_OVERRIDE must be 'left', 'right', or None"
                    )
            pose = self._sample_pose(
                occupied,
                radius,
                xlim=xlim,
                ylim=(-0.22, 0.06),
                qpos=entry["rest_qpos"],
                rotate_rand=entry["rotate_rand"],
                rotate_lim=entry["rotate_lim"],
            )
            if pose is None:
                raise UnStableError(
                    f"pick_diverse_object: no free spot for {asset} "
                    f"(placement radius {radius:.3f})"
                )

            # Preserve the previously verified bottle mixture and arm-directed lying pose.
            if entry["grasp_strategy"] == "bottle":
                upright = rng.random() < 0.5
                if upright:
                    base = [0.66, 0.66, -0.25, -0.25]
                    jitter = t3d.euler.euler2quat(0, rng.uniform(-1, 1), 0)
                else:
                    base = (
                        [0.707, 0.0, 0.0, 0.707]
                        if pose.p[0] > 0
                        else [0.707, 0.0, 0.0, -0.707]
                    )
                    jitter = t3d.euler.euler2quat(0, 0, rng.uniform(-0.4, 0.4))
                quat = t3d.quaternions.qmult(base, jitter)
                pose = sapien.Pose(
                    [float(pose.p[0]), float(pose.p[1]), float(pose.p[2])],
                    quat,
                )
                if is_target:
                    self._target_bottle_upright = upright

            actor_kwargs = {}
            if "scale" in entry:
                actor_kwargs["scale"] = entry["scale"]
            actor = create_actor(
                self,
                pose=pose,
                modelname=asset,
                convex=True,
                model_id=model_id,
                is_static=False,
                **actor_kwargs,
            )
            if actor is None:
                raise UnStableError(f"pick_diverse_object: failed to place {asset}")
            if "actor_config" in entry:
                # Some manual candidates have meshes but no usable asset metadata.
                # Keep the third-party JSON untouched and give each episode its own
                # grasp config so Actor.get_point() can apply the explicit scale.
                actor.config = deepcopy(entry["actor_config"])
            occupied.append((np.asarray(pose.p[:2], dtype=float), radius))
            self.add_prohibit_area(
                actor if actor.config is not None else actor.get_pose(),
                padding=max(0.04, radius),
            )

            spawn_pose = actor.get_pose()
            record = {
                "actor": actor,
                "noun": noun,
                "modelname": asset,
                "model_id": model_id,
                "role": "target" if is_target else "distractor",
                "familiarity": familiarity,
                "placement_index": len(self.scene_objects),
                "spawn_position": tuple(float(value) for value in spawn_pose.p),
                "spawn_quaternion": tuple(float(value) for value in spawn_pose.q),
            }
            self.scene_objects.append(record)
            tag = f"{noun}/{asset}base{model_id}"
            if is_target:
                self.target = actor
                self.target_modelname = asset
                self.target_id = model_id
                self.target_entry = entry
            else:
                self.distractors.append(record)
                self.distractor_info.append(tag)

        self.delay(2)
        self.target_origin_z = float(self.target.get_pose().p[2])

    def play_once(self):
        self.info["target"] = (
            f"{self.target_noun}/{self.target_modelname}base{self.target_id}"
        )
        self.info["target_noun"] = self.target_noun
        self.info["target_asset"] = self.target_modelname
        self.info["target_model_id"] = int(self.target_id)
        self.info["target_familiarity"] = self.target_familiarity
        self.info["scene_familiarity"] = self.scene_familiarity
        self.info["scene_objects"] = [
            {
                "noun": item["noun"],
                "asset": item["modelname"],
                "model_id": int(item["model_id"]),
                "role": item["role"],
                "familiarity": item["familiarity"],
                "placement_index": int(item["placement_index"]),
            }
            for item in self.scene_objects
        ]
        self.info["placement_policy"] = self.placement_policy
        self.info["placement_sequence"] = [
            item["noun"] for item in self.scene_objects
        ]
        self.info["distractors"] = list(self.distractor_info)

        arm_tag = ArmTag("right" if self.target.get_pose().p[0] > 0 else "left")
        strategy = self.target_entry["grasp_strategy"]
        kwargs = dict(self.target_entry["grasp_kwargs"])
        kwargs.update(
            self.target_entry.get("grasp_kwargs_by_arm", {}).get(str(arm_tag), {})
        )
        if strategy == "cup":
            kwargs["contact_point_id"] = [0, 2][int(arm_tag == "left")]
        elif strategy == "shoe":
            kwargs["gripper_pos"] = 0
        elif strategy == "bottle":
            kwargs["pre_grasp_dis"] = 0.08 if self._target_bottle_upright else 0.1
        grasp = self.grasp_actor(self.target, arm_tag=arm_tag, **kwargs)
        self.move(grasp)
        # World-z works for both top and side grasps; arm-axis lift does not.
        self.move(self.move_by_displacement(arm_tag, z=0.12))

        # Literal noun phrase (no '/') is substituted verbatim by RoboTwin.
        self.info["info"] = {"{A}": f"the {self.target_noun}", "{a}": str(arm_tag)}
        return self.info

    def check_success(self):
        return named_object_lifted_and_held(
            self,
            self.target,
            self.target_modelname,
            self.target_origin_z,
        )
