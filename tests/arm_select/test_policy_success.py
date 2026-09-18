"""Exercise arm_select success after setup, with no oracle execution."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np
from tasks.envs._if_grounding import ArmPickMonitor


class ArmTag(str):
    @property
    def opposite(self):
        return ArmTag("right" if self == "left" else "left")


class BaseTask:
    def _init_task_env_(self, seed, **kwargs):
        self.scene = SimpleNamespace(step=lambda: None)
        self.take_action_cnt = 0
        self.mode = "left" if seed % 2 == 0 else "right"
        self.position = np.array([0., 0.1, self.box_spawn_z])
        self.box = SimpleNamespace(get_pose=lambda: SimpleNamespace(p=self.position))
        # load_actors currently clears this before the base task settles physics.
        self._init_box_z = None
        self.info = {}
        self._scene_spec = {"version": self.scene_version}
        self.tcps = {"left": np.array([-0.3, 0.1, 0.9]), "right": np.array([0.3, 0.1, 0.9])}

    def get_arm_pose(self, arm):
        return self.tcps[str(arm)]

    def close_env(self, clear_cache=False):
        pass


source = Path(__file__).resolve().parents[2] / "tasks/envs/arm_select.py"
tree = ast.parse(source.read_text())
tree.body = [node for node in tree.body if isinstance(node, ast.ClassDef)]
namespace = {"Base_Task": BaseTask, "np": np, "ArmTag": ArmTag,
             "ArmPickMonitor": ArmPickMonitor,
             "apply_if_eval_step_limit": lambda task: None}
exec(compile(tree, str(source), "exec"), namespace)
Task = namespace["arm_select"]


class PolicySuccessTests(unittest.TestCase):
    def set_pose(self, task, lift, arm, *, new_action=True):
        task.position[2] = task._init_box_z + lift
        for name in ("left", "right"):
            task.tcps[name] = task.position + ([0, 0, .1] if name == arm else [.5, 0, .1])
        task.take_action_cnt += int(new_action)
        task.scene.step()

    def test_policy_can_succeed_without_play_once(self):
        for version, seed in ((v, s) for v in ("fixed-v1", "jitter-v2", "cube-v3") for s in (100000, 100001)):
            with self.subTest(seed=seed, version=version):
                task = Task()
                task.setup_demo(seed=seed, arm_select_scene_version=version)
                self.assertFalse(task.check_success())
                task.position[2] += 0.1
                task.tcps[task.mode] = task.position + [0, 0, 0.1]
                self.assertTrue(task.check_success())

    def test_wrong_arm_lift_still_fails(self):
        for version in ("fixed-v1", "jitter-v2", "cube-v3"):
            with self.subTest(version=version):
                task = Task()
                task.setup_demo(seed=100000, arm_select_scene_version=version)
                task.position[2] += 0.1
                task.tcps["right"] = task.position + [0, 0, 0.1]
                self.assertFalse(task.check_success())
                self.assertTrue(task.eval_signals()["lifted"])

    def test_reset_clears_previous_success(self):
        task = Task()
        task.setup_demo(seed=100000)
        task.position[2] += 0.1
        task.tcps["left"] = task.position + [0, 0, 0.1]
        self.assertTrue(task.check_success())
        task.setup_demo(seed=100001)
        self.assertFalse(task.check_success())
        self.assertEqual(task.eval_signals()["lift_delta"], 0)

    def test_wrong_arm_then_target_fails_with_or_without_putting_down(self):
        for seed in (500000, 500001):
            for put_down in (False, True):
                with self.subTest(seed=seed, put_down=put_down):
                    task = Task()
                    task.setup_demo(seed=seed, arm_select_scene_version="cube-v3")
                    # Do not query success/signals before the final state.
                    self.set_pose(task, .10, ArmTag(task.mode).opposite)
                    if put_down:
                        self.set_pose(task, 0, None)
                    self.set_pose(task, .10, task.mode)
                    self.assertFalse(task.check_success())
                    sig = task.eval_signals()
                    self.assertTrue(sig["arm_match"] and sig["lifted"])
                    self.assertTrue(sig["wrong_arm_lifted_ever"])
                    self.assertFalse(sig["target_arm_only_success"])
                    self.assertEqual(sig["first_lifted_arm"], ArmTag(task.mode).opposite)
                    self.assertEqual(sig["lifted_by"], task.mode)
                    self.assertEqual(sig["first_wrong_arm_lift_action"], 1)

    def test_wrong_arm_lift_inside_one_action_is_observed(self):
        task = Task()
        task.setup_demo(seed=500000, arm_select_scene_version="cube-v3")
        self.set_pose(task, .10, "right")
        self.set_pose(task, 0, None, new_action=False)
        self.set_pose(task, .10, "left", new_action=False)
        self.assertEqual(task.take_action_cnt, 1)
        self.assertFalse(task.check_success())
        self.assertEqual(task.eval_signals()["first_wrong_arm_lift_action"], 1)

    def test_wrong_arm_touch_or_small_lift_does_not_invalidate(self):
        for seed in (500000, 500001):
            task = Task()
            task.setup_demo(seed=seed, arm_select_scene_version="cube-v3")
            self.set_pose(task, .02, ArmTag(task.mode).opposite)
            self.set_pose(task, .10, task.mode)
            self.assertTrue(task.check_success())
            self.assertFalse(task.eval_signals()["wrong_arm_lifted_ever"])
            self.set_pose(task, 0, task.mode)
            self.assertFalse(task.check_success())

    def test_reset_clears_wrong_arm_history_and_detaches_old_scene(self):
        task = Task()
        task.setup_demo(seed=500000, arm_select_scene_version="cube-v3")
        self.set_pose(task, .10, "right")
        old_scene = task.scene
        task.setup_demo(seed=500001, arm_select_scene_version="cube-v3")
        task.position[2] += .10
        task.tcps["left"] = task.position + [0, 0, .1]
        old_scene.step()
        self.assertFalse(task._pick_monitor.wrong_arm_lifted_ever)
        self.set_pose(task, .10, "right")
        self.assertTrue(task.check_success())
        self.assertEqual(task.eval_signals()["first_lifted_arm"], "right")

    def test_close_restores_scene_and_queries_do_not_clear_history(self):
        task = Task()
        task.setup_demo(seed=500000, arm_select_scene_version="cube-v3")
        self.set_pose(task, .10, "right")
        self.set_pose(task, .10, "left")
        before = task.eval_signals()
        for _ in range(3):
            self.assertFalse(task.check_success())
            self.assertEqual(task.eval_signals(), before)
        json.dumps(before, allow_nan=False)
        scene = task.scene
        task.close_env()
        task.position[2] += .20
        scene.step()
        self.assertEqual(task._pick_monitor.signals(), before)
        self.assertIsNone(task._pick_observer)

    def test_lift_and_tcp_thresholds_remain_strict(self):
        monitor = ArmPickMonitor("left")
        monitor.observe(.05, .5, .1)
        self.assertFalse(monitor.wrong_arm_lifted_ever)
        monitor.observe(.10, .5, .20)
        self.assertFalse(monitor.wrong_arm_lifted_ever)
        monitor.observe(.10, .1, .1)  # Tied distances do not identify either arm.
        self.assertFalse(monitor.success)
        self.assertFalse(monitor.wrong_arm_lifted_ever)
        monitor.observe(.10, .20, .5)
        self.assertFalse(monitor.success)
        monitor.observe(.050001, .199999, .5)
        self.assertTrue(monitor.success)
        monitor.observe(.050001, .5, .199999)
        self.assertTrue(monitor.wrong_arm_lifted_ever)
        monitor.observe(.10, .1, .5)
        self.assertFalse(monitor.success)

    def test_play_once_preserves_baseline_and_wrong_arm_history(self):
        task = Task()
        task.setup_demo(seed=500000, arm_select_scene_version="cube-v3")
        initial_z = task._init_box_z
        self.set_pose(task, .10, "right")
        task.grasp_actor = lambda *args, **kwargs: None
        task.move_by_displacement = lambda *args, **kwargs: None
        task.move = lambda *args: self.set_pose(task, .10, "left")
        info = task.play_once()
        self.assertEqual(task._init_box_z, initial_z)
        self.assertTrue(info["signals"]["lifted"])
        self.assertTrue(info["signals"]["arm_match"])
        self.assertFalse(task.check_success())


if __name__ == "__main__":
    unittest.main()
