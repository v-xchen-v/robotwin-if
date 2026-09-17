"""Exercise arm_select success after setup, with no oracle execution."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np


class ArmTag(str):
    @property
    def opposite(self):
        return ArmTag("right" if self == "left" else "left")


class BaseTask:
    def _init_task_env_(self, seed, **kwargs):
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


source = Path(__file__).resolve().parents[2] / "tasks/envs/arm_select.py"
tree = ast.parse(source.read_text())
tree.body = [node for node in tree.body if isinstance(node, ast.ClassDef)]
namespace = {"Base_Task": BaseTask, "np": np, "ArmTag": ArmTag,
             "apply_if_eval_step_limit": lambda task: None}
exec(compile(tree, str(source), "exec"), namespace)
Task = namespace["arm_select"]


class PolicySuccessTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
