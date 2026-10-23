"""Isolated press/lift pair on one shared dynamic bell, outside the formal suite."""
import random
import numpy as np
import sapien

from ._base_task import Base_Task
from ._press_lift_bell import BellMonitor, INSTRUCTIONS, mode_for_seed
from .utils import ArmTag, create_actor


class press_lift_bell(Base_Task):
    ACTION_LIMIT = 250
    MODEL_IDS = (0, 1)

    def setup_demo(self, **kwargs):
        self._detach_observer()
        self.mode = mode_for_seed(kwargs.get("seed", 0))
        self.scene_seed = kwargs.get("seed", 0) // 2
        self.trace_callback = None
        random.seed(self.scene_seed)
        super()._init_task_env_(**dict(kwargs, seed=self.scene_seed))
        if self.eval_mode:
            self.step_lim = self.ACTION_LIMIT
        self.initial_position = self.bell.get_pose().p.copy()
        self.monitor = BellMonitor()
        self._simulation_time = self._sample_time = 0.0
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

    def _physical_signals(self):
        arms = {arm: dict(closed=bool(getattr(self, f"is_{arm}_gripper_close")()),
                         ee_z=float(self.get_arm_pose(ArmTag(arm))[2]), touching=False,
                         top_touch=False, contact_links=[]) for arm in ("left", "right")}
        cp = np.asarray(self.bell.get_contact_point(0)[:3])
        supported = False
        for contact in self.scene.get_contacts():
            names = [body.entity.name for body in contact.bodies]
            if self.bell.get_name() not in names:
                continue
            other = names[1] if names[0] == self.bell.get_name() else names[0]
            points = [p for p in contact.points if np.linalg.norm(p.impulse) > 1e-7]
            if not points:
                continue
            if other == self.table.get_name():
                supported = True
            for arm, gripper_names in self._gripper_names.items():
                if other not in gripper_names:
                    continue
                arms[arm]["touching"] = True
                arms[arm]["contact_links"].append(other)
                for point in points:
                    d = np.abs(np.asarray(point.position) - cp)
                    if np.all(d[:2] < self.monitor.rules.top_xy_m) and d[2] < self.monitor.rules.top_z_m:
                        arms[arm]["top_touch"] = True
        p = self.bell.get_pose().p
        return float(p[2] - self.initial_position[2]), float(np.linalg.norm(p[:2] - self.initial_position[:2])), supported, arms

    def _attach_observer(self):
        scene, original = self.scene, self.scene.step
        def observed_step():
            result = original()
            self._simulation_time += float(scene.get_timestep())
            if self._simulation_time - self._sample_time + 1e-9 >= self.monitor.rules.sample_seconds:
                self._sample_time = self._simulation_time
                self.monitor.observe(self._simulation_time, *self._physical_signals())
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
                    bell_id=self.bell_id, bell_position=self.bell.get_pose().p.tolist(),
                    initial_position=self.initial_position.tolist(), verdict_protocol="first-completed-action",
                    policy_action_count=self.take_action_cnt, policy_action_limit=self.step_lim)

    def play_once(self):
        if self.mode == "press":
            self.move(self.grasp_actor(self.bell, arm_tag=self.arm_tag, pre_grasp_dis=0.1,
                                       grasp_dis=0.1, contact_point_id=0))
            self.move(self.move_by_displacement(self.arm_tag, z=-0.045))
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
