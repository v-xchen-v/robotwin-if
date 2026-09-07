"""Checkpoint codec, stateful RPC ordering, and bounded rollouts without SAPIEN/GPU."""

import argparse
import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import msgpack
import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from policies.lingbot_va.client import LingBotClient, decode_actions, encode_proprio, packb, unpackb  # noqa: E402
from policies.lingbot_va.eval import run_episode  # noqa: E402


def observation(step=0):
    return {"observation": {name: {"rgb": np.full((16, 16, 3), step, dtype=np.uint8)}
                            for name in ("head_camera", "left_camera", "right_camera")},
            "endpose": {"left_endpose": [.1, .2, .3, .5, -.5, .5, .5], "left_gripper": 1.,
                        "right_endpose": [-.2, .3, .4, 1., 0., 0., 0.], "right_gripper": 0.},
            "joint_action": {"vector": np.zeros(14)}}


def chunk(first=False):
    raw = np.zeros((16, 2, 16), dtype=np.float32)
    raw[0] = .1
    raw[3:7] = np.array([.2, .3, .4, .5])[:, None, None]
    raw[8] = -.1
    raw[11:15] = np.array([.3, .5, -.4, .2])[:, None, None]
    raw[[7, 15]] = .9
    if first:
        raw[:, 0] = 0  # The initial conditioning frame must not be executed/decoded.
    return raw


def client_with_responses(*responses):
    conn = Mock()
    conn.recv.side_effect = [packb({"policy": "lingbot_va"})] + [r if isinstance(r, str) else packb(r) for r in responses]
    with patch("policies.lingbot_va.client.connect", return_value=conn):
        client = LingBotClient()
    return client, conn


class ClientTests(unittest.TestCase):
    def test_msgpack_matches_upstream_numpy_envelope(self):
        array = np.arange(12, dtype=np.float32).reshape(3, 4)
        envelope = msgpack.unpackb(packb({"action": array}))["action"]
        self.assertEqual(envelope[b"__ndarray__"], True)
        self.assertEqual(envelope[b"data"], array.tobytes())
        self.assertEqual(envelope[b"dtype"], "<f4")
        np.testing.assert_array_equal(unpackb(packb({"action": array}))["action"], array)
        with self.assertRaises(ValueError):
            packb(np.array([object()], dtype=object))

    def test_relative_translation_rotation_and_gripper(self):
        initial = encode_proprio(observation())
        relative = chunk()[:, 0].T
        absolute = decode_actions(relative, initial)
        np.testing.assert_allclose(absolute[:, 0], .2)
        np.testing.assert_allclose(absolute[:, 8], -.3)
        np.testing.assert_allclose(absolute[:, [7, 15]], .9)
        expected = Rotation.from_quat(initial[3:7]).as_matrix() @ Rotation.from_quat(relative[0, 3:7]).as_matrix()
        np.testing.assert_allclose(Rotation.from_quat(absolute[0, 3:7]).as_matrix(), expected, atol=1e-7)
        np.testing.assert_allclose(np.linalg.norm(absolute[:, 3:7], axis=1), 1.)

    def test_codec_matches_pinned_official_client(self):
        source = ROOT / "third_party/lingbot-va/evaluation/robotwin/eval_polict_client_openpi.py"
        if not source.exists():
            self.skipTest("Optional upstream checkout unavailable")
        tree = ast.parse(source.read_text())
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("add_eef_pose", "add_init_pose")]
        namespace = {"np": np, "R": Rotation}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)
        relative = chunk()[:, 1].T
        initial = encode_proprio(observation())
        expected = np.stack([namespace["add_init_pose"](r, initial) for r in relative])
        np.testing.assert_allclose(decode_actions(relative, initial), expected)

    def test_reset_prediction_cache_and_frame_sampling_order(self):
        client, conn = client_with_responses({}, {"action": chunk(first=True)}, {}, {"action": chunk()}, {})
        client.reset("Pick up the block", 100000)
        actions, prediction = client.predict(observation())
        self.assertEqual(actions.shape, (16, 16))
        self.assertEqual(prediction["skipped_frames"], 1)
        for step in range(1, 17):
            client.observe_execution(observation(step))
        actions, prediction = client.predict(observation(16))
        self.assertEqual(actions.shape, (32, 16))
        self.assertEqual(prediction["skipped_frames"], 0)
        sent = [unpackb(call.args[0]) for call in conn.send.call_args_list]
        self.assertTrue(sent[0]["reset"])
        self.assertEqual(sent[0]["seed"], 100000)
        self.assertTrue(sent[2]["compute_kv_cache"])
        self.assertEqual([int(o["observation.images.cam_high"][0, 0, 0]) for o in sent[2]["obs"]], [4, 8, 12, 16])
        np.testing.assert_array_equal(sent[2]["state"], chunk(first=True))
        self.assertEqual([r["kind"] for r in client.requests], ["reset", "predict", "cache", "predict"])
        client.observe_execution(observation(17))
        with self.assertRaisesRegex(RuntimeError, "partially executed"):
            client.predict(observation(17))
        client.reset("Next episode", 100001)
        self.assertIsNone(client.pending)
        self.assertIsNone(client.initial_pose)
        self.assertEqual(len(client.requests), 1)

    def test_server_error_and_invalid_tensor_are_not_actions(self):
        for response in ("Inference failed", {"action": np.zeros((14, 2, 16))}, {"action": np.full((16, 2, 16), np.nan)}):
            client, _ = client_with_responses({}, response)
            client.reset("Click the bell", 2000)
            with self.assertRaises((RuntimeError, ValueError)):
                client.predict(observation())


class FakeEnv:
    def __init__(self, success_at):
        self.success_at = success_at

    def setup_demo(self, **kwargs):
        self.take_action_cnt, self.step_lim = 0, 19
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
        self.take_action_cnt += 1
        self.eval_success = self.take_action_cnt == self.success_at


class RunnerTests(unittest.TestCase):
    def test_success_and_budget_preserve_complete_traces(self):
        for success_at, steps in ((5, 5), (100, 19)):
            with self.subTest(success_at=success_at), tempfile.TemporaryDirectory() as tmp:
                client, _ = client_with_responses({}, {"action": chunk(True)}, {}, {"action": chunk()})
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
                status = json.loads((directory / (prefix + "_status.json")).read_text())
                self.assertEqual(status["status"], "policy_" + result["status"])
                self.assertTrue((directory / f"{prefix}_{int(result['success'])}.mp4").exists())
                timings = json.loads((directory / (prefix + "_timings.json")).read_text())
                self.assertEqual(len(timings), steps)
                with np.load(directory / (prefix + "_actions.npz")) as trace:
                    self.assertEqual(len(trace["executed_actions"]), steps)
                    self.assertEqual(trace["raw_actions"].shape[1:], (16, 2, 16))
                logs = json.loads((directory / (prefix + "_action_logs.json")).read_text())
                self.assertIsNone(logs[0]["ROBOT_LEFT_ROT_MAT"][0])
                self.assertEqual(len(logs[0]["ROBOT_LEFT_TRANS"]), 32)

    def test_reset_error_keeps_seed_and_rpc_evidence(self):
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
