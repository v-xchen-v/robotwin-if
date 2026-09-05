from ._base_task import Base_Task
from .utils import *
import sapien
import numpy as np


class laptop_verb(Base_Task):
    """IF-Verb-Select: one env, the instruction verb (open vs close) selects the task.

    Same laptop scene from a shared ~50% mid-state; the verb picks the direction
    and the success criterion. Scene and verb are DECOUPLED through the seed so the
    same physical scene appears under BOTH verbs:

        scene_seed = seed // 2      # identical for the consecutive pair (2k, 2k+1)
        mode       = ["open","close"][seed % 2]

    So eval seeds (0,1),(2,3),... give scene #0,#1,... each once opening and once
    closing, with pixel-identical initial frames — the only difference the policy
    sees is the verb. Reliable variant subset {1,9} and thresholds (open >=70%,
    close <=20%) come from the oracle feasibility sweep
    (tests/laptop_verb/sweep_per_variant.py).
    """

    INIT_OPEN = 0.5
    OPEN_TARGET = 0.70
    # Close band. The twist-free fold (see _close_fold_action) settles at ~12-15%
    # rather than ~0%, so 0.15 left almost no margin (one episode landed 15.1% and
    # failed). 0.20 keeps a clear ~5-8% margin while still clearly "closed" vs the
    # 50% start; the reversal (opened ~78%) is nowhere near it.
    CLOSE_TARGET = 0.20
    ALLOWED_MODEL_IDS = [1, 9]
    # {V} verb pools (unambiguous for a laptop lid; avoid raise/lift/lower which
    # could read as lifting the whole device). Picked deterministically from
    # scene_seed so the instruction reproduces across eval's two setup passes.
    OPEN_VERBS = ["open"]
    CLOSE_VERBS = ["close", "shut"]

    # Pair-gate cache (class-level, survives across episodes in one process).
    # key = scene_seed (self._seed // 2); value = "is the OTHER verb also doable
    # on this scene?". Shared by the open and close episodes of a pair, so the
    # partner direction is trial-run at most once per scene.
    _pair_ok = {}

    def setup_demo(self, **kwags):
        # Capture seed so mode/scene can be derived purely from it. Also stash the
        # full demo kwargs so a partner trial-run (see check_success) can rebuild
        # an identical embodiment/camera/config env.
        self._seed = kwags.get("seed", 0)
        self._demo_kwargs = dict(kwags)
        super()._init_task_env_(**kwags)

    def load_actors(self):
        # Decouple scene from verb: the scene depends only on seed//2 so the pair
        # (2k, 2k+1) share one scene; the verb comes from seed%2. Re-seed here to
        # override _init_task_env_'s raw-seed seeding for the laptop sampling.
        scene_seed = self._seed // 2
        np.random.seed(scene_seed)
        self.mode = ["open", "close"][self._seed % 2]

        self.model_name = "015_laptop"
        self.model_id = int(np.random.choice(self.ALLOWED_MODEL_IDS))
        self.laptop: ArticulationActor = rand_create_sapien_urdf_obj(
            scene=self,
            modelname=self.model_name,
            modelid=self.model_id,
            xlim=[-0.05, 0.05],
            ylim=[-0.1, 0.05],
            rotate_rand=True,
            rotate_lim=[0, 0, np.pi / 3],
            qpos=[0.7, 0, 0, 0.7],
            fix_root_link=True,
        )
        limit = self.laptop.get_qlimits()[0]
        self.laptop.set_qpos([limit[0] + (limit[1] - limit[0]) * self.INIT_OPEN])
        self.laptop.set_mass(0.01)
        self.laptop.set_properties(1, 0)
        self.add_prohibit_area(self.laptop, padding=0.1)

    def _verb(self):
        pool = self.OPEN_VERBS if self.mode == "open" else self.CLOSE_VERBS
        return pool[(self._seed // 2) % len(pool)]

    def _close_fold_action(self, arm_tag):
        """Close-fold target: point-3 POSITION (on the base, folds the lid down)
        combined with point-0 ORIENTATION (on the screen, co-rotates with the lid).

        Servoing to point 3 directly would drag the gripper to point 3's base-grasp
        orientation, which is ~110deg off the screen grasp -> an ugly wrist twist.
        Taking only point 3's position while re-reading the screen point's current
        orientation each step makes the gripper follow the natural fold (like the
        open servo does with point 1), with no extra twist. Orientation is held
        along the path (constraint_pose rot weights = 1), position is free.
        """
        pos = self.get_grasp_pose(self.laptop, arm_tag, contact_point_id=3, pre_dis=0.0)
        ori = self.get_grasp_pose(self.laptop, arm_tag, contact_point_id=0, pre_dis=0.0)
        if not pos or not ori or pos[0] == -1 or ori[0] == -1:
            return None
        target = list(pos[:3]) + list(ori[3:])
        return (arm_tag, [Action(arm_tag, "move", target_pose=target, constraint_pose=[1, 1, 1, 0, 0, 0])])

    def play_once(self):
        face_prod = get_face_prod(self.laptop.get_pose().q, [1, 0, 0], [1, 0, 0])
        arm_tag = ArmTag("left" if face_prod > 0 else "right")
        self.arm_tag = arm_tag

        # Grasp the screen (same contact point for both directions).
        self.move(self.grasp_actor(self.laptop, arm_tag=arm_tag, pre_grasp_dis=0.08, contact_point_id=0))

        # Direction-specific servo: open pulls the held screen point toward the
        # higher screen point 1; close folds toward the base point 3 but keeps the
        # screen's orientation (see _close_fold_action) so the wrist doesn't twist.
        # The hinge arc is emergent from the constraint in both cases.
        opening = self.mode == "open"
        start_qpos = self.laptop.get_qpos()[0]
        for _ in range(30):
            try:
                if opening:
                    action = self.grasp_actor(
                        self.laptop,
                        arm_tag=arm_tag,
                        pre_grasp_dis=0.0,
                        grasp_dis=0.0,
                        contact_point_id=1,
                    )
                else:
                    action = self._close_fold_action(arm_tag)
                    if action is None:
                        break
                self.move(action)
            except AssertionError:
                # At steep angles the servo grasp pose can be unplannable
                # (choose_grasp_pose -> None); stop gracefully at the last angle.
                break
            new_qpos = self.laptop.get_qpos()[0]
            progress = (new_qpos - start_qpos) if opening else (start_qpos - new_qpos)
            if progress <= 0.001:  # stalled in the intended direction
                break
            start_qpos = new_qpos
            if not self.plan_success:
                break
            if self._raw_success(self.mode):  # raw end-state, NOT the pair-gate
                break

        self.info["mode"] = self.mode
        self.info["info"] = {
            "{A}": f"{self.model_name}/base{self.model_id}",
            "{a}": str(arm_tag),
            "{V}": self._verb(),
        }
        return self.info

    def _raw_success(self, mode):
        """Pure single-direction end-state check: no side effects, no recursion.
        open -> hinge past OPEN_TARGET; close -> hinge at/below CLOSE_TARGET.
        This is the ONLY success predicate play_once and the partner trial-run
        may call — check_success (below) adds the pair-gate and must not be
        reached from inside a trial-run."""
        limit = self.laptop.get_qlimits()[0]
        frac = (self.laptop.get_qpos()[0] - limit[0]) / (limit[1] - limit[0])
        if mode == "open":
            return frac >= self.OPEN_TARGET
        return frac <= self.CLOSE_TARGET

    def check_success(self):
        """Pair-gated success (makes native collect_data emit only complete
        open/close scene pairs): this direction must succeed AND the SAME scene
        must also be doable in the OTHER direction. If the partner direction
        fails, the scene has no valid demo for that verb, so BOTH episodes are
        dropped (each returns False).

        The partner is trial-run once per scene_seed and cached on the class
        (survives across episodes in the process). The trial calls only
        _raw_success — NEVER this method — and play_once's internal early-break
        also uses _raw_success, so there is no recursion. The trial runs in a
        throwaway env instance and never touches this env's scene/arm state."""
        if not self._raw_success(self.mode):
            return False
        scene_seed = self._seed // 2
        if scene_seed not in laptop_verb._pair_ok:
            partner_seed = scene_seed * 2 + (1 - self._seed % 2)
            buddy = laptop_verb()
            ok = False
            try:
                kw = dict(self._demo_kwargs)
                kw["seed"] = partner_seed  # same scene_seed -> same scene, other verb
                buddy.setup_demo(**kw)
                buddy.play_once()
                ok = bool(buddy._raw_success(buddy.mode))
            except Exception:
                ok = False
            finally:
                try:
                    buddy.close_env()
                except Exception:
                    pass
            laptop_verb._pair_ok[scene_seed] = ok
        return self._raw_success(self.mode) and laptop_verb._pair_ok[scene_seed]
