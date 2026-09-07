"""LingBot-VA's stateful RoboTwin protocol and initial-pose-relative EE codec.

Based on Robbyant/lingbot-va (Apache-2.0), revision
7c6ffa9bfc4b83582cafc860fab4c82cc7deeeeb, evaluation/robotwin.
Copyright 2024-2025 The Robbyant Team Authors.
"""

import time

import msgpack
import numpy as np
from scipy.spatial.transform import Rotation
from websockets.sync.client import connect

CAMERAS = ("head_camera", "left_camera", "right_camera")
IMAGE_KEYS = ("observation.images.cam_high", "observation.images.cam_left_wrist", "observation.images.cam_right_wrist")


def pack_array(value):
    if isinstance(value, (np.ndarray, np.generic)) and value.dtype.kind in "VOc":
        raise ValueError(f"Unsupported dtype: {value.dtype}")
    if isinstance(value, np.ndarray):
        return {b"__ndarray__": True, b"data": value.tobytes(), b"dtype": value.dtype.str, b"shape": value.shape}
    if isinstance(value, np.generic):
        return {b"__npgeneric__": True, b"data": value.item(), b"dtype": value.dtype.str}
    raise TypeError(f"Unsupported message value: {type(value)}")


def unpack_array(value):
    if b"__ndarray__" in value:
        dtype = np.dtype(value[b"dtype"])
        if dtype.kind in "VOc":
            raise ValueError(f"Unsupported dtype: {dtype}")
        return np.ndarray(buffer=value[b"data"], dtype=dtype, shape=value[b"shape"])
    if b"__npgeneric__" in value:
        return np.dtype(value[b"dtype"]).type(value[b"data"])
    return value


def packb(value):
    return msgpack.packb(value, default=pack_array)


def unpackb(value):
    return msgpack.unpackb(value, object_hook=unpack_array)


def encode_proprio(observation):
    endpose = observation["endpose"]
    result = np.concatenate([np.r_[endpose[f"{arm}_endpose"], endpose[f"{arm}_gripper"]]
                             for arm in ("left", "right")]).astype(np.float64)
    if result.shape != (16,) or not np.isfinite(result).all():
        raise ValueError("Expected finite dual-arm 16D endpose")
    return result


def format_observation(observation, instruction):
    result = {"task": instruction, "observation.state": np.asarray(observation["joint_action"]["vector"])}
    if result["observation.state"].shape != (14,) or not np.isfinite(result["observation.state"]).all():
        raise ValueError("Expected the Agilex 14D joint/gripper observation")
    for camera, key in zip(CAMERAS, IMAGE_KEYS):
        image = np.asarray(observation["observation"][camera]["rgb"])
        if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
            raise ValueError(f"{camera} must be an HWC uint8 image")
        result[key] = image.copy()
    return result


def decode_actions(relative, initial_pose):
    """Match upstream add_init_pose, including its numerical quaternion convention.

    Both input quaternion arrays are fed directly to SciPy's default xyzw API,
    and the result is passed numerically to RoboTwin as wxyz. Do not swap only
    one side of this checkpoint-specific convention.
    """
    relative = np.asarray(relative, dtype=np.float64)
    initial_pose = np.asarray(initial_pose, dtype=np.float64)
    if relative.ndim != 2 or relative.shape[1] != 16 or not len(relative) or not np.isfinite(relative).all():
        raise ValueError("Expected nonempty finite (N, 16) relative actions")
    if initial_pose.shape != (16,) or not np.isfinite(initial_pose).all():
        raise ValueError("Expected a finite initial pose with 16 channels")
    absolute = relative.copy()
    for start in (0, 8):
        absolute[:, start:start + 3] += initial_pose[start:start + 3]
        absolute[:, start + 3:start + 7] = (
            Rotation.from_quat(initial_pose[start + 3:start + 7]) *
            Rotation.from_quat(relative[:, start + 3:start + 7])).as_quat()
    return absolute


class LingBotClient:
    def __init__(self, server_url="ws://127.0.0.1:8011", timeout=600):
        if timeout <= 0:
            raise ValueError("Request timeout must be positive")
        self.timeout = timeout
        self.connection = connect(server_url, compression=None, max_size=64 * 1024**2,
                                  open_timeout=timeout, close_timeout=5, ping_interval=None)
        self.requests = []
        try:
            self.server_metadata = self._receive()
        except Exception:
            self.connection.close()
            raise
        self.prompt = None

    def _receive(self):
        response = self.connection.recv(timeout=self.timeout)
        if isinstance(response, str):
            raise RuntimeError(f"LingBot-VA server error: {response}")
        result = unpackb(response)
        if not isinstance(result, dict):
            raise ValueError("Expected a mapping from the server")
        return result

    def _rpc(self, kind, payload):
        started = time.monotonic()
        event = {"kind": kind}
        try:
            self.connection.send(packb(payload))
            result = self._receive()
            event["server_timing"] = result.get("server_timing")
            return result
        except Exception as exc:
            event["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            event["latency_seconds"] = time.monotonic() - started
            self.requests.append(event)

    def reset(self, instruction, seed):
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("A nonempty instruction is required")
        self.prompt = None
        self.first = True
        self.pending = None
        self.initial_pose = None
        self.requests = []
        self._rpc("reset", {"reset": True, "prompt": instruction, "seed": int(seed), "save_visualization": False})
        self.prompt = instruction

    def predict(self, observation):
        if self.prompt is None:
            raise RuntimeError("Reset the episode before inference")
        started = time.monotonic()
        if self.pending is not None:
            if self.executed != self.expected:
                raise RuntimeError("Cannot update KV cache from a partially executed chunk")
            self._rpc("cache", {"obs": self.keyframes, "compute_kv_cache": True, "imagine": False,
                                "save_visualization": False, "state": self.pending})
            self.pending = None
        if self.first:
            self.initial_pose = encode_proprio(observation)
            self.initial_observation = format_observation(observation, self.prompt)
        response = self._rpc("predict", {"obs": self.initial_observation, "prompt": self.prompt,
                                         "save_visualization": False, "video_guidance_scale": 5.,
                                         "action_guidance_scale": 1.})
        raw = np.asarray(response.get("action"))
        # Pinned RoboTwin config: 16 output channels, 2 latent frames, 16 actions/frame.
        if raw.shape != (16, 2, 16) or not np.isfinite(raw).all():
            raise ValueError(f"Expected finite (16, 2, 16) action tensor, got {raw.shape}")
        skipped = 1 if self.first else 0
        relative = raw[:, skipped:, :].transpose(1, 2, 0).reshape(-1, 16)
        actions = decode_actions(relative, self.initial_pose)
        self.pending = raw.copy()
        self.executed, self.expected = 0, len(actions)
        self.keyframes = []
        self.first = False
        return actions, {"raw_actions": raw.copy(), "skipped_frames": skipped,
                         "latency_seconds": time.monotonic() - started}

    def observe_execution(self, observation):
        if self.pending is None or self.executed >= self.expected:
            raise RuntimeError("No pending action to observe")
        self.executed += 1
        # Upstream collects four real observations for each generated latent frame.
        if self.executed % 4 == 0:
            self.keyframes.append(format_observation(observation, self.prompt))

    def close(self):
        self.connection.close()
