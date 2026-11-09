"""CPU protocol checks: episode isolation, checkpoint identity, and action prefixes."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from urllib.request import urlopen

import numpy as np

from policies.wam.assets import verify_file
from policies.wam.client import CAMERAS, CONTRACTS, PROTOCOL, WAMClient, format_observation, packb, unpackb
from policies.wam.serve import EpisodePolicy

ROOT = Path(__file__).resolve().parents[2]


def observation():
    return {"observation": {name: {"rgb": np.full((240, 320, 3), index, np.uint8)}
                            for index, name in enumerate(CAMERAS)},
            "joint_action": {"vector": np.arange(14, dtype=np.float32)}}


class Backend:
    def __init__(self, horizon):
        self.horizon = horizon
        self.calls = []
        self.resets = 0

    def reset(self):
        self.resets += 1

    def predict(self, obs, instruction):
        self.calls.append((obs, instruction))
        return np.arange(self.horizon * 14, dtype=np.float32).reshape(self.horizon, 14) / 10


class Connection:
    def __init__(self, policy, server):
        self.server = server
        horizon, length = CONTRACTS[policy]
        self.response = {"ok": True, "policy": policy, "protocol": PROTOCOL,
                         "action_horizon": horizon, "use_length": length, "action_type": "qpos", "action_dim": 14}
        self.closed = False

    def send(self, body):
        try:
            self.response = self.server.infer(unpackb(body))
        except Exception as exc:
            self.response = {"ok": False, "error": str(exc)}

    def recv(self, timeout=None):
        return packb(self.response)

    def close(self):
        self.closed = True


class PolicyProtocolTests(unittest.TestCase):
    def test_roundtrip_replanning_preserves_qpos_and_actual_instruction(self):
        for policy, (horizon, length) in CONTRACTS.items():
            with self.subTest(policy=policy):
                backend = Backend(horizon)
                seeds = []
                server = EpisodePolicy(backend, policy, seeds.append)
                connection = Connection(policy, server)
                with patch("policies.wam.client.connect", return_value=connection):
                    client = WAMClient(policy, "ws://fixture")
                with self.assertRaisesRegex(RuntimeError, "Reset"):
                    client.predict(observation())
                client.reset("lift the stapler, do not press it", 100024)
                actions, prediction = client.predict(observation())
                self.assertEqual(actions.shape, (length, 14))
                self.assertEqual(prediction["model_actions"].shape, (horizon, 14))
                np.testing.assert_array_equal(actions, prediction["model_actions"][:length])
                self.assertGreater(float(actions[-1, 0]), np.pi)
                self.assertGreater(float(actions[-1, 6]), 1.0)
                self.assertEqual(backend.calls[-1][1], "lift the stapler, do not press it")
                np.testing.assert_array_equal(backend.calls[-1][0]["joint_action"]["vector"], np.arange(14))
                decoded_obs = backend.calls[-1][0]
                self.assertTrue(decoded_obs["joint_action"]["vector"].flags.writeable)
                for camera in CAMERAS:
                    self.assertTrue(decoded_obs["observation"][camera]["rgb"].flags.writeable)
                self.assertEqual(seeds, [100024])
                client.reset("press the stapler", 100025)
                client.predict(observation())
                self.assertEqual(server.chunk, 1)
                self.assertEqual(seeds, [100024, 100025])
                self.assertEqual(backend.calls[-1][1], "press the stapler")
                client.close()
                self.assertTrue(connection.closed)

    def test_cross_policy_server_is_rejected(self):
        server = EpisodePolicy(Backend(16), "motus", lambda seed: None)
        connection = Connection("motus", server)
        with patch("policies.wam.client.connect", return_value=connection):
            with self.assertRaisesRegex(ValueError, "contract"):
                WAMClient("fastwam", "ws://fixture")
        self.assertTrue(connection.closed)

    def test_reordered_chunk_invalidates_episode_and_requires_reset(self):
        server = EpisodePolicy(Backend(32), "fastwam", lambda seed: None)
        server.infer({"type": "reset", "seed": 1, "instruction": "left arm"})
        request = {"type": "infer", "chunk": 1, "observation": format_observation(observation())}
        with self.assertRaisesRegex(ValueError, "consecutive"):
            server.infer(request)
        request["chunk"] = 0
        with self.assertRaisesRegex(RuntimeError, "Reset"):
            server.infer(request)
        server.infer({"type": "reset", "seed": 2, "instruction": "right arm"})
        self.assertEqual(server.infer(request)["chunk"], 0)

    def test_invalid_reset_does_not_leave_previous_episode_active(self):
        server = EpisodePolicy(Backend(32), "fastwam", lambda seed: None)
        for seed in (-1, 2**32, True):
            server.infer({"type": "reset", "seed": 1, "instruction": "left arm"})
            with self.assertRaises(ValueError):
                server.infer({"type": "reset", "seed": seed, "instruction": "right arm"})
            self.assertIsNone(server.instruction)

    def test_nonfinite_model_action_invalidates_server_and_client(self):
        backend = Backend(16)
        server = EpisodePolicy(backend, "motus", lambda seed: None)
        connection = Connection("motus", server)
        with patch("policies.wam.client.connect", return_value=connection):
            client = WAMClient("motus", "ws://fixture")
        client.reset("place left", 5)
        with patch.object(backend, "predict", return_value=np.full((16, 14), np.nan)):
            with self.assertRaisesRegex(RuntimeError, "finite"):
                client.predict(observation())
        self.assertIsNone(server.instruction)
        self.assertFalse(client.ready)
        with self.assertRaisesRegex(RuntimeError, "Reset"):
            client.predict(observation())

    def test_rgb_and_state_validation(self):
        obs = observation()
        obs["observation"]["head_camera"]["rgb"] = np.zeros((3, 240, 320), np.uint8)
        with self.assertRaisesRegex(ValueError, "HWC"):
            format_observation(obs)
        obs = observation()
        obs["joint_action"]["vector"][0] = np.inf
        with self.assertRaisesRegex(ValueError, "finite"):
            format_observation(obs)


class AssetIntegrityTests(unittest.TestCase):
    def test_same_size_corruption_fails_for_git_and_lfs_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weights"
            contents = b"checkpoint"
            checks = [{"size": len(contents), "sha256": hashlib.sha256(contents).hexdigest()},
                      {"size": len(contents), "git_blob_sha1": hashlib.sha1(
                          f"blob {len(contents)}\0".encode() + contents).hexdigest()}]
            for expected in checks:
                path.write_bytes(contents)
                verify_file(path, expected)
                path.write_bytes(b"X" + contents[1:])
                with self.assertRaisesRegex(ValueError, "hash mismatch"):
                    verify_file(path, expected)


class EvaluationTests(unittest.TestCase):
    def test_action_budget_full_predictions_and_final_verdict_are_preserved(self):
        from policies.wam.eval import run_episode
        spec = importlib.util.spec_from_file_location("joint_episode_fixtures", ROOT / "tests/vlact/test_client.py")
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        for policy, (horizon, length) in CONTRACTS.items():
            for success in (True, False):
                with self.subTest(policy=policy, success=success), tempfile.TemporaryDirectory() as tmp:
                    env = fixture.FakeEnv(success_at=10000)
                    env.finalize_policy_success = lambda: success
                    backend = Backend(horizon)
                    backend.predict = lambda obs, instruction: np.broadcast_to(fixture.chunk()[0], (horizon, 14)).copy()
                    server = EpisodePolicy(backend, policy, lambda seed: None)
                    connection = Connection(policy, server)
                    with patch("policies.wam.client.connect", return_value=connection):
                        client = WAMClient(policy, "ws://fixture")
                    def writer(path, **kwargs):
                        path.touch()
                        return Mock()
                    directory = Path(tmp) / "episode"
                    with patch("imageio.v2.get_writer", side_effect=writer):
                        result = run_episode(env, {}, client,
                            argparse.Namespace(policy=policy, task="click_bell", task_config="demo_clean"),
                            2000, "task-name", directory)
                    self.assertEqual(result["success"], success, result)
                    self.assertEqual(result["status"], "success" if success else "failure")
                    self.assertEqual(result["action_calls"], 53)
                    self.assertEqual(result["termination"], "action_limit")
                    with np.load(directory / "click_bell_ep2000_actions.npz") as actions:
                        self.assertEqual(actions["executed_actions"].shape, (53, 14))
                        chunks = (53 + length - 1) // length
                        self.assertEqual(actions["model_actions"].shape, (chunks, horizon, 14))
                        self.assertEqual(actions["raw_actions"].shape, (chunks, length, 14))
                    self.assertTrue((directory / f"click_bell_ep2000_{int(success)}.mp4").is_file())
                    diagnostic = json.loads((directory / "click_bell_ep2000_diagnostics.json").read_text())
                    self.assertEqual(diagnostic["policy"], policy)
                    self.assertNotIn("wrap to", diagnostic["action_log_semantics"])

    def test_summary_recognizes_new_models_without_inventing_complete_scores(self):
        from tools.summarize_formal_policy_results import snapshot
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for policy in CONTRACTS:
                (root / policy).mkdir()
            data = snapshot(root, blocks=1)
            self.assertEqual(set(data["policies"]), set(CONTRACTS))
            for totals in data["policies"].values():
                self.assertEqual(totals["recorded"], 0)
                self.assertIsNone(totals["overall_pct"])


class WebSocketServiceTests(unittest.TestCase):
    def test_exclusive_connection_error_recovery_and_fresh_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as socket_probe:
                socket_probe.bind(("127.0.0.1", 0))
                port = socket_probe.getsockname()[1]
            program = '''
from pathlib import Path
import sys
sys.path.insert(0, str(Path('tests/wam').resolve()))
from test_client import Backend
from policies.wam.client import PROTOCOL
from policies.wam.serve import EpisodePolicy, serve_policy
metadata = dict(ok=True, policy='fastwam', protocol=PROTOCOL, action_type='qpos',
                action_dim=14, action_horizon=32, use_length=24)
serve_policy(EpisodePolicy(Backend(32), 'fastwam', lambda seed: None), metadata,
             '127.0.0.1', int(sys.argv[1]), Path(sys.argv[2]))
'''
            with (Path(tmp) / "server.log").open("w+") as log:
                process = subprocess.Popen([sys.executable, "-c", program, str(port), str(Path(tmp) / "requests.jsonl")],
                                           cwd=ROOT, stdout=log, stderr=log)
                clients = []
                try:
                    deadline = time.monotonic() + 10
                    while True:
                        try:
                            with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=.2) as response:
                                self.assertEqual(response.status, 200)
                            break
                        except OSError:
                            if process.poll() is not None or time.monotonic() > deadline:
                                log.seek(0)
                                self.fail(log.read())
                            time.sleep(.02)
                    url = f"ws://127.0.0.1:{port}"
                    first = WAMClient("fastwam", url, timeout=2)
                    clients.append(first)
                    first.reset("lift", 4)
                    self.assertEqual(first.predict(observation())[0].shape, (24, 14))
                    from websockets.exceptions import ConnectionClosedError
                    with self.assertRaises(ConnectionClosedError) as rejected:
                        WAMClient("fastwam", url, timeout=2)
                    self.assertEqual(rejected.exception.rcvd.code, 1013)
                    first.predict(observation())  # A rejected connection must not reset the active episode.
                    first.connection.send(packb({"type": "infer", "chunk": 99}))
                    bad = unpackb(first.connection.recv(timeout=2))
                    self.assertFalse(bad["ok"])
                    with self.assertRaisesRegex(RuntimeError, "Reset"):
                        first.predict(observation())
                    first.reset("press", 5)
                    first.predict(observation())
                    first.close()
                    deadline = time.monotonic() + 2
                    while True:
                        try:
                            second = WAMClient("fastwam", url, timeout=2)
                            clients.append(second)
                            break
                        except ConnectionClosedError:
                            if time.monotonic() > deadline:
                                raise
                            time.sleep(.02)
                    # Check the server's own reset guard, independent of the client's local guard.
                    second.connection.send(packb({"type": "infer", "chunk": 0}))
                    self.assertIn("Reset", unpackb(second.connection.recv(timeout=2))["error"])
                    second.reset("right arm", 6)
                    second.predict(observation())
                finally:
                    for client in clients:
                        client.close()
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
