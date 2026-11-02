"""CPU checks for paired geometry, reset, and paired language."""
import ast
import importlib
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from tasks.envs._if_grounding import ArmPickMonitor

ROOT = Path(__file__).resolve().parents[2]


class Pose:
    def __init__(self, p, q):
        self.p, self.q = np.asarray(p), np.asarray(q)


class Base:
    def _init_task_env_(self, **kwargs):
        self.scene = SimpleNamespace(step=lambda: None)
        self.info = {}
        self.load_actors()

    def add_prohibit_area(self, *args, **kwargs):
        pass


source = ROOT / "tasks/envs/arm_select.py"
tree = ast.parse(source.read_text())
tree.body = [node for node in tree.body if isinstance(node, ast.ClassDef)]
namespace = {"Base_Task": Base, "np": np, "sapien": SimpleNamespace(Pose=Pose),
             "ArmPickMonitor": ArmPickMonitor,
             "create_box": lambda **kw: SimpleNamespace(get_pose=lambda: kw["pose"]),
             "apply_if_eval_step_limit": lambda env: None}
exec(compile(tree, str(source), "exec"), namespace)
Task = namespace["arm_select"]


class SceneVariationTests(unittest.TestCase):
    def test_cube_pairs_vary_pose_without_leaking_arm(self):
        poses, rotations, regions = set(), set(), []
        for block in range(150000, 150012):
            left, right = Task(), Task()
            left.setup_demo(seed=2*block)
            np.random.random(37)
            right.setup_demo(seed=2*block+1)
            self.assertEqual((left.mode, right.mode), ("left", "right"))
            self.assertEqual(left.info["arm_select_scene"], right.info["arm_select_scene"])
            np.testing.assert_array_equal(left.box.get_pose().p, right.box.get_pose().p)
            np.testing.assert_array_equal(left.box.get_pose().q, right.box.get_pose().q)
            poses.add(tuple(left.box.get_pose().p))
            rotations.add(tuple(left.box.get_pose().q))
            regions.append(left._scene_spec["region"])
            x, y, _ = left.box.get_pose().p
            self.assertTrue(-0.04 <= x <= 0.04 and -0.08 <= y <= -0.06)
            self.assertLessEqual(abs(left._scene_spec["yaw_degrees"]), 15)
            # Roll/pitch remain zero so the cube starts flat on the table.
            np.testing.assert_array_equal(left.box.get_pose().q[1:3], [0, 0])
        self.assertEqual(len(poses), 12)
        self.assertEqual(len(rotations), 12)
        self.assertEqual([regions.count(r) for r in ("left", "center", "right")], [4, 4, 4])

    def test_reset_always_uses_the_current_cube(self):
        task = Task()
        with patch.dict(namespace, create_box=lambda **kw: SimpleNamespace(get_pose=lambda: kw["pose"], creation=kw)):
            for seed in (500000, 500001, 500039):
                task.setup_demo(seed=seed)
                cube = task.box.creation
                self.assertEqual(cube["boxtype"], "default")
                self.assertEqual(cube["half_size"], (0.025, 0.025, 0.025))
                self.assertAlmostEqual(cube["pose"].p[2] - cube["half_size"][2], 0.741)
                self.assertEqual(task.pre_grasp_dis, 0.09)

    def test_obsolete_selector_is_rejected_before_setup(self):
        task = Task()
        with self.assertRaisesRegex(ValueError, "scene_version is retired"):
            task.setup_demo(seed=0, arm_select_scene_version="fixed-v1")
        self.assertFalse(hasattr(task, "scene"))

    def test_paired_language_only_changes_arm_and_restores_rng(self):
        from policies.xvla.eval import instruction_for
        # Use actual maintained templates and generator, with no GPU imports.
        import sys
        utils = str(ROOT / "third_party/robotwin/description/utils")
        with patch.object(sys, "path", [utils, *sys.path]):
            before = random.getstate()
            for block in range(250000, 250020):
                texts = []
                for offset, arm in enumerate(("left", "right")):
                    info = {"info": {"{A}": "the block", "{a}": arm}}
                    text = instruction_for("arm_select", info, "unseen", 2*block+offset)
                    self.assertIn(f"the {arm} arm", text)
                    texts.append(text.replace(f"the {arm} arm", "the ARM arm"))
                self.assertEqual(*texts)
            self.assertEqual(random.getstate(), before)

    def test_formal_seeds_preserve_published_scene_and_instruction_contract(self):
        from policies.xvla.eval import instruction_for
        seeds = json.loads((ROOT / "seed-manifests/20-blocks/arm_select.json").read_text())["seeds"]
        rows = []
        utils = str(ROOT / "third_party/robotwin/description/utils")
        with patch.object(sys, "path", [utils, *sys.path]):
            for seed in seeds:
                task = Task()
                task.setup_demo(seed=seed)
                info = {"info": {"{A}": "the block", "{a}": task.mode},
                        "arm_select_scene": task.info["arm_select_scene"]}
                rows.append(dict(seed=seed, mode=task.mode,
                    instruction=instruction_for("arm_select", info, "unseen", seed),
                    scene=task.info["arm_select_scene"],
                    geometry=dict(half_size=list(task.box_half_size), boxtype=task.box_type,
                        spawn_z=task.box_spawn_z, pre_grasp_dis=task.pre_grasp_dis,
                        grasp_ids=task.GRASP_IDS, lift_z=task.LIFT_Z)))
        payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        # Captured from release-20261030 before removing its scene selector.
        self.assertEqual(hashlib.sha256(payload).hexdigest(),
                         "c213eda904fd955514aa0aaaa9168a8d09a0e54e93dc121727d078f82a4c14d4")

    def test_all_six_evaluators_require_matching_manifest_config(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "arm_select.json"
            for policy in ("xvla", "lingbot_va", "lingbot_vla", "vlact", "dm05", "hy_vla"):
                config = "demo_clean_arm_select"
                manifest.write_text(json.dumps({"schema_version": 1, "task": "arm_select",
                                               "task_config": config, "seeds": [100000, 100001]}))
                module = importlib.import_module(f"policies.{policy}.eval")
                argv = ["eval.py", "--task", "arm_select", "--task-config", config,
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
