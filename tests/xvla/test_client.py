"""Codec, HTTP, episode isolation, and rollout termination without SAPIEN."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import json_numpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from policies.xvla.client import XVLAClient, decode_actions, decode_rotation, encode_proprio, encode_rotation
from policies.xvla.eval import run_episode, select_seeds
from policies.xvla.outputs import convert_legacy


def observation():
    return {"observation": {name: {"rgb": np.zeros((16, 16, 3), dtype=np.uint8)}
                            for name in ("head_camera", "left_camera", "right_camera")},
            "endpose": {"left_endpose": [0.1, 0.2, 0.3, 1, 0, 0, 0], "left_gripper": 1.0,
                        "right_endpose": [-0.2, 0.1, 0.4, 0.5, -0.5, 0.5, 0.5], "right_gripper": 0.0}}


def action_chunk(count=5):
    action = encode_proprio(observation())
    action[[9, 19]] = [0.8, 0.1]
    return np.tile(action, (count, 1))


def fake_video_writer(path, **kwargs):
    path.touch()
    return Mock()


class ClientTests(unittest.TestCase):
    def test_checkpoint_quaternion_convention(self):
        # Official training calls SciPy with wxyz numbers and scalar_first=False.
        np.testing.assert_allclose(encode_rotation([1, 0, 0, 0]), [1, 0, 0, -1, 0, 0])
        quaternions = np.array([[1, 0, 0, 0], [0.2, -0.4, 0.8, 0.3]])
        quaternions /= np.linalg.norm(quaternions, axis=1, keepdims=True)
        restored = decode_rotation(encode_rotation(quaternions))
        np.testing.assert_allclose(abs(np.sum(restored * quaternions, axis=1)), 1)

    def test_dual_arm_layout_and_grippers(self):
        decoded = decode_actions(action_chunk(1))[0]
        obs = observation()["endpose"]
        np.testing.assert_allclose(decoded[:7], obs["left_endpose"])
        np.testing.assert_allclose(decoded[8:15], obs["right_endpose"])
        self.assertEqual(decoded[7], -1)
        self.assertEqual(decoded[15], 1)

    def test_invalid_predictions(self):
        for bad in (np.zeros((1, 20)), np.ones((20,)), np.full((1, 20), np.nan)):
            with self.assertRaises(ValueError):
                decode_actions(bad)
        bad = action_chunk(1)
        bad[0, 19] = 2
        with self.assertRaises(ValueError):
            decode_actions(bad)

    def test_http_payload_feedback_and_reset(self):
        client = XVLAClient(timeout=7)
        client.session = Mock()
        client.session.post.return_value.json.return_value = {"action": action_chunk(1).tolist()}
        obs = observation()
        decoded, _ = client.predict(obs, "click bell")
        payload = client.session.post.call_args.kwargs["json"]
        self.assertEqual(payload["domain_id"], 6)
        self.assertEqual(payload["language_instruction"], "click bell")
        self.assertEqual(client.session.post.call_args.kwargs["timeout"], 7)
        self.assertEqual(set(payload), {"domain_id", "steps", "proprio", "language_instruction", "image0", "image1", "image2"})
        command = decoded[0].copy()
        command[0] = 0.55
        client.record_action(command)
        client.predict(obs, "click bell")
        payload = client.session.post.call_args.kwargs["json"]
        self.assertAlmostEqual(json_numpy.loads(payload["proprio"])[0], 0.55)
        self.assertEqual(obs["endpose"]["left_endpose"][0], 0.1)
        client.reset()
        client.predict(obs, "next episode")
        payload = client.session.post.call_args.kwargs["json"]
        self.assertAlmostEqual(json_numpy.loads(payload["proprio"])[0], 0.1)

    def test_http_errors_are_not_actions(self):
        client = XVLAClient()
        client.session = Mock()
        client.session.post.return_value.json.return_value = {"error": "inference failed"}
        with self.assertRaises(ValueError):
            client.predict(observation(), "click bell")


class FakeEnv:
    def __init__(self, success_at):
        self.success_at = success_at
        self.oracle = False

    def setup_demo(self, **kwargs):
        self.oracle = False
        self.take_action_cnt = 0
        self.step_lim = 3
        self.eval_success = False
        self.plan_success = True

    def play_once(self):
        self.oracle = True
        return {"info": {}}

    def check_success(self):
        return self.oracle or self.eval_success

    def take_action(self, action, action_type):
        assert action_type == "ee"
        self.take_action_cnt += 1
        self.eval_success = self.take_action_cnt == self.success_at

    def get_obs(self):
        return observation()

    def set_instruction(self, instruction):
        self.instruction = instruction

    def close_env(self):
        pass


class RunnerTests(unittest.TestCase):
    def test_chunks_stop_at_success_and_budget(self):
        for success_at, expected_calls, status in ((2, 2, "success"), (100, 3, "failure")):
            with self.subTest(success_at=success_at), tempfile.TemporaryDirectory() as tmp:
                client = Mock()
                client.predict.return_value = (decode_actions(action_chunk()),
                    {"raw_actions": action_chunk(), "proprio": encode_proprio(observation()), "latency_seconds": 0.1})
                with patch("imageio.v2.get_writer", side_effect=fake_video_writer), redirect_stdout(io.StringIO()):
                    result = run_episode(FakeEnv(success_at), {}, client, argparse.Namespace(task="click_bell"),
                                         2000, "task-name", Path(tmp) / "episode")
                self.assertEqual(result["status"], status)
                self.assertEqual(result["action_calls"], expected_calls)
                self.assertEqual(client.record_action.call_count, expected_calls)
                client.reset.assert_called_once()
                directory = Path(tmp) / "episode"
                prefix = "click_bell_ep2000"
                for suffix in (".log", "_summary.json", "_status.json", "_action_logs.json", "_timings.json",
                               "_instruction.txt", "_step0000.png", f"_{int(status == 'success')}.mp4"):
                    self.assertTrue((directory / (prefix + suffix)).is_file(), suffix)
                summary = json.loads((directory / (prefix + "_summary.json")).read_text())
                outcome = json.loads((directory / (prefix + "_status.json")).read_text())
                timings = json.loads((directory / (prefix + "_timings.json")).read_text())
                chunks = json.loads((directory / (prefix + "_action_logs.json")).read_text())
                self.assertEqual(outcome["status"], "policy_" + status)
                self.assertEqual(summary["steps"], expected_calls)
                self.assertEqual(len(timings), expected_calls)
                self.assertEqual(len(chunks[0]["ROBOT_LEFT_TRANS"]), 5)  # Keep unexecuted predictions.
                self.assertGreater(timings[0]["inference_time_sec"], 0)
                self.assertEqual(timings[1]["inference_time_sec"], 0)
                self.assertAlmostEqual(summary["total_step_time_sec"],
                                       summary["total_inference_time_sec"] + summary["total_env_step_time_sec"])
                self.assertIn("click bell", (directory / (prefix + "_instruction.txt")).read_text())
                import imageio.v2 as imageio
                self.assertEqual(imageio.imread(directory / (prefix + "_step0000.png")).shape, (16, 48, 3))

    def test_inference_error_keeps_exact_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = Mock()
            client.predict.side_effect = TimeoutError("server unavailable")
            with patch("imageio.v2.get_writer"), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = run_episode(FakeEnv(2), {}, client, argparse.Namespace(task="click_bell"),
                                     2000, "task-name", Path(tmp) / "episode")
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["seed"], 2000)
            self.assertEqual(result["error"]["stage"], "inference")
            self.assertEqual(result["action_calls"], 0)
            directory = Path(tmp) / "episode"
            status = json.loads((directory / "click_bell_ep2000_status.json").read_text())
            self.assertEqual(status["status"], "execution_error")
            self.assertIn("server unavailable", (directory / "click_bell_ep2000.log").read_text())
            self.assertEqual(json.loads((directory / "click_bell_ep2000_action_logs.json").read_text()), [])

    def test_manifest_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "arm_select.json"
            path.write_text(json.dumps({"schema_version": 1, "task": "arm_select", "task_config": "demo_clean",
                                        "seeds": [100000, 100001, 100004, 100005]}))
            args = argparse.Namespace(task="arm_select", task_config="demo_clean", seed_manifest=path,
                                      seeds=None, blocks=1, instruction_type=None)
            seeds, _, split = select_seeds(args)
            self.assertEqual(seeds, [100000, 100001])
            self.assertEqual(split, "unseen")
            args.instruction_type = "task-name"
            with self.assertRaises(ValueError):
                select_seeds(args)
            args.instruction_type = None
            args.seed_manifest = None
            with self.assertRaises(ValueError):
                select_seeds(args)

    def test_observed_mode_must_match_exact_seed(self):
        class WrongModeEnv(FakeEnv):
            def setup_demo(self, **kwargs):
                super().setup_demo(**kwargs)
                self.mode = "left"

        with tempfile.TemporaryDirectory() as tmp:
            client = Mock()
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = run_episode(WrongModeEnv(2), {}, client, argparse.Namespace(task="arm_select"),
                                     100001, "unseen", Path(tmp) / "episode")
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["mode"], "right")
            self.assertIn("does not match", result["error"]["message"])
            client.predict.assert_not_called()

    def test_second_chunk_timing_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = Mock()
            client.predict.return_value = (decode_actions(action_chunk(2)),
                {"raw_actions": action_chunk(2), "proprio": encode_proprio(observation()), "latency_seconds": 0.1})
            directory = Path(tmp) / "episode"
            args = argparse.Namespace(task="click_bell")
            with patch("imageio.v2.get_writer"):
                run_episode(FakeEnv(100), {}, client, args, 2000, "task-name", directory)
            timings = json.loads((directory / "click_bell_ep2000_timings.json").read_text())
            self.assertGreater(timings[2]["inference_time_sec"], 0)
            with self.assertRaises(FileExistsError):
                run_episode(FakeEnv(100), {}, client, args, 2000, "task-name", directory)


class OutputConversionTests(unittest.TestCase):
    def test_legacy_conversion_preserves_evidence_and_marks_missing_measurements(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, dest = Path(tmp) / "old", Path(tmp) / "new"
            episode = source / "seed-100001"
            episode.mkdir(parents=True)
            record = {"task": "arm_select", "seed": 100001, "status": "failure", "success": False,
                      "instruction": "Use the right arm.", "instruction_type": "unseen", "mode": "right",
                      "action_calls": 3, "chunks": 2, "elapsed_seconds": 10, "signals": {"lifted": False}}
            (source / "run.json").write_text(json.dumps({"arguments": {"task": "arm_select", "task_config": "demo_clean"},
                                                       "seeds": [100000, 100001]}))
            (source / "console.log").write_text("Setup log\nPolicy seed=100001, instruction='Use the right arm.'\nDone\n")
            (episode / "result.json").write_text(json.dumps(record))
            (episode / "rollout.mp4").write_bytes(b"original-video-bytes")
            np.savez(episode / "initial_observation.npz", proprio=encode_proprio(observation()),
                     **{k: v["rgb"] for k, v in observation()["observation"].items()})
            raw = action_chunk()
            np.savez(episode / "actions.npz", raw_actions=raw, chunk_lengths=[2, 3],
                     executed_actions=decode_actions(raw)[:3], request_latency_seconds=[0.2, 0.4])
            hashes = {p.relative_to(source): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in source.rglob("*") if p.is_file()}
            convert_legacy(source, dest)
            for relative, digest in hashes.items():
                self.assertEqual(hashlib.sha256((source / relative).read_bytes()).hexdigest(), digest)
            for before, after in ((source / "run.json", dest / "run.json"),
                                  (episode / "result.json", dest / "arm_select_ep100001_result.json"),
                                  (episode / "actions.npz", dest / "arm_select_ep100001_actions.npz"),
                                  (episode / "rollout.mp4", dest / "arm_select_ep100001_0.mp4")):
                self.assertEqual(before.read_bytes(), after.read_bytes())
            summary = json.loads((dest / "arm_select_ep100001_summary.json").read_text())
            self.assertFalse(summary["success"])
            self.assertIsNone(summary["total_env_step_time_sec"])
            self.assertIsNone(summary["total_step_time_sec"])
            self.assertIsNone(summary["grasp_target_correct"])
            self.assertAlmostEqual(summary["total_inference_time_sec"], 0.6)
            self.assertEqual(summary["signals"], record["signals"])
            timings = json.loads((dest / "arm_select_ep100001_timings.json").read_text())
            self.assertEqual([r["inference_time_sec"] for r in timings], [0.2, 0, 0.4])
            self.assertTrue(all(r["env_step_time_sec"] is None for r in timings))
            chunks = json.loads((dest / "arm_select_ep100001_action_logs.json").read_text())
            self.assertEqual([len(c["ROBOT_RIGHT_TRANS"]) for c in chunks], [2, 3])
            np.testing.assert_allclose(chunks[0]["ROBOT_LEFT_GRIPPER"], raw[:2, 9:10])
            np.testing.assert_allclose(chunks[1]["ROBOT_RIGHT_ROT_6D"], raw[2:, 13:19])
            status = json.loads((dest / "arm_select_ep100001_status.json").read_text())
            self.assertEqual(status, {"task": "arm_select", "seed": 100001, "mode": "right", "block": 0,
                                      "status": "policy_failure", "detail": None, "attempts": 1})
            with self.assertRaises(FileExistsError):
                convert_legacy(source, dest)


if __name__ == "__main__":
    unittest.main()
