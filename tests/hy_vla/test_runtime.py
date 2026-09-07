"""Official EE geometry and per-step MEM/cache parity, without allocating the model."""
from collections import deque
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from scipy.spatial.transform import Rotation
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "third_party/hy-vla")]
from policies.hy_vla.runtime import RecordedWrapper  # noqa: E402
from robotwin_eval.deploy_policy import encode_obs  # noqa: E402
from hy_vla.modeling_hy_vla import HyVLA  # noqa: E402
from safetensors.torch import save_file  # noqa: E402


def observation(step=0):
    quats = [Rotation.from_euler("z", 60, degrees=True).as_quat(), Rotation.from_euler("x", -40, degrees=True).as_quat()]
    return {"observation": {name: {"rgb": np.full((12, 16, 3), step + 20 + i, dtype=np.uint8)}
                            for i, name in enumerate(("head_camera", "left_camera", "right_camera"))},
            "endpose": {"left_endpose": np.r_[[.1, .2, .3], quats[0][[3, 0, 1, 2]]], "left_gripper": .3,
                        "right_endpose": np.r_[[-.2, .3, .4], quats[1][[3, 0, 1, 2]]], "right_gripper": .7}}


def raw_prediction():
    obs = observation()
    relative, absolute, target = [], [], []
    for arm, delta in [("left", [.1, .02, .03]), ("right", [-.03, .04, .01])]:
        pose = obs["endpose"][f"{arm}_endpose"]
        rotation = Rotation.from_quat(pose[[4, 5, 6, 3]]).as_matrix()
        position = pose[:3] + rotation @ delta
        grip = obs["endpose"][f"{arm}_gripper"]
        relative.extend([*delta, 1, 0, 0, 0, 1, 0, grip])
        absolute.extend([*position, *rotation[:2].reshape(6), grip])
        target.extend([*position, *pose[3:7], grip])
    return np.concatenate([np.tile(relative, (20, 1)), np.tile(absolute, (20, 1))]), np.asarray(target)


def wrapper_without_weights():
    wrapper = RecordedWrapper.__new__(RecordedWrapper)
    wrapper.norm_data = {"qpos_mean": np.zeros(20), "qpos_std": np.ones(20),
                         "act_mean": np.zeros((20, 20)), "act_std": np.ones((20, 20)),
                         "act_mean_abs": np.zeros((20, 20)), "act_std_abs": np.ones((20, 20))}
    wrapper._has_abs_stats = True
    wrapper.blend_mode, wrapper.exc_action_size = "rel_abs", 7
    wrapper.umi_coord_frame, wrapper.umi_gripper_space = False, False
    wrapper.use_video_encoder, wrapper.img_history_size, wrapper.img_history_interval = True, 6, 5
    wrapper._top_imgs, wrapper._left_imgs, wrapper._right_imgs = [], [], []
    wrapper.action_cache = deque()
    wrapper.weight_dtype = torch.float32
    return wrapper


class RuntimeTests(unittest.TestCase):
    def test_strict_loader_matches_training_structure_and_rejects_missing_weights(self):
        class TinyPolicy(HyVLA):
            def __init__(self, config):
                torch.nn.Module.__init__(self)
                self.model = torch.nn.Module()
                self.model.dual_tower = torch.nn.Module()
                self.model.dual_tower.expert = torch.nn.Module()
                self.model.dual_tower.expert.lm_head = torch.nn.Linear(2, 3)
                self.model.action_in_proj = torch.nn.Linear(2, 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "config.json").write_text('{}')
            config = SimpleNamespace(vlm_config_dict={"test": True}, pretrained_path=directory)
            expected = {"model.action_in_proj.weight": torch.full((2, 2), .5, dtype=torch.bfloat16),
                        "model.action_in_proj.bias": torch.ones(2, dtype=torch.bfloat16)}
            save_file(expected, path / "model.safetensors")
            loaded = TinyPolicy.from_pretrained(directory, config=config, strict=True)
            self.assertFalse(hasattr(loaded.model.dual_tower.expert, "lm_head"))
            self.assertEqual(set(loaded.state_dict()), set(expected))
            for name, value in loaded.state_dict().items():
                self.assertEqual(value.dtype, torch.bfloat16)
                torch.testing.assert_close(value, expected[name])
            del expected["model.action_in_proj.bias"]
            save_file(expected, path / "model.safetensors")
            with self.assertRaisesRegex(RuntimeError, 'Missing key'):
                TinyPolicy.from_pretrained(directory, config=config, strict=True)

    def test_relabs_decode_respects_local_frame_and_wxyz(self):
        wrapper = wrapper_without_weights()
        raw, target = raw_prediction()
        start = encode_obs(observation(), "Pick")["observation.state"][0, :16]
        start_xyzw = start.copy()
        start_xyzw[3:7] = start[[4, 5, 6, 3]]
        start_xyzw[11:15] = start[[12, 13, 14, 11]]
        wrapper._decode_actions(raw, start_xyzw)
        output = wrapper.last_prediction["decoded_actions"]
        np.testing.assert_array_equal(wrapper.last_prediction["model_actions"], raw)
        np.testing.assert_allclose(output, np.tile(target, (20, 1)), atol=1e-7)

    def test_cached_steps_feed_history_and_reset_clears_it(self):
        wrapper = wrapper_without_weights()
        raw, _ = raw_prediction()
        class Policy:
            def __init__(self):
                self.batches = []
                self.reset()
            def reset(self):
                self._action_queue = deque()
            def select_action(self, batch):
                self.batches.append(batch)
                self._action_queue.extend(torch.from_numpy(raw[i:i + 1].astype(np.float32)) for i in range(1, 40))
                return torch.from_numpy(raw[:1].astype(np.float32))
        wrapper.policy = Policy()
        with patch.object(torch.Tensor, "cuda", lambda tensor, *a, **kw: tensor):
            for step in range(8):
                wrapper.get_action(encode_obs(observation(step), "Pick with the right arm"))
                self.assertEqual(wrapper.last_prediction is not None, step in (0, 7))
        self.assertEqual(len(wrapper.policy.batches), 2)
        first, second = wrapper.policy.batches
        for key in ("top_head", "hand_left", "hand_right"):
            images = first[f"observation.images.{key}"]
            self.assertEqual(tuple(images.shape), (1, 6, 3, 12, 16))
            self.assertTrue(torch.all(images[:, :5] == 0))
            images = second[f"observation.images.{key}"]
            self.assertTrue(torch.all(images[:, :4] == 0))
        head = second["observation.images.top_head"]
        np.testing.assert_allclose(head[0, 4, 0, 0, 0], 22/255)
        np.testing.assert_allclose(head[0, 5, 0, 0, 0], 27/255)
        self.assertEqual(second["task"], ["Pick with the right arm"])
        self.assertEqual(len(wrapper._top_imgs), 8)
        self.assertEqual(wrapper._eval_history_indices(28, 6, 5), [3, 8, 13, 18, 23, 28])
        wrapper.reset()
        self.assertEqual(len(wrapper._top_imgs), 0)
        self.assertEqual(len(wrapper.action_cache), 0)
        self.assertIsNone(wrapper.last_prediction)


if __name__ == "__main__":
    unittest.main()
