"""CPU checks for paired geometry, version isolation, and paired language."""
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

ROOT = Path(__file__).resolve().parents[2]


class Pose:
    def __init__(self, p, q):
        self.p, self.q = np.asarray(p), np.asarray(q)


class Base:
    def _init_task_env_(self, **kwargs):
        self.info = {}
        self.load_actors()

    def add_prohibit_area(self, *args, **kwargs):
        pass


source = ROOT / "tasks/envs/arm_select.py"
tree = ast.parse(source.read_text())
tree.body = [node for node in tree.body if isinstance(node, ast.ClassDef)]
namespace = {"Base_Task": Base, "np": np, "sapien": SimpleNamespace(Pose=Pose),
             "create_box": lambda **kw: SimpleNamespace(get_pose=lambda: kw["pose"]),
             "apply_if_eval_step_limit": lambda env: None}
exec(compile(tree, str(source), "exec"), namespace)
Task = namespace["arm_select"]


class SceneVariationTests(unittest.TestCase):
    def test_pairs_share_geometry_and_cross_blocks_vary(self):
        poses, regions = set(), []
        for block in range(50000, 50012):
            left, right = Task(), Task()
            left.setup_demo(seed=2*block, arm_select_scene_version="jitter-v2")
            # Disturb RNG to ensure the paired scene does not depend on history.
            np.random.seed(123)
            np.random.random(37)
            right.setup_demo(seed=2*block+1, arm_select_scene_version="jitter-v2")
            self.assertEqual((left.mode, right.mode), ("left", "right"))
            self.assertEqual(left.info["arm_select_scene"], right.info["arm_select_scene"])
            np.testing.assert_array_equal(left.box.get_pose().p, right.box.get_pose().p)
            np.testing.assert_array_equal(left.box.get_pose().q, right.box.get_pose().q)
            x, y, _ = left.box.get_pose().p
            self.assertTrue(-0.02 <= x <= 0.02 and 0.10 <= y <= 0.12)
            self.assertLessEqual(abs(left._scene_spec["yaw_degrees"]), 3)
            poses.add(tuple(left.box.get_pose().p))
            regions.append(left._scene_spec["region"])
        self.assertEqual(len(poses), 12)
        self.assertEqual([regions.count(r) for r in ("left", "center", "right")], [4, 4, 4])

    def test_default_and_reset_retain_fixed_v1(self):
        task = Task()
        task.setup_demo(seed=100000, arm_select_scene_version="jitter-v2")
        for seed in (100000, 100001, 100099):
            task.setup_demo(seed=seed)
            np.testing.assert_array_equal(task.box.get_pose().p, [0, 0.1, 0.842])
            np.testing.assert_array_equal(task.box.get_pose().q, [1, 0, 0, 0])
            self.assertEqual(task.scene_version, "fixed-v1")

    def test_unknown_version_fails_before_setup(self):
        with self.assertRaisesRegex(ValueError, "scene_version"):
            Task().setup_demo(seed=0, arm_select_scene_version="typo")

    def test_paired_language_only_changes_arm_and_restores_rng(self):
        from policies.xvla.eval import instruction_for
        # Use actual maintained templates and generator, with no GPU imports.
        import sys
        utils = str(ROOT / "third_party/robotwin/description/utils")
        with patch.object(sys, "path", [utils, *sys.path]):
            before = random.getstate()
            for block in range(50000, 50012):
                texts = []
                for offset, arm in enumerate(("left", "right")):
                    info = {"info": {"{A}": "the block", "{a}": arm},
                            "arm_select_scene": {"version": "jitter-v2"}}
                    text = instruction_for("arm_select", info, "unseen", 2*block+offset)
                    self.assertIn(f"the {arm} arm", text)
                    texts.append(text.replace(f"the {arm} arm", "the ARM arm"))
                self.assertEqual(*texts)
            self.assertEqual(random.getstate(), before)
            # Fixed-v1 keeps the archived raw-seed language selection.
            text = instruction_for("arm_select", {"info": {"{A}": "the block", "{a}": "left"}}, "unseen", 100000)
            self.assertEqual(text, "Have the left arm take the block.")

    def test_all_six_evaluators_require_matching_v2_manifest_config(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "arm_select.json"
            manifest.write_text(json.dumps({"schema_version": 1, "task": "arm_select",
                                           "task_config": "demo_clean_arm_select_v2",
                                           "seeds": [100000, 100001]}))
            for policy in ("xvla", "lingbot_va", "lingbot_vla", "vlact", "dm05", "hy_vla"):
                module = importlib.import_module(f"policies.{policy}.eval")
                argv = ["eval.py", "--task", "arm_select", "--task-config", "demo_clean_arm_select_v2",
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
