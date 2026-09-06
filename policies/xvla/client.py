"""X-VLA RoboTwin HTTP client and checkpoint-specific EE6D codec.

Based on 2toinf/X-VLA (Apache-2.0), revision
6bc2513f5f1cbec715cc668b414392a6cae5c671, evaluation/robotwin-2.0/client.py
and datasets/domain_handler/simulations.py. Copyright 2025 2toINF.
"""

import time

import json_numpy
import numpy as np
import requests
from scipy.spatial.transform import Rotation


CAMERAS = ("head_camera", "left_camera", "right_camera")


def encode_rotation(quaternion):
    """Preserve the released checkpoint's numeric quaternion convention.

    RoboTwin exposes wxyz, but BOTH the official training handler and client
    feed those four numbers directly to SciPy's default xyzw codec. Changing
    only inference to scalar_first=True changes the checkpoint's input space.
    Decode with the inverse codec, returning the original RoboTwin ordering.
    """
    q = np.asarray(quaternion, dtype=np.float64)
    if q.shape[-1:] != (4,) or not np.isfinite(q).all():
        raise ValueError("Expected finite quaternion(s) with last dimension 4")
    return Rotation.from_quat(q).as_matrix()[..., :, :2].reshape(q.shape[:-1] + (6,))


def decode_rotation(rotation):
    v = np.asarray(rotation, dtype=np.float64)
    if v.shape[-1:] != (6,) or not np.isfinite(v).all():
        raise ValueError("Expected finite rotation(s) with last dimension 6")
    a, b = v[..., 0::2], v[..., 1::2]
    norm_a = np.linalg.norm(a, axis=-1, keepdims=True)
    if np.any(norm_a < 1e-8):
        raise ValueError("Degenerate first rotation column")
    a = a / norm_a
    b = b - (a * b).sum(axis=-1, keepdims=True) * a
    norm_b = np.linalg.norm(b, axis=-1, keepdims=True)
    if np.any(norm_b < 1e-8):
        raise ValueError("Degenerate second rotation column")
    b = b / norm_b
    return Rotation.from_matrix(np.stack((a, b, np.cross(a, b)), axis=-1)).as_quat()


def encode_proprio(observation):
    parts = []
    for arm in ("left", "right"):
        pose = np.asarray(observation["endpose"][f"{arm}_endpose"], dtype=np.float64)
        grip = float(observation["endpose"][f"{arm}_gripper"])
        if pose.shape != (7,) or not np.isfinite(pose).all() or not np.isfinite(grip):
            raise ValueError(f"Invalid {arm} endpose/gripper observation")
        # Official client transform; the model masks the proprio gripper slots.
        parts.extend((pose[:3], encode_rotation(pose[3:]), [1 - 2 * grip]))
    return np.concatenate(parts).astype(np.float32)


def decode_actions(actions, gripper_threshold=0.7):
    actions = np.asarray(actions, dtype=np.float64)
    if actions.ndim != 2 or actions.shape[1] != 20 or not len(actions):
        raise ValueError(f"Expected a nonempty (N, 20) action chunk, got {actions.shape}")
    if not np.isfinite(actions).all():
        raise ValueError("Model returned non-finite actions")
    if not 0 <= gripper_threshold <= 1:
        raise ValueError("Gripper threshold must be between zero and one")
    if np.any((actions[:, [9, 19]] < 0) | (actions[:, [9, 19]] > 1)):
        raise ValueError("Expected post-sigmoid gripper probabilities in [0, 1]")
    arms = []
    for offset in (0, 10):
        arms.extend((
            actions[:, offset:offset + 3],
            decode_rotation(actions[:, offset + 3:offset + 9]),
            # Preserve reference execution: RoboTwin clips negative values to 0.
            1.0 - 2.0 * (actions[:, offset + 9:offset + 10] > gripper_threshold),
        ))
    return np.concatenate(arms, axis=1)


class XVLAClient:
    def __init__(self, server_url="http://127.0.0.1:8010", timeout=120, steps=10,
                 feedback="commanded", gripper_threshold=0.7):
        if timeout <= 0 or steps <= 0:
            raise ValueError("Timeout and denoising steps must be positive")
        if feedback not in ("commanded", "measured"):
            raise ValueError("Unknown feedback mode")
        self.url = server_url.rstrip("/") + "/act"
        self.timeout = timeout
        self.steps = steps
        self.feedback = feedback
        self.gripper_threshold = gripper_threshold
        self.session = requests.Session()
        self.reset()

    def reset(self):
        # The official /act endpoint is stateless; only client feedback persists.
        self.last_action = None

    def record_action(self, action):
        self.last_action = np.asarray(action, dtype=np.float64).copy()

    def predict(self, observation, instruction):
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("A nonempty language instruction is required")
        endpose = dict(observation["endpose"])
        if self.feedback == "commanded" and self.last_action is not None:
            endpose["left_endpose"] = self.last_action[:7]
            endpose["right_endpose"] = self.last_action[8:15]
        proprio = encode_proprio({"endpose": endpose})
        payload = {"domain_id": 6, "steps": self.steps,
                   "language_instruction": instruction, "proprio": json_numpy.dumps(proprio)}
        for index, name in enumerate(CAMERAS):
            rgb = np.asarray(observation["observation"][name]["rgb"])
            if rgb.ndim != 3 or rgb.shape[-1] != 3 or rgb.dtype != np.uint8:
                raise ValueError(f"{name} must be an HWC uint8 RGB image")
            payload[f"image{index}"] = json_numpy.dumps(rgb)
        started = time.monotonic()
        response = self.session.post(self.url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or "action" not in body:
            raise ValueError(f"Server response is missing action: {body!r}")
        raw = np.asarray(body["action"], dtype=np.float64)
        decoded = decode_actions(raw, self.gripper_threshold)
        return decoded, {"raw_actions": raw, "proprio": proprio,
                         "latency_seconds": time.monotonic() - started}

    def close(self):
        self.session.close()
