"""Experimental hold-above-pad / place-on-pad pair, outside the maintained suite."""

import itertools
import math
import random

import numpy as np
import sapien
import transforms3d as t3d

from ._base_task import Base_Task
from ._bottle_hold_place import HoldPlaceMonitor, INSTRUCTIONS, mode_for_seed
from .utils import ArmTag, create_actor, create_box


class bottle_hold_place(Base_Task):
    MODEL_IDS = (13, 16)
    ACTION_LIMIT = 700
    PAD_HALF_SIZE = (0.09, 0.09, 0.003)
    HOVER_CLEARANCE = 0.12

    def setup_demo(self, **kwargs):
        self._detach_observer()
        self._seed = kwargs.get("seed", 0)
        self.mode = mode_for_seed(self._seed)
        self.scene_seed = self._seed // 2
        self._terminal = False
        self._final_success = None
        self.trace_callback = None
        # Seed the ENTIRE setup by scene, including cameras, background and robot.
        # The command mode never consumes scene RNG or changes any actor.
        random.seed(self.scene_seed)
        setup = dict(kwargs, seed=self.scene_seed)
        super()._init_task_env_(**setup)
        if self.eval_mode:
            self.step_lim = self.ACTION_LIMIT
        self.monitor = HoldPlaceMonitor()
        self._simulation_time = self._sample_time = 0.0
        self._attach_observer()

    def load_actors(self):
        self.bottle_id = self.MODEL_IDS[(self.scene_seed // 2) % len(self.MODEL_IDS)]
        side = -1 if self.scene_seed % 2 == 0 else 1
        self.arm_tag = ArmTag("left" if side < 0 else "right")
        x = side * np.random.uniform(0.16, 0.21)
        y = np.random.uniform(-0.23, -0.21)
        # Reuse a demonstrated lying-bottle grasp, with a shared destination pad.
        yaw = t3d.euler.euler2quat(0, 0, np.random.uniform(-0.12, 0.12))
        quaternion = t3d.quaternions.qmult(yaw, [0, 0, 1, 0])
        self.bottle = create_actor(self, sapien.Pose([x, y, 0.795], quaternion),
                                   modelname="001_bottle", model_id=self.bottle_id, convex=True)
        self.pad = create_box(self, sapien.Pose([x, np.random.uniform(0.14, 0.16),
                                                0.74 + self.PAD_HALF_SIZE[2]]),
                              half_size=self.PAD_HALF_SIZE, color=(0.1, 0.3, 0.9),
                              is_static=True, name="hold_place_pad")
        scale = np.asarray(self.bottle.config["scale"])
        center = np.asarray(self.bottle.config["center"]) * scale
        half = np.asarray(self.bottle.config["extents"]) * scale / 2
        self._local_center = center
        self._local_corners = np.array([center + np.array(sign) * half
                                       for sign in itertools.product((-1, 1), repeat=3)])
        self.add_prohibit_area(self.bottle, padding=0.06)
        self.add_prohibit_area(self.pad, padding=0.02)

    def _geometry(self):
        pose = self.bottle.get_pose()
        rotation = t3d.quaternions.quat2mat(pose.q)
        center = rotation @ self._local_center + pose.p
        corners = self._local_corners @ rotation.T + pose.p
        pad = self.pad.get_pose().p
        bottom = float(corners[:, 2].min())
        clearance = bottom - (float(pad[2]) + self.PAD_HALF_SIZE[2])
        return pose, center, pad, clearance

    def _attach_observer(self):
        scene, original = self.scene, self.scene.step

        def observed_step():
            result = original()
            self._simulation_time += float(scene.get_timestep())
            if self._simulation_time - self._sample_time + 1e-9 >= self.monitor.rules.sample_seconds:
                self._sample_time = self._simulation_time
                pose, center, pad, clearance = self._geometry()
                held = bool(self.get_gripper_actor_contact_position(self.bottle.get_name()))
                supported = self.check_actors_contact(self.bottle.get_name(), self.pad.get_name())
                self.monitor.observe(self._simulation_time, center, pose.q, pad[:2],
                                     clearance, held, supported)
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
            raise ValueError("This experiment requires its explicit hold/place instruction")
        # A fixed pair first; seen/unseen here are runner interface values, not
        # claims about which language or motor behavior appeared in training.
        return INSTRUCTIONS[self.mode]

    def start_policy_rollout(self):
        self._terminal = True

    def finalize_policy_success(self):
        if not self._terminal or self.take_action_cnt != self.step_lim:
            raise RuntimeError("Both modes require the complete policy action budget")
        self._final_success = bool(self.monitor.success(self.mode))
        return self._final_success

    def check_success(self):
        return False if self._terminal else self.monitor.success(self.mode)

    def eval_signals(self):
        pose, center, pad, _ = self._geometry()
        return dict(self.monitor.signals(), mode=self.mode, scene_seed=self.scene_seed,
                    bottle_id=self.bottle_id, verdict_protocol="action-budget-end",
                    bottle_center=center.tolist(), bottle_quaternion=list(map(float, pose.q)),
                    pad_position=list(map(float, pad)),
                    final_success=self._final_success, policy_action_count=self.take_action_cnt,
                    policy_action_limit=self.step_lim)

    def play_once(self):
        self.move(self.grasp_actor(self.bottle, arm_tag=self.arm_tag, pre_grasp_dis=0.1))
        target_quat = [0.707, 0, 0, 0.707]
        self.move(self.move_by_displacement(self.arm_tag, z=0.1, quat=target_quat))
        self.move(self.move_by_displacement(self.arm_tag, z=0.1, quat=target_quat))
        pose, center, pad, _ = self._geometry()
        # Shared transport: align the bottle's long (+y) axis upright, using the
        # measured grasp transform. A tilted bottle would topple when released.
        rotation = t3d.quaternions.quat2mat(pose.q)
        axis = rotation[:, 1]
        correction = np.r_[1 + axis[2], np.cross(axis, [0, 0, 1])]
        if np.linalg.norm(correction) < 1e-8:
            correction = np.array([0, 1, 0, 0])
        correction = correction / np.linalg.norm(correction)
        turn = t3d.quaternions.quat2mat(correction)
        upright_rotation = turn @ rotation
        bottom_offset = ((self._local_corners - self._local_center) @ upright_rotation.T)[:, 2].min()
        destination = np.array([pad[0], pad[1], pad[2] + self.PAD_HALF_SIZE[2]
                                + self.HOVER_CLEARANCE - bottom_offset])
        ee = self.get_arm_pose(self.arm_tag)
        target_position = destination - turn @ (center - np.asarray(ee[:3]))
        target_rotation = t3d.quaternions.qmult(correction, ee[3:])
        self.move(self.move_to_pose(self.arm_tag, np.r_[target_position, target_rotation].tolist()))
        if self.mode == "place":
            _, _, _, clearance = self._geometry()
            self.move(self.move_by_displacement(self.arm_tag, z=0.002 - clearance))
            self.move(self.open_gripper(self.arm_tag))
            self.move(self.move_by_displacement(self.arm_tag, z=0.12))
        # Time advances only through real physics in oracle and policy runs.
        for _ in range(math.ceil((self.monitor.rules.stable_seconds + 0.5) / self.scene.get_timestep())):
            self.scene.step()
        self.info.update(mode=self.mode, scene_seed=self.scene_seed, bottle_id=self.bottle_id,
                         instruction=INSTRUCTIONS[self.mode], signals=self.eval_signals())
        self.info["info"] = {"{I}": INSTRUCTIONS[self.mode]}
        return self.info
