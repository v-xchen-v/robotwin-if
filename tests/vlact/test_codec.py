"""Verify wrap decoding, arm order and image pixels against official RoboTwin code."""

import ast
from pathlib import Path
import sys
import unittest

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from policies.vlact.codec import ACTION_ORDER, IMAGE_BUCKETS, decode_model_actions, resize_image  # noqa: E402


class CodecTests(unittest.TestCase):
    def test_wrap_preserves_radians_outside_unit_range_and_arm_order(self):
        values = np.tile([2., -2., 4., -4., 0., 1., .2, .3, .4, .5, .6, .7, .25, .75], (32, 1))
        decoded = decode_model_actions(values, [True] * 12 + [False] * 2)
        self.assertAlmostEqual(decoded[0, 0], 2., places=5)
        self.assertAlmostEqual(decoded[0, 2], 4. - 2 * np.pi, places=5)
        self.assertAlmostEqual(decoded[0, 3], -4. + 2 * np.pi, places=5)
        self.assertAlmostEqual(decoded[0, 6], .25)
        self.assertAlmostEqual(decoded[0, 7], .2, places=5)
        self.assertAlmostEqual(decoded[0, 13], .75)
        for invalid in (np.zeros((31, 14)), np.full((32, 14), np.inf)):
            with self.assertRaises(ValueError):
                decode_model_actions(invalid, [True] * 12 + [False] * 2)
        with self.assertRaises(ValueError):
            decode_model_actions(values, [True] * 14)

    def test_official_wrap_and_image_parity(self):
        path = ROOT / "third_party/vlact/examples/Robotwin/eval_files/model2robotwin_interface.py"
        if not path.exists():
            self.skipTest("Pinned VLAct checkout unavailable")
        # Execute the actual upstream pure methods without importing its Torch
        # server/training dependencies into the independent simulator environment.
        tree = ast.parse(path.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ModelClient")
        cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in
                    ("unnormalize_actions", "_resize_image", "_get_target_image_size")]
        namespace = {"np": np, "cv": cv2}
        exec("from __future__ import annotations\n" + ast.unparse(cls), namespace)
        official = namespace["ModelClient"]()
        official.image_size_buckets, official.image_size = IMAGE_BUCKETS, [224, 224]
        rng = np.random.default_rng(17)
        raw = rng.uniform(-9, 9, (32, 14)).astype(np.float32)
        stats = {"min": [-10.] * 14, "max": [10.] * 14, "mask": [True] * 12 + [False] * 2}
        expected = official.unnormalize_actions(raw, stats, "wrap")[:, ACTION_ORDER]
        np.testing.assert_array_equal(decode_model_actions(raw, stats["mask"]), expected)
        for height, width in ((480, 640), (240, 320), (720, 1280)):
            rgb = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
            np.testing.assert_array_equal(resize_image(rgb), official._resize_image(rgb))


if __name__ == "__main__":
    unittest.main()
