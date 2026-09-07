"""HTTP/image/state contract, reproducible seeds and exact action-budget evidence."""
import argparse
import base64
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from policies.dm05.client import (  # noqa: E402
    CAMERAS, PROTOCOL, ROBOT_TYPE, DM05Client, decode_actions, format_observation,
)
from policies.dm05.eval import run_episode  # noqa: E402


def observation(step=0):
    return {"observation": {name: {"rgb": np.broadcast_to(np.array([step + i, 40, 90], dtype=np.uint8),
                                                                       (16, 20, 3)).copy()}
                            for i, name in enumerate(CAMERAS)},
            "endpose": {"left_endpose": [.1, .2, .3, .5, -.5, .5, .5],
                        "right_endpose": [-.2, .3, .4, 1., 0., 0., 0.]},
            "joint_action": {"vector": np.arange(14, dtype=np.float32) / 20 + step / 100}}


def chunk():
    return np.broadcast_to(np.arange(14, dtype=np.float32) / 20, (50, 14)).copy()


def client_with_responses(*responses, metadata=None):
    session = Mock()
    metadata = metadata if metadata is not None else {
        "protocol": PROTOCOL, "use_length": 50, "action_type": "qpos", "action_mode": "absolute",
        "robot_type": ROBOT_TYPE, "diffusion_steps": 10}
    values = []
    for payload in (metadata, *responses):
        response = Mock()
        if isinstance(payload, Exception):
            response.raise_for_status.side_effect = payload
        else:
            response.json.return_value = payload
        values.append(response)
    session.request.side_effect = values
    with patch("policies.dm05.client.requests.Session", return_value=session):
        client = DM05Client()
    return client, session


class ClientTests(unittest.TestCase):
    def test_absolute_joint_order_and_continuous_grippers(self):
        actions = chunk()
        np.testing.assert_array_equal(decode_actions(actions), actions)
        for bad in (np.zeros((50, 16)), np.zeros((0, 14)), np.zeros((51, 14)), np.full((50, 14), np.nan)):
            with self.assertRaises(ValueError):
                decode_actions(bad)

    def test_lossless_rgb_slots_and_measured_state(self):
        obs = observation()
        encoded = format_observation(obs, "Use the right arm")
        for slot, name in enumerate(CAMERAS, 1):
            rgb = np.asarray(Image.open(BytesIO(base64.b64decode(encoded["images"][str(slot)]))))
            np.testing.assert_array_equal(rgb, obs["observation"][name]["rgb"])
        np.testing.assert_array_equal(encoded["state"], obs["joint_action"]["vector"])
        self.assertEqual(encoded["prompt"], "Use the right arm")
        obs["joint_action"]["vector"][0] = np.nan
        with self.assertRaises(ValueError):
            format_observation(obs, "Invalid state")

    def test_reset_seed_schedule_and_fresh_observations(self):
        client, session = client_with_responses({"status": "ok"}, {"actions": chunk().tolist()},
                                                {"actions": chunk().tolist()}, {"status": "ok"})
        with self.assertRaises(RuntimeError):
            client.predict(observation())
        client.reset("Use the right arm", 2**32 - 1)
        client.predict(observation())
        client.predict(observation(50))
        payloads = [c.kwargs["json"] for c in session.request.call_args_list][2:]
        self.assertEqual([p["sampling"]["seed"] for p in payloads], [2**32 - 1, 0])
        np.testing.assert_array_equal(payloads[1]["observation"]["state"], observation(50)["joint_action"]["vector"])
        self.assertEqual([e["kind"] for e in client.requests], ["reset", "predict", "predict"])
        client.reset("Use the left arm", 100000)
        self.assertEqual(client.chunk_index, 0)
        self.assertEqual(client.prompt, "Use the left arm")

    def test_wrong_protocol_and_failed_reset(self):
        for metadata in ({}, {"protocol": "vlact_robotwin_v1"}):
            with self.assertRaises(ValueError):
                client_with_responses(metadata=metadata)
        client, _ = client_with_responses({"status": "ok"}, requests.HTTPError("Reset failed"))
        for seed in (True, -1, 2**32, 1.5):
            with self.assertRaises(ValueError):
                client.reset("Bell", seed)
        client.reset("Bell", 2000)
        with self.assertRaises(requests.HTTPError):
            client.reset("Next", 2001)
        with self.assertRaises(RuntimeError):
            client.predict(observation())


class FakeEnv:
    step_lim = 53

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
        assert action_type == "qpos"
        np.testing.assert_array_equal(action, chunk()[0])
        self.take_action_cnt += 1
        self.eval_success = self.take_action_cnt == self.success_at


class RunnerTests(unittest.TestCase):
    def test_success_and_partial_chunk_budget_keep_full_evidence(self):
        for success_at, steps in ((5, 5), (100, 53)):
            with self.subTest(steps=steps), tempfile.TemporaryDirectory() as tmp:
                client, _ = client_with_responses({"status": "ok"}, {"actions": chunk().tolist()}, {"actions": chunk().tolist()})
                def writer(path, **kwargs):
                    path.touch()
                    return Mock()
                directory = Path(tmp)
                with patch("imageio.v2.get_writer", side_effect=writer):
                    result = run_episode(FakeEnv(success_at), {}, client,
                                         argparse.Namespace(task="click_bell", task_config="demo_clean"),
                                         2000, "task-name", directory)
                self.assertEqual(result["action_calls"], steps)
                self.assertEqual(result["status"], "success" if steps == 5 else "failure")
                prefix = "click_bell_ep2000"
                self.assertTrue((directory / f"{prefix}_{int(result['success'])}.mp4").exists())
                with np.load(directory / (prefix + "_actions.npz")) as trace:
                    self.assertEqual(trace["raw_actions"].shape, (1 if steps == 5 else 2, 50, 14))
                    np.testing.assert_array_equal(trace["executed_actions"], np.tile(chunk()[0], (steps, 1)))
                timings = json.loads((directory / (prefix + "_timings.json")).read_text())
                self.assertEqual(len(timings), steps)
                logs = json.loads((directory / (prefix + "_action_logs.json")).read_text())
                self.assertIsNone(logs[0]["ROBOT_LEFT_ROT_MAT"])

    def test_reset_error_preserves_seed_and_request_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = client_with_responses(requests.HTTPError("Reset failed"))
            with patch("imageio.v2.get_writer"):
                result = run_episode(FakeEnv(5), {}, client,
                                     argparse.Namespace(task="click_bell", task_config="demo_clean"),
                                     2000, "task-name", Path(tmp))
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["seed"], 2000)
            self.assertEqual(result["error"]["stage"], "server_reset")
            events = json.loads((Path(tmp) / "click_bell_ep2000_requests.json").read_text())
            self.assertIn("Reset failed", events[0]["error"])


if __name__ == "__main__":
    unittest.main()
