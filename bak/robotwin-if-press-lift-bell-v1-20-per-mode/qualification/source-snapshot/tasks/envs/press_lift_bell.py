"""Press/lift instruction contrast on one shared dynamic bell scene."""
import random
import numpy as np
import sapien

from ._base_task import Base_Task
from ._press_lift_bell import (BellMonitor, BellRules, CONTEXT_LAYOUT_VERSION, INSTRUCTIONS,
                              bell_contacts, mode_for_seed, sample_context_positions)
from .utils import ArmTag, create_actor


class press_lift_bell(Base_Task):
    ACTION_LIMIT = 250
    MODEL_IDS = (0, 1)

    def setup_demo(self, **kwargs):
        self._detach_observer()
        self.mode = mode_for_seed(kwargs.get("seed", 0))
        self.scene_seed = kwargs.get("seed", 0) // 2
        self.trace_callback = None
        self.scene_layout = kwargs.pop("bell_scene_layout", "context")
        if self.scene_layout not in ("bare", "context"):
            raise ValueError(f"Unknown bell scene layout: {self.scene_layout}")
        random.seed(self.scene_seed)
        super()._init_task_env_(**dict(kwargs, seed=self.scene_seed))
        if self.eval_mode:
            self.step_lim = self.ACTION_LIMIT
        self.initial_position = self.bell.get_pose().p.copy()
        self.context_initial_positions = {a.get_name(): a.get_pose().p.tolist() for a in self.context_objects}
        self.monitor = BellMonitor(BellRules(sample_seconds=round(float(self.scene.get_timestep()), 9)))
        self._simulation_time = 0.0
        self.native_click_first_time = None
        self._gripper_names = {}
        for arm in ("left", "right"):
            names = list(getattr(self.robot, f"{arm}_fix_gripper_name"))
            names.extend(g[0].child_link.get_name() for g in getattr(self.robot, f"{arm}_gripper"))
            self._gripper_names[arm] = set(names)
        self._attach_observer()

    def load_actors(self):
        self.bell_id = self.MODEL_IDS[(self.scene_seed // 2) % len(self.MODEL_IDS)]
        side = -1 if self.scene_seed % 2 == 0 else 1
        self.arm_tag = ArmTag("left" if side < 0 else "right")
        pose = sapien.Pose([side * np.random.uniform(0.14, 0.19), np.random.uniform(-0.15, -0.10), 0.74],
                           [0.5, 0.5, 0.5, 0.5])
        self.bell = create_actor(self, pose, modelname="050_bell", model_id=self.bell_id,
                                 convex=True, is_static=False)
        self.bell.set_mass(0.05)
        self.add_prohibit_area(self.bell, padding=0.07)
        self.context_objects = []
        if self.scene_layout == "context":
            # Both assets can occupy either side. One local scene-seeded sampler
            # preserves paired scenes and the rest of the task's random streams.
            for asset, position in sample_context_positions(self.scene_seed, pose.p[:2]):
                actor = create_actor(self, sapien.Pose(position, [0.5] * 4),
                                     modelname=asset, model_id=0, convex=True, is_static=False)
                actor.set_mass(0.05)
                self.add_prohibit_area(actor, padding=0.04)
                self.context_objects.append(actor)

    def _physical_signals(self):
        cp = np.asarray(self.bell.get_contact_point(0)[:3])
        supported, arms = bell_contacts(self.scene.get_contacts(), self.bell.get_name(), self.table.get_name(),
                                        self._gripper_names, cp, self.monitor.rules)
        for arm in arms:
            arms[arm].update(closed=bool(getattr(self, f"is_{arm}_gripper_close")()),
                             ee_z=float(self.get_arm_pose(ArmTag(arm))[2]))
        p = self.bell.get_pose().p
        return float(p[2] - self.initial_position[2]), float(np.linalg.norm(p[:2] - self.initial_position[:2])), supported, arms

    def _attach_observer(self):
        scene, original = self.scene, self.scene.step
        def observed_step():
            result = original()
            self._simulation_time += float(scene.get_timestep())
            signals = self._physical_signals()
            arms = signals[3]
            if (self.native_click_first_time is None and arms[str(self.arm_tag)]["closed"]
                    and any(a["top_touch"] for a in arms.values())):
                self.native_click_first_time = self._simulation_time
            self.monitor.observe(self._simulation_time, *signals)
            if self.trace_callback is not None:
                self.trace_callback(self)
            return result
        self._observer = scene, original, observed_step
        scene.step = observed_step

    def _detach_observer(self):
        observer = getattr(self, "_observer", None)
        if observer is not None:
            scene, original, installed = observer
            if scene.step is installed:
                scene.step = original
            self._observer = None

    def close_env(self, clear_cache=False):
        self._detach_observer()
        self.trace_callback = None
        return super().close_env(clear_cache=clear_cache)

    def policy_instruction(self, split):
        if split not in ("seen", "unseen"):
            raise ValueError("This experiment requires the explicit press/lift instruction")
        return INSTRUCTIONS[self.mode]

    def check_success(self):
        return self.monitor.success(self.mode)

    def eval_signals(self):
        return dict(self.monitor.signals(), mode=self.mode, scene_seed=self.scene_seed,
                    contact_protocol="native-all-contact-points", sampling_protocol="every-physics-step",
                    native_click_success=self.native_click_first_time is not None,
                    native_click_first_time=self.native_click_first_time,
                    bell_id=self.bell_id, scene_layout=self.scene_layout,
                    context_sampling_version=CONTEXT_LAYOUT_VERSION if self.scene_layout == "context" else None,
                    context_objects=[dict(name=a.get_name(), position=a.get_pose().p.tolist(),
                                          initial_position=self.context_initial_positions[a.get_name()])
                                     for a in self.context_objects],
                    bell_position=self.bell.get_pose().p.tolist(),
                    initial_position=self.initial_position.tolist(), verdict_protocol="first-completed-action",
                    policy_action_count=self.take_action_cnt, policy_action_limit=self.step_lim)

    def play_once(self):
        if self.mode == "press":
            self.move(self.grasp_actor(self.bell, arm_tag=self.arm_tag, pre_grasp_dis=0.1,
                                       grasp_dis=0.1, contact_point_id=0))
            # Native fixed-depth pressing can eject a dynamic bell. Approach
            # slowly and stop at contact; this feedback belongs to the oracle only.
            self.move(self.move_by_displacement(self.arm_tag, z=-0.025))
            for _ in range(15):
                if self.monitor.arms[str(self.arm_tag)]["candidate"] is not None:
                    break
                self.move(self.move_by_displacement(self.arm_tag, z=-0.002))
            self.move(self.move_by_displacement(self.arm_tag, z=0.06))
        else:
            self.move(self.grasp_actor(self.bell, arm_tag=self.arm_tag))
            self.move(self.move_by_displacement(self.arm_tag, z=0.10))
        for _ in range(round(0.3 / self.scene.get_timestep())):
            self.scene.step()
        self.info.update(mode=self.mode, scene_seed=self.scene_seed, bell_id=self.bell_id,
                         instruction=INSTRUCTIONS[self.mode], signals=self.eval_signals())
        self.info["info"] = {"{I}": INSTRUCTIONS[self.mode]}
        return self.info
