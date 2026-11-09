"""CPU checks for X-WAM's coordinate transforms, sequential deltas and EE rollout."""

import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
from scipy.spatial.transform import Rotation

from policies.lingbot_va.client import packb, unpackb
from policies.xwam.client import (BASE_COORD_XFORM, CAMERAS, CONTRACT, XWAMClient,
                                  decode_actions, encode_proprio, format_observation,
                                  native_proprio, prediction_seed)
from policies.xwam.serve import XWAMEpisodePolicy


def observation():
    result = {"observation": {name: {"rgb": np.full((240, 320, 3), i, np.uint8)}
                              for i, name in enumerate(CAMERAS)},
              "joint_action": {"vector": np.arange(14, dtype=np.float64)}, "endpose": {}}
    for arm, pos, angles, grip in (("left", [.2, -.3, 1.], [.4, -.6, .2], .5),
                                   ("right", [-.2, .3, .9], [-.3, .7, .8], .25)):
        quat = Rotation.from_euler("xyz", angles).as_quat()[[3, 0, 1, 2]]
        result["endpose"][arm + "_endpose"] = np.r_[pos, quat]
        result["endpose"][arm + "_gripper"] = grip
    return result


class Backend:
    def __init__(self):
        self.calls = []
        self.actions = np.zeros((32, 14), dtype=np.float64)

    def reset(self):
        pass

    def predict(self, obs, instruction, seed):
        self.calls.append((obs, instruction, seed))
        return self.actions.copy()


class Connection:
    def __init__(self, server):
        self.server = server
        self.response = {"ok": True, "policy": "xwam", **CONTRACT}

    def send(self, body):
        try:
            self.response = self.server.infer(unpackb(body))
        except Exception as exc:
            self.response = {"ok": False, "error": str(exc)}

    def recv(self, timeout=None):
        return packb(self.response)

    def close(self):
        pass


def connected_client():
    backend = Backend()
    server = XWAMEpisodePolicy(backend, "xwam", lambda seed: None)
    with patch("policies.wam.client.connect", return_value=Connection(server)):
        client = XWAMClient("ws://fixture")
    return client, backend


class CodecTests(unittest.TestCase):
    def test_zero_deltas_round_trip_both_native_poses(self):
        obs = observation()
        decoded = decode_actions(np.zeros((32, 14)), encode_proprio(obs))
        np.testing.assert_allclose(decoded, np.tile(native_proprio(obs), (32, 1)), atol=1e-14)

    def test_translations_grippers_and_noncommuting_rotations_accumulate(self):
        obs = observation()
        deltas = np.zeros((32, 14))
        deltas[:, 0], deltas[:, 8], deltas[:, 6] = .01, -.02, .1
        deltas[0, 3], deltas[1, 4] = np.pi/2, np.pi/2
        decoded = decode_actions(deltas, encode_proprio(obs))
        native = native_proprio(obs)
        np.testing.assert_allclose(decoded[:, :3], native[:3] + np.arange(1, 33)[:, None] * [0, .01, 0], atol=1e-14)
        np.testing.assert_allclose(decoded[:, 8:11], native[8:11] + np.arange(1, 33)[:, None] * [.02, 0, 0], atol=1e-14)
        np.testing.assert_allclose(decoded[:, 7], .5 + np.arange(1, 33) * .1)
        r0 = Rotation.from_quat(native[3:7][[1, 2, 3, 0]]).as_matrix()
        dx = Rotation.from_rotvec([np.pi/2, 0, 0]).as_matrix()
        dy = Rotation.from_rotvec([0, np.pi/2, 0]).as_matrix()
        expected = BASE_COORD_XFORM.T @ dy @ dx @ BASE_COORD_XFORM @ r0
        actual = Rotation.from_quat(decoded[1, 3:7][[1, 2, 3, 0]]).as_matrix()
        np.testing.assert_allclose(actual, expected, atol=1e-14)

    def test_transport_preserves_precision_instruction_and_chunk_seed(self):
        client, backend = connected_client()
        backend.actions[0, 0] = .0123456789012345
        with self.assertRaisesRegex(RuntimeError, "Reset"):
            client.predict(observation())
        client.reset("Lift the stapler.", 110001)
        for step in (0, 32):
            actions, pred = client.predict(observation())
            self.assertEqual(actions.shape, (32, 16))
            self.assertEqual(pred["model_actions"][0, 0], backend.actions[0, 0])
            self.assertEqual(backend.calls[-1][1:], ("Lift the stapler.", prediction_seed(110001, step)))
            self.assertTrue(backend.calls[-1][0]["state"].flags.writeable)
        client.reset("Press down on the stapler.", 110000)
        client.predict(observation())
        self.assertEqual(backend.calls[-1][2], prediction_seed(110000, 0))

    def test_wrong_contract_and_nonfinite_output_are_rejected(self):
        backend = Backend()
        connection = Connection(XWAMEpisodePolicy(backend, "xwam", lambda seed: None))
        connection.response["action_type"] = "qpos"
        with patch("policies.wam.client.connect", return_value=connection), self.assertRaisesRegex(ValueError, "contract"):
            XWAMClient("ws://fixture")
        client, backend = connected_client()
        client.reset("press", 7)
        backend.actions[:] = np.nan
        with self.assertRaisesRegex(RuntimeError, "finite"):
            client.predict(observation())
        self.assertFalse(client.ready)

    def test_invalid_images_and_zero_quaternion_fail_before_inference(self):
        obs = observation()
        obs["observation"]["head_camera"]["rgb"] = np.zeros((320, 240, 3), np.uint8)
        with self.assertRaisesRegex(ValueError, "240x320"):
            format_observation(obs)
        obs = observation()
        obs["endpose"]["left_endpose"][3:] = 0
        with self.assertRaisesRegex(ValueError, "quaternion"):
            format_observation(obs)


class FakeEnv:
    def __init__(self, success_at):
        self.success_at = success_at

    def setup_demo(self, **kwargs):
        self.take_action_cnt, self.step_lim = 0, 37
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
        return observation()

    def take_action(self, action, action_type):
        assert action_type == "ee"
        np.testing.assert_allclose(action, native_proprio(observation()), atol=1e-14)
        self.take_action_cnt += 1
        self.eval_success = self.take_action_cnt == self.success_at


class EvaluationTests(unittest.TestCase):
    def test_success_and_budget_stop_mid_chunk_with_correct_evidence(self):
        from policies.xwam.eval import run_episode
        for success_at, count in ((5, 5), (100, 37)):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as tmp:
                client, backend = connected_client()
                def writer(path, **kwargs):
                    path.touch()
                    return Mock()
                with patch("imageio.v2.get_writer", side_effect=writer):
                    result = run_episode(FakeEnv(success_at), {}, client,
                        argparse.Namespace(policy="xwam", task="click_bell", task_config="demo_clean"),
                        2000, "task-name", Path(tmp))
                self.assertEqual(result["action_calls"], count, result)
                self.assertEqual(result["status"], "success" if count == 5 else "failure")
                with np.load(Path(tmp) / 'click_bell_ep2000_actions.npz') as data:
                    self.assertEqual(data['model_actions'].shape, ((count+31)//32, 32, 14))
                    self.assertEqual(data['raw_actions'].shape, ((count+31)//32, 32, 16))
                    self.assertEqual(data['measured_poses'].shape, (count, 16))
                    np.testing.assert_allclose(data['executed_actions'], data['raw_actions'].reshape(-1, 16)[:count])
                diagnostic = json.loads((Path(tmp) / 'click_bell_ep2000_diagnostics.json').read_text())
                self.assertEqual(diagnostic['policy'], 'xwam')
                self.assertEqual(diagnostic['action_type'], 'ee')
                self.assertNotIn('rel+abs', diagnostic['action_log_semantics'])


if __name__ == "__main__":
    unittest.main()
