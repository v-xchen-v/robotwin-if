"""Experimental Press/Lift contrast on one shared dynamic native stapler."""
import random

import numpy as np
import sapien

from ._base_task import Base_Task
from ._press_lift_bell import (CONTEXT_LAYOUT_VERSION, bell_contacts, mode_for_seed,
                              sample_context_positions)
from ._press_lift_stapler import (INSTRUCTIONS, MODEL_IDS, PRESS_CONTACT_POINT, ROTATION_VERSION,
                                 StaplerMonitor, sample_rotations, stapler_rules)
from .utils import ArmTag, create_actor


class press_lift_stapler(Base_Task):
    ACTION_LIMIT = 250
    MODEL_IDS = MODEL_IDS

    def setup_demo(self, **kwargs):
        self._detach_observer()
        episode_seed = kwargs.get("seed", 0)
        self.mode = mode_for_seed(episode_seed)
        self.scene_seed = episode_seed // 2
        self.trace_callback = None
        self.scene_layout = kwargs.pop("stapler_scene_layout", "context")
        if self.scene_layout not in ("bare", "context"):
            raise ValueError(f"Unknown stapler scene layout: {self.scene_layout}")
        self.rotations = sample_rotations(self.scene_seed)
        random.seed(self.scene_seed)
        super()._init_task_env_(**dict(kwargs, seed=self.scene_seed))
        if self.eval_mode:
            self.step_lim = self.ACTION_LIMIT
        self.initial_position = self.stapler.get_pose().p.copy()
        self.initial_quaternion = self.stapler.get_pose().q.copy()
        self.context_initial_positions = {a.get_name(): a.get_pose().p.tolist() for a in self.context_objects}
        self.context_initial_quaternions = {a.get_name(): a.get_pose().q.tolist() for a in self.context_objects}
        self.monitor = StaplerMonitor(stapler_rules(round(float(self.scene.get_timestep()), 9)))
        self._simulation_time = 0.0
        self.native_press_first_time = None
        self._gripper_names = {}
        for arm in ("left", "right"):
            names = list(getattr(self.robot, f"{arm}_fix_gripper_name"))
            names.extend(g[0].child_link.get_name() for g in getattr(self.robot, f"{arm}_gripper"))
            self._gripper_names[arm] = set(names)
        self._attach_observer()

    def load_actors(self):
        self.stapler_id = self.MODEL_IDS[(self.scene_seed // 2) % len(self.MODEL_IDS)]
        side = -1 if self.scene_seed % 2 == 0 else 1
        self.arm_tag = ArmTag("left" if side < 0 else "right")
        pose = sapien.Pose([side * np.random.uniform(0.14, 0.19), np.random.uniform(-0.15, -0.10), 0.74],
                           self.rotations["048_stapler"]["quaternion"])
        self.spawn_position = pose.p.tolist()
        self.stapler = create_actor(self, pose, modelname="048_stapler", model_id=self.stapler_id,
                                    convex=True, is_static=False)
        self.stapler.set_mass(0.05)
        self.add_prohibit_area(self.stapler, padding=0.07)
        self.context_objects = []
        self.context_spawn_positions = {}
        if self.scene_layout == "context":
            for asset, position in sample_context_positions(self.scene_seed, pose.p[:2]):
                actor = create_actor(self, sapien.Pose(position, self.rotations[asset]["quaternion"]),
                                     modelname=asset, model_id=0, convex=True, is_static=False)
                actor.set_mass(0.05)
                self.add_prohibit_area(actor, padding=0.04)
                self.context_objects.append(actor)
                self.context_spawn_positions[asset] = list(position)

    def _physical_signals(self):
        cp = np.asarray(self.stapler.get_contact_point(PRESS_CONTACT_POINT)[:3])
        supported, arms = bell_contacts(self.scene.get_contacts(), self.stapler.get_name(), self.table.get_name(),
                                        self._gripper_names, cp, self.monitor.rules)
        for arm in arms:
            arms[arm].update(closed=bool(getattr(self, f"is_{arm}_gripper_close")()),
                             ee_z=float(self.get_arm_pose(ArmTag(arm))[2]))
        position = self.stapler.get_pose().p
        return (float(position[2] - self.initial_position[2]),
                float(np.linalg.norm(position[:2] - self.initial_position[:2])), supported, arms)

    def _attach_observer(self):
        scene, original = self.scene, self.scene.step

        def observed_step():
            result = original()
            self._simulation_time += float(scene.get_timestep())
            signals = self._physical_signals()
            # The native diagnostic only requires contact near point 2, without
            # the action classifier's already-closed downward approach gate.
            if self.native_press_first_time is None and any(a["top_touch"] for a in signals[3].values()):
                self.native_press_first_time = self._simulation_time
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
                    native_press_success=self.native_press_first_time is not None,
                    native_press_first_time=self.native_press_first_time,
                    press_contact_point=PRESS_CONTACT_POINT, stapler_id=self.stapler_id,
                    scene_layout=self.scene_layout, target_is_static=False, target_mass_kg=0.05,
                    context_sampling_version=CONTEXT_LAYOUT_VERSION if self.scene_layout == "context" else None,
                    rotation_sampling_version=ROTATION_VERSION,
                    context_objects=[dict(name=a.get_name(), position=a.get_pose().p.tolist(),
                                          initial_position=self.context_initial_positions[a.get_name()],
                                          spawn_position=self.context_spawn_positions[a.get_name()],
                                          quaternion=a.get_pose().q.tolist(),
                                          initial_quaternion=self.context_initial_quaternions[a.get_name()],
                                          spawn_quaternion=self.rotations[a.get_name()]["quaternion"],
                                          yaw_degrees=self.rotations[a.get_name()]["yaw_degrees"])
                                     for a in self.context_objects],
                    stapler_position=self.stapler.get_pose().p.tolist(),
                    initial_position=self.initial_position.tolist(), spawn_position=self.spawn_position,
                    stapler_quaternion=self.stapler.get_pose().q.tolist(),
                    initial_quaternion=self.initial_quaternion.tolist(),
                    spawn_quaternion=self.rotations["048_stapler"]["quaternion"],
                    stapler_yaw_degrees=self.rotations["048_stapler"]["yaw_degrees"],
                    verdict_protocol="first-completed-action",
                    policy_action_count=self.take_action_cnt, policy_action_limit=self.step_lim)

    def play_once(self):
        if self.mode == "press":
            self.move(self.grasp_actor(self.stapler, arm_tag=self.arm_tag, pre_grasp_dis=0.1,
                                       grasp_dis=0.1, contact_point_id=PRESS_CONTACT_POINT))
            self.move(self.close_gripper(arm_tag=self.arm_tag))
            # Native press_stapler closes above point 2 and approaches by 8 cm.
            # Stop at observed contact so the shared dynamic target is not ejected.
            approach = np.asarray(self.get_arm_pose(self.arm_tag)).copy()
            for step in range(40):
                if self.monitor.arms[str(self.arm_tag)]["candidate"] is not None:
                    break
                target = approach.copy()
                target[2] -= 0.002 * (step + 1)
                # Use absolute waypoints: measured-pose-relative 2 mm moves
                # accumulate tracking shortfall and can stop above the head.
                self.move(self.move_to_pose(self.arm_tag, target))
            self.move(self.move_by_displacement(self.arm_tag, z=0.06))
        else:
            # The grasp/lift prefix of native move_stapler_pad; no placement target.
            self.move(self.grasp_actor(self.stapler, arm_tag=self.arm_tag, pre_grasp_dis=0.1))
            self.move(self.move_by_displacement(self.arm_tag, z=0.10))
        for _ in range(round(0.3 / self.scene.get_timestep())):
            self.scene.step()
        self.info.update(mode=self.mode, scene_seed=self.scene_seed, stapler_id=self.stapler_id,
                         oracle_plan_success=bool(self.plan_success),
                         instruction=INSTRUCTIONS[self.mode], signals=self.eval_signals())
        self.info["info"] = {"{I}": INSTRUCTIONS[self.mode]}
        return self.info
