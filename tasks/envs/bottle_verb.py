from ._base_task import Base_Task
from ._if_eval import apply_if_eval_step_limit
from .utils import *
import sapien
import math


class bottle_verb(Base_Task):
    """IF-Verb-Select v2: one env, the instruction verb (pick vs shake) selects the task.

    Both verbs are native RoboTwin actions on 001_bottle (pick_* = pick, shake_bottle
    = shake), so BOTH are in a native-trained model's repertoire — the seen-vs-seen
    design that keeps this a clean instruction-following test under every eval
    protocol (unlike laptop_verb's OOD close). Cost: weak habitual prior.

    Scene and verb are DECOUPLED through the seed so the same bottle scene appears
    under both verbs (pixel-identical initial frames, only the verb differs):
        scene_seed = seed // 2 ,  mode = ["pick","shake"][seed % 2]

    THE CRUX: pick and shake share the same end-state ("bottle held in the air") —
    native shake's own check is just bottle.z>0.8, which can't tell them apart. So
    success keys on the TRAJECTORY:
      - pick  = bottle reaches a HIGH z that a shake never reaches (a positive
                end-state, robust to eval's first-True latching).
      - shake = the bottle's cumulative vertical travel over the episode exceeds a
                threshold (oscillation), accumulated in _record() which runs both in
                the oracle play_once (collection) and in check_success (eval, called
                every physics substep).
    NOTE: check_success is pair-gated UNIFORMLY (collection AND eval) — a seed's
    success counts only if the OTHER verb is oracle-feasible on the SAME scene, so
    an unpairable scene is dropped entirely (both seeds fail) and collection/eval
    use the identical set of two-way-doable scenes. The partner is trial-run by the
    oracle (cached per scene_seed), so the gate reflects SCENE feasibility, not the
    policy. Cost: a second sapien.Engine runs once per episode when _raw_success
    first passes (during eval too) — eval must use the validated pairable seed set.
    """

    ALLOWED_MODEL_IDS = list(range(20))  # native tasks use range(20); narrow via sweep if needed
    PICK_LIFT = 0.2         # pick lifts distinctly higher than shake's ~0.1
    PICK_HIGH = 0.95        # pick success: bottle.z above this (above shake's peak); tune from spike
    SHAKE_TRAVEL = 0.30     # shake success: cumulative |Δz| above this (pick monotonic ~0.2, shake ~0.4)

    # Pair-gate cache (class-level, per scene_seed): "is the OTHER verb also
    # oracle-feasible on this scene?". Applied uniformly in collection AND eval so
    # both use the same set of scenes where BOTH verbs are achievable.
    _pair_ok = {}

    def setup_demo(self, **kwags):
        self._seed = kwags.get("seed", 0)
        self._demo_kwargs = dict(kwags)  # so the partner trial-run rebuilds an identical env
        super()._init_task_env_(**kwags)
        apply_if_eval_step_limit(self)

    def load_actors(self):
        # Decouple scene from verb: scene depends only on seed//2 so (2k,2k+1) share
        # one bottle scene; the verb comes from seed%2.
        scene_seed = self._seed // 2
        np.random.seed(scene_seed)
        self.mode = ["pick", "shake"][self._seed % 2]

        # Bottle pose (mirror native shake_bottle: keep |x|>=0.1 so the arm is unambiguous).
        rand_pos = rand_pose(xlim=[-0.15, 0.15], ylim=[-0.15, -0.05], zlim=[0.785],
                             qpos=[0, 0, 1, 0], rotate_rand=True, rotate_lim=[0, 0, np.pi / 4])
        while abs(rand_pos.p[0]) < 0.1:
            rand_pos = rand_pose(xlim=[-0.15, 0.15], ylim=[-0.15, -0.05], zlim=[0.785],
                                 qpos=[0, 0, 1, 0], rotate_rand=True, rotate_lim=[0, 0, np.pi / 4])
        self.model_name = "001_bottle"
        self.bottle_id = int(np.random.choice(self.ALLOWED_MODEL_IDS))
        self.bottle = create_actor(scene=self, pose=rand_pos, modelname=self.model_name,
                                   convex=True, model_id=self.bottle_id)
        self.bottle.set_mass(0.01)
        self.add_prohibit_area(self.bottle, padding=0.05)

        # Trajectory accumulators (reset per episode) — read by _raw_success.
        self._z_prev = None
        self._z_cum = 0.0     # cumulative |Δz| over the episode (oscillation signal)
        self._z_peak = rand_pos.p[2]

    PICK_VERBS = ["pick up", "grab", "lift"]
    SHAKE_VERBS = ["shake"]

    def _verb(self):
        pool = self.PICK_VERBS if self.mode == "pick" else self.SHAKE_VERBS
        return pool[(self._seed // 2) % len(pool)]

    def _record(self):
        """Update trajectory accumulators from the bottle's current z. Called after
        each move in the oracle play_once (collection) AND at the top of check_success
        (eval, every substep) so the oscillation signal is populated in both paths."""
        z = float(self.bottle.get_pose().p[2])
        if self._z_prev is not None:
            self._z_cum += abs(z - self._z_prev)
        self._z_prev = z
        if z > self._z_peak:
            self._z_peak = z

    def play_once(self):
        arm_tag = ArmTag("right" if self.bottle.get_pose().p[0] > 0 else "left")
        self.arm_tag = arm_tag
        self._z_prev = float(self.bottle.get_pose().p[2])

        # Grasp the bottle (free/center grasp, same as native).
        self.move(self.grasp_actor(self.bottle, arm_tag=arm_tag, pre_grasp_dis=0.1))
        self._record()

        if self.mode == "pick":
            # Lift HIGH and hold — reaches a z a shake never does. Reuse shake's
            # proven reorient-lift (z=0.1 + upright wrist quat), then continue up.
            target_quat = [0.707, 0, 0, 0.707]
            self.move(self.move_by_displacement(arm_tag=arm_tag, z=0.1, quat=target_quat))
            self._record()
            self.move(self.move_by_displacement(arm_tag=arm_tag, z=self.PICK_LIFT - 0.1, quat=target_quat))
            self._record()
        else:
            # Shake: reuse native shake_bottle motion verbatim (lift + ±7π/8 y-swings x3).
            target_quat = [0.707, 0, 0, 0.707]
            self.move(self.move_by_displacement(arm_tag=arm_tag, z=0.1, quat=target_quat))
            self._record()
            quat1, quat2 = deepcopy(target_quat), deepcopy(target_quat)
            yq = t3d.euler.euler2quat(0, (np.pi / 8) * 7, 0)
            rq = t3d.quaternions.qmult(yq, quat1)
            quat1 = [-rq[1], rq[0], rq[3], -rq[2]]
            yq = t3d.euler.euler2quat(0, -7 * (np.pi / 8), 0)
            rq = t3d.quaternions.qmult(yq, quat2)
            quat2 = [-rq[1], rq[0], rq[3], -rq[2]]
            for _ in range(3):
                self.move(self.move_by_displacement(arm_tag=arm_tag, z=0.05, quat=quat1))
                self._record()
                self.move(self.move_by_displacement(arm_tag=arm_tag, z=-0.05, quat=quat2))
                self._record()
            self.move(self.move_by_displacement(arm_tag=arm_tag, quat=target_quat))
            self._record()

        self.info["mode"] = self.mode
        self.info["info"] = {
            "{A}": f"{self.model_name}/base{self.bottle_id}",
            "{a}": str(arm_tag),
            "{V}": self._verb(),
        }
        return self.info

    def _raw_success(self, mode):
        """Pure single-direction check (no side effects). Reads the trajectory
        accumulators updated by _record()."""
        if mode == "pick":
            return self._z_peak > self.PICK_HIGH + self.table_z_bias
        return self._z_cum >= self.SHAKE_TRAVEL

    def _partner_ok(self):
        """Is the OTHER verb oracle-feasible on this SAME scene? Trial-run the
        partner seed's oracle in a throwaway instance, cached per scene_seed. A
        scene counts as a valid test case only if BOTH verbs are achievable, so an
        unpairable scene fails entirely (both seeds dropped) — in collection AND
        eval, keeping the two sets identical. The trial calls only _raw_success
        (never this gated check_success) and play_once has no check_success call,
        so there is no recursion."""
        scene_seed = self._seed // 2
        if scene_seed not in bottle_verb._pair_ok:
            partner_seed = scene_seed * 2 + (1 - self._seed % 2)
            buddy = bottle_verb()
            ok = False
            try:
                kw = dict(self._demo_kwargs)
                kw["seed"] = partner_seed  # same scene_seed -> same bottle, other verb
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
            bottle_verb._pair_ok[scene_seed] = ok
        return bottle_verb._pair_ok[scene_seed]

    def check_success(self):
        # Record every call so eval (which polls check_success every physics substep)
        # accumulates the full trajectory.
        self._record()
        if not self._raw_success(self.mode):
            return False
        # Scene-validity pair-gate (uniform, collection AND eval): this verb
        # succeeded AND the partner verb is oracle-feasible on this scene. The buddy
        # runs at most once per episode (right when _raw_success first passes) and
        # is cached. NOTE: this runs the oracle buddy during eval too (a second
        # sapien.Engine, once per episode) — eval must be run on the validated
        # pairable seed set, else a non-pairable scene reads as a policy failure.
        return bool(self._raw_success(self.mode)) and self._partner_ok()

