"""X-WAM RoboTwin EE codec, adapted from the Apache-2.0 official deployment.

Source: sharinka0715/X-WAM@72cfb86b33fc5060963ef63412f16439fcfa472f,
evaluation/X-WAM/deploy_policy.py. Delta rotations are left-multiplied and all
deltas (including grippers) accumulate relative to the preceding predicted pose.
"""

import hashlib
import time

import numpy as np
from scipy.spatial.transform import Rotation

from policies.lingbot_va.client import CAMERAS, encode_proprio as native_proprio
from policies.wam.client import WAMClient

CONTRACT = {"protocol": "wam_robotwin_delta_ee_v1", "action_type": "delta_ee", "action_dim": 14,
            "state_dim": 16, "action_horizon": 32, "use_length": 32}
BASE_COORD_XFORM = np.array([[0., 1., 0.], [-1., 0., 0.], [0., 0., 1.]])
EEF_AXES_XFORM = np.array([[0., 0., 1.], [0., -1., 0.], [1., 0., 0.]])


def prediction_seed(episode_seed, step_id):
    # Keep upstream's hash; use the manifest seed as the stable rollout identity.
    return int(hashlib.md5(f"0_{episode_seed}_{step_id}".encode()).hexdigest(), 16) % 2**32


def encode_proprio(observation):
    state = native_proprio(observation)
    encoded = state.copy()
    for start in (0, 8):
        quaternion = state[start + 3:start + 7]
        if np.linalg.norm(quaternion) < 1e-8:
            raise ValueError("Expected nonzero EE quaternion")
        matrix = Rotation.from_quat(quaternion[[1, 2, 3, 0]]).as_matrix()
        encoded[start:start + 3] = state[start:start + 3] @ BASE_COORD_XFORM.T
        encoded[start + 3:start + 7] = Rotation.from_matrix(
            BASE_COORD_XFORM @ matrix @ EEF_AXES_XFORM).as_quat(canonical=True)[[3, 0, 1, 2]]
    return encoded


def validate_wire_observation(obs):
    if not isinstance(obs, dict) or not isinstance(obs.get("images"), dict) or set(obs["images"]) != set(CAMERAS):
        raise ValueError("Expected three RGB cameras and transformed 16D EE state")
    images = {}
    for name in CAMERAS:
        rgb = np.asarray(obs["images"][name])
        if rgb.shape != (240, 320, 3) or rgb.dtype != np.uint8:
            raise ValueError(f"{name} must be 240x320 HWC uint8 RGB")
        images[name] = rgb.copy()
    state = np.asarray(obs.get("state"), dtype=np.float64)
    if state.shape != (16,) or not np.isfinite(state).all():
        raise ValueError("Expected finite transformed 16D EE state")
    for start in (3, 11):
        if not np.isclose(np.linalg.norm(state[start:start + 4]), 1., atol=1e-5):
            raise ValueError("Expected unit EE quaternion")
    return {"images": images, "state": state.copy()}


def format_observation(observation):
    return validate_wire_observation({
        "images": {name: observation["observation"][name]["rgb"] for name in CAMERAS},
        "state": encode_proprio(observation)})


def validate_deltas(relative):
    relative = np.asarray(relative, dtype=np.float64)
    if relative.shape != (32, 14) or not np.isfinite(relative).all():
        raise ValueError("Expected finite (32, 14) X-WAM delta actions")
    return relative.copy()


def decode_actions(relative, initial_state):
    relative = validate_deltas(relative)
    state = np.asarray(initial_state, dtype=np.float64)
    if state.shape != (16,) or not np.isfinite(state).all():
        raise ValueError("Expected finite transformed 16D initial EE state")
    absolute = np.empty((len(relative), 16), dtype=np.float64)
    for source, target in ((0, 0), (7, 8)):
        pos = state[target:target + 3].copy()
        quat = state[target + 3:target + 7]
        rot = Rotation.from_quat(quat[[1, 2, 3, 0]])
        gripper = state[target + 7]
        for i, action in enumerate(relative[:, source:source + 7]):
            pos += action[:3]
            rot = Rotation.from_rotvec(action[3:6]) * rot
            gripper += action[6]
            absolute[i, target:target + 3] = pos @ BASE_COORD_XFORM
            matrix = BASE_COORD_XFORM.T @ rot.as_matrix() @ EEF_AXES_XFORM.T
            absolute[i, target + 3:target + 7] = Rotation.from_matrix(matrix).as_quat(canonical=True)[[3, 0, 1, 2]]
            absolute[i, target + 7] = gripper
    if not np.isfinite(absolute).all():
        raise ValueError("Nonfinite decoded EE actions")
    return absolute


class XWAMClient(WAMClient):
    def __init__(self, server_url="ws://127.0.0.1:8018", timeout=600):
        super().__init__("xwam", server_url, timeout, contract=CONTRACT)

    def predict(self, observation):
        if not self.ready:
            raise RuntimeError("Reset the episode before inference")
        obs = format_observation(observation)
        started = time.monotonic()
        response = self._rpc("predict", {"type": "infer", "chunk": self.chunk, "observation": obs})
        try:
            if type(response.get("chunk")) is not int or response["chunk"] != self.chunk:
                raise ValueError("Server returned an incorrect chunk index")
            deltas = validate_deltas(response["actions"])
            actions = decode_actions(deltas, obs["state"])
        except Exception:
            self.ready = False
            raise
        self.chunk += 1
        return actions, {"raw_actions": actions.copy(), "model_actions": deltas,
                         "latency_seconds": time.monotonic() - started}
