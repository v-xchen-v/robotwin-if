"""CPU invariants for paired translation, fixed arm, language and scoring."""
import ast
import importlib
import json
from pathlib import Path
import random
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import transforms3d as t3d

ROOT = Path(__file__).resolve().parents[2]


class Pose:
    def __init__(self, p, q):
        self.p, self.q = np.asarray(p, dtype=float), np.asarray(q, dtype=float)


class Base:
    def _init_task_env_(self, **kwargs):
        self.info = {}
        self.load_actors()

    def add_prohibit_area(self, *args, **kwargs):
        pass


def box(**kwargs):
    return SimpleNamespace(get_pose=lambda: kwargs["pose"], config={}, set_mass=lambda mass: None)


source = ROOT / "tasks/envs/grasp_cube_approach.py"
tree = ast.parse(source.read_text())
tree.body = [node for node in tree.body if isinstance(node, ast.ClassDef)]
namespace = {"Base_Task": Base, "np": np, "t3d": t3d, "ArmTag": str,
             "sapien": SimpleNamespace(Pose=Pose), "create_box": box,
             "apply_if_eval_step_limit": lambda env: None}
exec(compile(tree, str(source), "exec"), namespace)
Task = namespace["grasp_cube_approach"]


class TranslationTests(unittest.TestCase):
    def test_wide_profile_is_paired_and_keeps_old_profile_replayable(self):
        wide_positions = []
        for scene_seed in range(250000, 250120):
            a, b = Task(), Task()
            for offset, task in enumerate((a, b)):
                task.setup_demo(seed=2 * scene_seed + offset,
                                grasp_approach_scene_version="translate-v2",
                                grasp_approach_translation_profile="wide-r1")
            np.testing.assert_array_equal(a.cube.get_pose().p, b.cube.get_pose().p)
            np.testing.assert_array_equal(a.riser.get_pose().p[:2], a.cube.get_pose().p[:2])
            np.testing.assert_array_equal(a.cube.get_pose().q, [1, 0, 0, 0])
            self.assertEqual((a.mode, b.mode), ("top", "side"))
            self.assertEqual((a.execution_arm(), b.execution_arm()), ("right", "right"))
            self.assertEqual(a._scene_spec['translation_profile'], 'wide-r1')
            x, y = a.cube.get_pose().p[:2]
            self.assertTrue(0 <= x <= .08 and -.085 <= y <= -.035)
            wide_positions.append([x, y])
            old = Task.translation_xy(scene_seed)
            self.assertTrue(-.01 <= old[0] <= .01 and -.06 <= old[1] <= -.05)
        self.assertGreater(np.ptp(wide_positions, axis=0)[0], .07)
        self.assertGreater(np.ptp(wide_positions, axis=0)[1], .045)

    def test_unknown_translation_profile_rejected(self):
        with self.assertRaisesRegex(ValueError, 'translation_profile'):
            Task().setup_demo(seed=0, grasp_approach_scene_version='translate-v2',
                              grasp_approach_translation_profile='typo')

    def test_paired_geometry_varies_without_rotation_or_arm_switch(self):
        positions, regions = set(), []
        for block in range(50000, 50012):
            top, side = Task(), Task()
            top.setup_demo(seed=2*block, grasp_approach_scene_version="translate-v2")
            np.random.seed(13)
            np.random.random(31)
            side.setup_demo(seed=2*block+1, grasp_approach_scene_version="translate-v2")
            self.assertEqual((top.mode, side.mode), ("top", "side"))
            for actor in ("cube", "riser"):
                a, b = getattr(top, actor).get_pose(), getattr(side, actor).get_pose()
                np.testing.assert_array_equal(a.p, b.p)
                np.testing.assert_array_equal(a.q, [1, 0, 0, 0])
                np.testing.assert_array_equal(a.q, b.q)
            self.assertEqual(top.info["grasp_approach_scene"], side.info["grasp_approach_scene"])
            x, y, z = top.cube.get_pose().p
            self.assertTrue(-0.01 <= x <= 0.01 and -0.06 <= y <= -0.05)
            self.assertAlmostEqual(z, 0.790)
            np.testing.assert_array_equal(top.cube.get_pose().p[:2], top.riser.get_pose().p[:2])
            self.assertAlmostEqual(z-top.riser.get_pose().p[2], 0.037)
            self.assertEqual(top.execution_arm(), "right")
            self.assertEqual(side.execution_arm(), "right")
            positions.add((x, y))
            regions.append(top._scene_spec["region"])
        self.assertEqual(len(positions), 12)
        self.assertEqual([regions.count(r) for r in ("left", "center", "right")], [4, 4, 4])

    def test_default_reset_preserves_fixed_pose_and_v1_phrases(self):
        task = Task()
        task.setup_demo(seed=100002, grasp_approach_scene_version="translate-v2")
        for seed, phrase in [(100000, "from the top"), (100002, "from above"), (100003, "from the side")]:
            task.setup_demo(seed=seed)
            self.assertEqual(task.scene_version, "fixed-v1")
            np.testing.assert_array_equal(task.cube.get_pose().p[:2], [0, -0.05])
            self.assertEqual(task._approach_phrase(), phrase)
            self.assertEqual(task.execution_arm(), "right")

    def test_invalid_or_conflicting_versions_fail(self):
        with self.assertRaisesRegex(ValueError, "scene_version"):
            Task().setup_demo(seed=0, grasp_approach_scene_version="typo")
        task = Task()
        task.POSE_JITTER = True
        with self.assertRaisesRegex(ValueError, "POSE_JITTER"):
            task.setup_demo(seed=0, grasp_approach_scene_version="translate-v2")

    def test_lift_with_wrong_direction_fails_in_both_modes(self):
        for seed, correct, wrong in [(100000, 1.0, 0.0), (100001, 0.0, 1.0)]:
            task = Task()
            task.setup_demo(seed=seed, grasp_approach_scene_version="translate-v2")
            self.assertFalse(task.check_success())
            task.cube.get_pose().p[2] += 0.1
            task._approach_axis_z = wrong
            self.assertTrue(task.eval_signals()["lifted"])
            self.assertFalse(task.check_success())
            task._approach_axis_z = correct
            self.assertTrue(task.check_success())

    def test_language_changes_only_top_side_and_restores_rng(self):
        from policies.xvla.eval import instruction_for
        utils = str(ROOT / "third_party/robotwin/description/utils")
        with patch.object(sys, "path", [utils, *sys.path]):
            before = random.getstate()
            for block in range(50000, 50012):
                texts = []
                for offset, direction in enumerate(("top", "side")):
                    info = {"info": {"{A}": "the block", "{a}": "right", "{D}": f"from the {direction}"},
                            "grasp_approach_scene": {"version": "translate-v2"}}
                    text = instruction_for("grasp_cube_approach", info, "unseen", 2*block+offset)
                    self.assertIn(f"from the {direction}", text)
                    texts.append(text.replace(f"from the {direction}", "from the DIRECTION"))
                self.assertEqual(*texts)
            self.assertEqual(random.getstate(), before)
            info = {"info": {"{A}": "the block", "{a}": "right", "{D}": "from the top"}}
            self.assertEqual(instruction_for("grasp_cube_approach", info, "unseen", 100000),
                             "Grasp the block from the top with care.")

    def test_all_six_clis_accept_new_config_and_reject_old_manifest_config(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "grasp_cube_approach.json"
            manifest.write_text(json.dumps({"schema_version": 1, "task": "grasp_cube_approach",
                                           "task_config": "demo_clean_grasp_approach_v2", "seeds": [100000, 100001]}))
            for policy in ("xvla", "lingbot_va", "lingbot_vla", "vlact", "dm05", "hy_vla"):
                module = importlib.import_module(f"policies.{policy}.eval")
                argv = ["eval.py", "--task", "grasp_cube_approach", "--task-config", "demo_clean_grasp_approach_v2",
                        "--seed-manifest", str(manifest), "--blocks", "1", "--output-dir", "unused"]
                with self.subTest(policy=policy), patch.object(sys, "argv", argv):
                    select = module.select_seeds
                    with patch.object(module, "select_seeds", side_effect=InterruptedError) as called:
                        with self.assertRaises(InterruptedError):
                            module.main()
                    args = called.call_args.args[0]
                    self.assertEqual(select(args)[0], [100000, 100001])
                    args.task_config = "demo_clean"
                    with self.assertRaisesRegex(ValueError, "task/config"):
                        select(args)


if __name__ == "__main__":
    unittest.main()
