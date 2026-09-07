"""Per-step camera transport, reset isolation and bounded EE rollout evidence."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from policies.hy_vla.client import CAMERAS, PROTOCOL, HyVLAClient, format_observation, packb, unpackb  # noqa: E402
from policies.hy_vla.eval import run_episode  # noqa: E402
from policies.hy_vla.serve import EpisodePolicy  # noqa: E402


def observation(step=0):
    return {"observation": {name: {"rgb": np.full((12, 16, 3), step + i, dtype=np.uint8)}
                            for i, name in enumerate(CAMERAS)},
            "endpose": {"left_endpose": [.1, .2, .3, 1., 0., 0., 0.], "left_gripper": .3,
                        "right_endpose": [-.2, .3, .4, 0., 1., 0., 0.], "right_gripper": .7},
            "joint_action": {"vector": np.arange(14, dtype=np.float32) / 20 + step / 100}}


def decoded():
    pose = np.array([.1, .2, .3, 1., 0., 0., 0., .3, -.2, .3, .4, 0., 1., 0., 0., .7])
    return np.broadcast_to(pose, (20, 16)).copy()


def step_response(step):
    new = step % 7 == 0
    return {"action": decoded()[step % 7], "episode_step": step, "new_chunk": new,
            **({"model_actions": np.zeros((40, 20), dtype=np.float32), "decoded_actions": decoded()} if new else {})}


def client_with_responses(*responses, metadata=None):
    connection = Mock()
    metadata = metadata if metadata is not None else {
        "protocol": PROTOCOL, "action_type": "ee", "action_dim": 16,
        "model_shape": [40, 20], "decoded_shape": [20, 16], "execute_horizon": 7,
        "history_size": 6, "history_interval": 5, "blend_mode": "rel_abs"}
    connection.recv.side_effect = [packb(metadata), *[packb(r) for r in responses]]
    with patch("policies.hy_vla.client.connect", return_value=connection):
        client = HyVLAClient()
    return client, connection


class ClientTests(unittest.TestCase):
    def test_native_state_and_lossless_camera_order(self):
        obs = observation(3)
        packed = unpackb(packb(format_observation(obs)))
        np.testing.assert_array_equal(packed["state"][[3, 4, 5, 6]], [1, 0, 0, 0])
        np.testing.assert_array_equal(packed["state"][[11, 12, 13, 14]], [0, 1, 0, 0])
        np.testing.assert_allclose(packed["state"][[7, 15]], [.3, .7])
        for name in CAMERAS:
            np.testing.assert_array_equal(packed["images"][name], obs["observation"][name]["rgb"])
        obs["endpose"]["left_endpose"][3:] = [0]*4
        with self.assertRaises(ValueError):
            format_observation(obs)

    def test_every_cached_step_sends_fresh_observation(self):
        client, connection = client_with_responses({"ok": True}, *[step_response(i) for i in range(8)])
        with self.assertRaises(RuntimeError):
            client.predict(observation())
        client.reset("Use the right arm", 100001)
        for step in range(8):
            action, prediction = client.predict(observation(step))
            self.assertEqual(prediction["new_chunk"], step in (0, 7))
            np.testing.assert_array_equal(action, decoded()[0])
        sent = [unpackb(c.args[0]) for c in connection.send.call_args_list]
        self.assertEqual(sent[0]["seed"], 100001)
        for i, request in enumerate(sent[1:]):
            self.assertEqual(request["step"], i)
            self.assertEqual(request["observation"]["images"]["head_camera"][0, 0, 0], i)

    def test_bad_protocol_and_response_invalidate_episode(self):
        with self.assertRaises(ValueError):
            client_with_responses(metadata={"protocol": "dm05_robotwin_v1"})
        client, _ = client_with_responses({"ok": True}, {"error": "Inference failed"}, {"error": "Reset failed"})
        for bad in (True, -1, 2**32):
            with self.assertRaises(ValueError):
                client.reset("Bell", bad)
        client.reset("Bell", 2000)
        with self.assertRaisesRegex(RuntimeError, "Inference failed"):
            client.predict(observation())
        with self.assertRaises(RuntimeError):
            client.predict(observation())
        with self.assertRaisesRegex(RuntimeError, "Reset failed"):
            client.reset("Next", 2001)
        self.assertIsNone(client.prompt)

    def test_wrong_step_and_chunk_shape_fail_closed(self):
        for response in ({**step_response(0), "episode_step": 1},
                         {**step_response(0), "model_actions": np.zeros((20, 20))},
                         {**step_response(0), "action": np.full(16, np.nan)}):
            client, _ = client_with_responses({"ok": True}, response)
            client.reset("Bell", 2000)
            with self.assertRaises(ValueError):
                client.predict(observation())
            self.assertIsNone(client.prompt)


class FakeEnv:
    step_lim = 9

    def __init__(self, success_at):
        self.success_at = success_at

    def setup_demo(self, **kwargs):
        self.take_action_cnt = 0
        self.eval_success, self.oracle, self.plan_success = False, False, True

    def play_once(self):
        self.oracle = True
        return {"info": {}}

    def check_success(self):
        return self.oracle or self.eval_success

    def close_env(self):
        pass

    def set_instruction(self, instruction):
        pass

    def get_obs(self):
        return observation(self.take_action_cnt)

    def take_action(self, action, action_type):
        assert action_type == "ee"
        np.testing.assert_array_equal(action, decoded()[0])
        self.take_action_cnt += 1
        self.eval_success = self.take_action_cnt == self.success_at


class RunnerTests(unittest.TestCase):
    def test_partial_cache_budget_and_success_keep_all_predictions(self):
        for success_at, count in [(3, 3), (100, 9)]:
            with self.subTest(count=count), tempfile.TemporaryDirectory() as tmp:
                client, _ = client_with_responses({"ok": True}, *[step_response(i) for i in range(count)])
                def writer(path, **kwargs):
                    path.touch()
                    return Mock()
                directory = Path(tmp)
                with patch("imageio.v2.get_writer", side_effect=writer):
                    result = run_episode(FakeEnv(success_at), {}, client,
                                         argparse.Namespace(task="click_bell", task_config="demo_clean"),
                                         2000, "task-name", directory)
                self.assertEqual(result["action_calls"], count)
                self.assertEqual(result["status"], "success" if count == 3 else "failure")
                with np.load(directory / "click_bell_ep2000_actions.npz") as trace:
                    self.assertEqual(trace["raw_actions"].shape, ((count + 6)//7, 20, 16))
                    self.assertEqual(trace["model_actions"].shape, ((count + 6)//7, 40, 20))
                    np.testing.assert_array_equal(trace["executed_actions"], np.tile(decoded()[0], (count, 1)))
                events = json.loads((directory / "click_bell_ep2000_requests.json").read_text())
                self.assertEqual(len(events), count + 1)
                self.assertTrue((directory / f"click_bell_ep2000_{int(result['success'])}.mp4").exists())

    def test_inference_error_retains_seed_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = client_with_responses({"ok": True}, {"error": "Inference failed"})
            with patch("imageio.v2.get_writer"):
                result = run_episode(FakeEnv(5), {}, client,
                                     argparse.Namespace(task="click_bell", task_config="demo_clean"),
                                     2000, "task-name", Path(tmp))
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["seed"], 2000)
            self.assertEqual(result["error"]["stage"], "inference")


class ServiceTests(unittest.TestCase):
    def test_reset_seed_and_bad_step_clear_history(self):
        wrapper, seed = Mock(), Mock()
        policy = EpisodePolicy(wrapper, Mock(), seed)
        with self.assertRaises(RuntimeError):
            policy.infer({"type": "step", "step": 0})
        self.assertTrue(policy.infer({"type": "reset", "seed": 5, "instruction": "Bell"})["ok"])
        seed.assert_called_once_with(5)
        with self.assertRaises(ValueError):
            policy.infer({"type": "step", "step": 1})
        self.assertIsNone(policy.instruction)
        self.assertGreaterEqual(wrapper.reset.call_count, 3)
        with self.assertRaises(ValueError):
            policy.infer({"type": "reset", "seed": True, "instruction": "Bell"})
        self.assertIsNone(policy.instruction)


if __name__ == "__main__":
    unittest.main()
