"""Protocol, action ordering, reset isolation and exact action-budget evidence."""

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
from policies.lingbot_vla.client import (  # noqa: E402
    CAMERAS, PROTOCOL, LingBotVLAClient, decode_actions, packb, unpackb,
)
from policies.lingbot_vla.eval import run_episode  # noqa: E402


def observation(step=0):
    return {"observation": {name: {"rgb": np.full((16, 16, 3), step + i, dtype=np.uint8)}
                            for i, name in enumerate(CAMERAS)},
            "endpose": {"left_endpose": [.1, .2, .3, .5, -.5, .5, .5], "left_gripper": .3,
                        "right_endpose": [-.2, .3, .4, 1., 0., 0., 0.], "right_gripper": .7},
            "joint_action": {"vector": np.arange(14, dtype=np.float32) / 20 + step / 100}}


def chunk():
    return np.broadcast_to(np.arange(14, dtype=np.float32) / 20, (50, 14)).copy()


def client_with_responses(*responses, metadata=None):
    conn = Mock()
    metadata = metadata if metadata is not None else {"protocol": PROTOCOL, "use_length": 50, "action_type": "qpos"}
    conn.recv.side_effect = [packb(metadata)] + [r if isinstance(r, str) else packb(r) for r in responses]
    with patch("policies.lingbot_vla.client.connect", return_value=conn):
        client = LingBotVLAClient()
    return client, conn


class ClientTests(unittest.TestCase):
    def test_absolute_joint_order_and_continuous_grippers(self):
        actions = chunk()
        np.testing.assert_array_equal(decode_actions(actions), actions)
        np.testing.assert_array_equal(decode_actions(actions)[:, [6, 13]], actions[:, [6, 13]])
        for bad in (np.zeros((50, 16)), np.zeros((0, 14)), np.zeros((51, 14)), np.full((50, 14), np.nan)):
            with self.assertRaises(ValueError):
                decode_actions(bad)

    def test_reset_and_fresh_observation_each_chunk(self):
        client, conn = client_with_responses({}, {"action": chunk()}, {"action": chunk()}, {})
        with self.assertRaises(RuntimeError):
            client.predict(observation())
        client.reset("Use the right arm", 100001)
        actions, _ = client.predict(observation())
        np.testing.assert_array_equal(actions, chunk())
        client.predict(observation(50))
        sent = [unpackb(call.args[0]) for call in conn.send.call_args_list]
        self.assertEqual(sent[0], {"reset": True, "robo_name": "robotwin", "seed": 100001})
        self.assertEqual(sent[1]["task"], "Use the right arm")
        np.testing.assert_array_equal(sent[2]["observation.state"], observation(50)["joint_action"]["vector"])
        for i, key in enumerate(("cam_high", "cam_left_wrist", "cam_right_wrist")):
            self.assertEqual(sent[2]["observation.images." + key][0, 0, 0], 50 + i)
        self.assertEqual([r["kind"] for r in client.requests], ["reset", "predict", "predict"])
        client.reset("Use the left arm", 100000)
        self.assertEqual(client.prompt, "Use the left arm")
        self.assertEqual(len(client.requests), 1)

    def test_wrong_protocol_and_invalid_requests_fail_closed(self):
        for metadata in ({}, {"protocol": "lingbot_va_robotwin_v1"},
                         {"protocol": PROTOCOL, "use_length": True, "action_type": "qpos"},
                         {"protocol": PROTOCOL, "use_length": 50, "action_type": "ee"}):
            with self.assertRaises(ValueError):
                client_with_responses(metadata=metadata)
        client, _ = client_with_responses({}, "Inference failed", "Reset failed")
        for seed in (True, -1, 2**32, 1.5):
            with self.assertRaises(ValueError):
                client.reset("Bell", seed)
        client.reset("Bell", 2000)
        with self.assertRaisesRegex(RuntimeError, "Inference failed"):
            client.predict(observation())
        with self.assertRaisesRegex(RuntimeError, "Reset failed"):
            client.reset("Next", 2001)
        with self.assertRaises(RuntimeError):
            client.predict(observation())

    def test_wire_format_matches_official_numpy_codec(self):
        source = ROOT / "third_party/lingbot-vla/deploy/msgpack_numpy.py"
        if not source.exists():
            self.skipTest("Optional upstream checkout unavailable")
        import runpy
        upstream = runpy.run_path(str(source))
        value = {"action": chunk()}
        np.testing.assert_array_equal(upstream["unpackb"](packb(value))["action"], chunk())
        np.testing.assert_array_equal(unpackb(upstream["Packer"]().pack(value))["action"], chunk())


class FakeEnv:
    def __init__(self, success_at):
        self.success_at = success_at

    def setup_demo(self, **kwargs):
        self.take_action_cnt, self.step_lim = 0, 53
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
                client, _ = client_with_responses({}, {"action": chunk()}, {"action": chunk()})
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
                status = json.loads((directory / (prefix + "_status.json")).read_text())
                self.assertEqual(status["status"], "policy_" + result["status"])
                with np.load(directory / (prefix + "_actions.npz")) as trace:
                    self.assertEqual(trace["executed_actions"].shape, (steps, 14))
                    self.assertEqual(trace["raw_actions"].shape, (1 if steps == 5 else 2, 50, 14))
                    np.testing.assert_array_equal(trace["executed_actions"], np.tile(chunk()[0], (steps, 1)))
                timings = json.loads((directory / (prefix + "_timings.json")).read_text())
                self.assertEqual(len(timings), steps)
                logs = json.loads((directory / (prefix + "_action_logs.json")).read_text())
                self.assertIsNone(logs[0]["ROBOT_LEFT_ROT_MAT"])
                self.assertEqual(len(logs[0]["ROBOT_LEFT_JOINT_POS"]), 50)

    def test_reset_error_preserves_seed_and_request_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = client_with_responses("Reset failed")
            with patch("imageio.v2.get_writer"):
                result = run_episode(FakeEnv(5), {}, client,
                                     argparse.Namespace(task="click_bell", task_config="demo_clean"),
                                     2000, "task-name", Path(tmp))
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["seed"], 2000)
            self.assertEqual(result["error"]["stage"], "server_reset")
            requests = json.loads((Path(tmp) / "click_bell_ep2000_requests.json").read_text())
            self.assertIn("Reset failed", requests[0]["error"])


if __name__ == "__main__":
    unittest.main()
