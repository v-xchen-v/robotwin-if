from ._base_task import Base_Task
from ._if_eval import apply_if_eval_step_limit
from ._if_bottle_verb import PickHoldMonitor, PickHoldRules
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

    Pick allows translation above the relative lift threshold, with a tolerant
    orientation hold. Angular excursions reset the hold; repeated rotation
    reversals veto pick for the rest of the episode. Policy pick is judged after
    the full action budget, never at the first transient hold. Hold duration
    advances only with physics steps. Shake retains its vertical-travel rule.
    NOTE: check_success is pair-gated UNIFORMLY (collection AND eval) — a seed's
    success counts only if the OTHER verb is oracle-feasible on the SAME scene, so
    an unpairable scene is dropped entirely (both seeds fail) and collection/eval
    use the identical set of two-way-doable scenes. The partner is trial-run by the
    oracle (cached per scene_seed), so the gate reflects SCENE feasibility, not the
    policy. On a cache miss, a second environment checks the partner when
    _raw_success first passes; formal eval qualifies the pair before rollout.
    """

    ALLOWED_MODEL_IDS = list(range(20))  # native tasks use range(20); narrow via sweep if needed
    PICK_LIFT = 0.2         # Preserve the existing oracle lift trajectory.
    PICK_RULES = PickHoldRules()
    SHAKE_TRAVEL = 0.30     # shake success: cumulative |Δz| above this (pick monotonic ~0.2, shake ~0.4)

    # Pair-gate cache (class-level, per scene_seed): "is the OTHER verb also
    # oracle-feasible on this scene?". Applied uniformly in collection AND eval so
    # both use the same set of scenes where BOTH verbs are achievable.
    _pair_ok = {}

    def setup_demo(self, **kwags):
        self._detach_pick_observer()
        self._pick_monitor = None
        self._pick_terminal_evaluation = False
        self._pick_verdict_finalized = False
        self._pick_verdict_success = None
        self._seed = kwags.get("seed", 0)
        self._demo_kwargs = dict(kwags)  # so the partner trial-run rebuilds an identical env
        super()._init_task_env_(**kwags)
        apply_if_eval_step_limit(self)
        # Capture the settled baseline in BOTH oracle and policy setups.
        self._pick_monitor = PickHoldMonitor(self.bottle.get_pose().p, self.PICK_RULES)
        self._pick_sim_time = 0.0
        self._attach_pick_observer()

    def _attach_pick_observer(self):
        # Local to this task instance; records physics, never polls/latches success.
        # RoboTwin has no step counter and check_success is also called without a
        # step. Hook the scene's real step to share one clock with oracle moves.
        scene = self.scene
        original_step = scene.step
        def observed_step():
            result = original_step()
            self._pick_sim_time += float(scene.get_timestep())
            pose = self.bottle.get_pose()
            self._pick_monitor.observe(self._pick_sim_time, pose.p, pose.q)
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

    def _hold_pick_oracle(self):
        # Hold the existing robot drive targets; no model actions or fake elapsed time.
        seconds = self.PICK_RULES.hold_seconds + 0.25
        for i in range(math.ceil(seconds / self.scene.get_timestep())):
            self.scene.step()
            if self.save_data and self.save_freq and i % self.save_freq == 0:
                self._update_render()
                self._take_picture()

    def eval_signals(self):
        return dict(self._pick_monitor.signals(), mode=self.mode,
                    pick_verdict_protocol='action-budget-end',
                    pick_terminal_evaluation=self._pick_terminal_evaluation,
                    pick_verdict_finalized=self._pick_verdict_finalized,
                    pick_final_success=self._pick_verdict_success,
                    pick_translation_allowed=True,
                    policy_action_count=getattr(self, 'take_action_cnt', 0),
                    policy_action_limit=getattr(self, 'step_lim', None),
                    shake_vertical_travel_m=self._z_cum,
                    shake_travel_threshold_m=self.SHAKE_TRAVEL)

    def start_policy_rollout(self):
        # Oracle/collection still checks the raw physical predicate. Only policy
        # pick rollouts defer their verdict; shake keeps its existing early stop.
        self._pick_terminal_evaluation = self.mode == 'pick'

    def finalize_policy_success(self):
        if not self._pick_terminal_evaluation:
            return bool(self.eval_success or self.check_success())
        if self.take_action_cnt != self.step_lim:
            raise RuntimeError('Pick verdict requires the complete action budget')
        self._record()
        result = bool(self._raw_success('pick') and self._partner_ok())
        self._pick_verdict_finalized = True
        self._pick_verdict_success = result
        return result

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
            # Keep the proven reorient/lift, then physically hold for the new check.
            target_quat = [0.707, 0, 0, 0.707]
            self.move(self.move_by_displacement(arm_tag=arm_tag, z=0.1, quat=target_quat))
            self._record()
            self.move(self.move_by_displacement(arm_tag=arm_tag, z=self.PICK_LIFT - 0.1, quat=target_quat))
            self._record()
            self._hold_pick_oracle()
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
        self.info["signals"] = self.eval_signals()
        self.info["info"] = {
            "{A}": f"{self.model_name}/base{self.bottle_id}",
            "{a}": str(arm_tag),
            "{V}": self._verb(),
        }
        return self.info

    def _raw_success(self, mode):
        """Read the physics-clock pick monitor or the unchanged shake accumulator."""
        if mode == "pick":
            return self._pick_monitor is not None and self._pick_monitor.success
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
        # Returning True here would stop inside take_action, possibly halfway
        # through the last action. The evaluator finalizes after it fully returns.
        if self._pick_terminal_evaluation:
            return False
        if not self._raw_success(self.mode):
            return False
        # Scene-validity pair-gate (uniform, collection AND eval): this verb
        # succeeded AND the partner verb is oracle-feasible on this scene. The buddy
        # runs on a scene cache miss (right when _raw_success first passes).
        # Formal evaluation qualifies the oracle pair before policy rollout,
        # so an infeasible scene is reported as a setup error, not policy failure.
        return bool(self._raw_success(self.mode)) and self._partner_ok()
