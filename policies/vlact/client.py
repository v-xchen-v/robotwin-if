"""VLAct WebSocket client: three RGB views and absolute Agilex joint chunks."""

import time

import numpy as np
from websockets.sync.client import connect

# VLAct uses the same OpenPI NumPy wire envelope.
from policies.lingbot_va.client import CAMERAS as CAMERAS
from policies.lingbot_va.client import packb, unpackb

PROTOCOL = "vlact_robotwin_v1"


def encode_proprio(observation):
    state = np.asarray(observation["joint_action"]["vector"], dtype=np.float32)
    if state.shape != (14,) or not np.isfinite(state).all():
        raise ValueError("Expected finite Agilex 14D joint/gripper state")
    return state.copy()


def decode_actions(actions, use_length=32):
    """Validate server-decoded absolute qpos; gripper clipping happens in the server."""
    values = np.asarray(actions, dtype=np.float32)
    if values.shape != (use_length, 14) or not np.isfinite(values).all():
        raise ValueError(f"Expected finite ({use_length}, 14) joint actions, got {values.shape}")
    return values.copy()


class VLActClient:
    def __init__(self, server_url="ws://127.0.0.1:8013", timeout=600):
        if timeout <= 0:
            raise ValueError("Request timeout must be positive")
        self.timeout = timeout
        self.prompt = None
        self.requests = []
        self.connection = connect(server_url, compression=None, max_size=64 * 1024**2,
                                  open_timeout=timeout, close_timeout=5, ping_interval=None)
        try:
            self.server_metadata = self._receive()
            if self.server_metadata.get("protocol") != PROTOCOL:
                raise ValueError("Expected the VLAct RoboTwin server protocol")
            self.use_length = self.server_metadata.get("use_length")
            if type(self.use_length) is not int or not 1 <= self.use_length <= 32:
                raise ValueError("Server use_length must be an integer in [1, 32]")
            if self.use_length != 32 or self.server_metadata.get("joint_action_mode") != "wrap":
                raise ValueError("Expected the wrap32 checkpoint action contract")
            if self.server_metadata.get("action_type") != "qpos":
                raise ValueError("Server must return absolute qpos actions")
        except Exception:
            self.connection.close()
            raise

    def _receive(self):
        response = self.connection.recv(timeout=self.timeout)
        if isinstance(response, str):
            raise RuntimeError(f"VLAct server error: {response}")
        result = unpackb(response)
        if not isinstance(result, dict):
            raise ValueError("Expected a mapping from the server")
        if result.get("ok") is not True:
            raise RuntimeError(f"VLAct server error: {result.get('error', result)}")
        return result

    def _rpc(self, kind, payload):
        started = time.monotonic()
        event = {"kind": kind}
        try:
            self.connection.send(packb(payload))
            response = self._receive()
            event["server_timing"] = response.get("server_timing")
            return response
        except Exception as exc:
            event["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            event["latency_seconds"] = time.monotonic() - started
            self.requests.append(event)

    def reset(self, instruction, seed):
        self.prompt = None
        self.requests = []
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("A nonempty instruction is required")
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError("Seed must be a uint32 integer")
        self._rpc("reset", {"type": "reset", "seed": seed, "instruction": instruction})
        self.prompt = instruction

    def predict(self, observation):
        if self.prompt is None:
            raise RuntimeError("Reset the episode before inference")
        images = []
        for name in CAMERAS:
            rgb = np.asarray(observation["observation"][name]["rgb"])
            if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8 or min(rgb.shape[:2]) < 1:
                raise ValueError(f"{name} must be nonempty HWC uint8 RGB")
            images.append(rgb.copy())
        # QwenOFT consumes images + language only. Measured state is evidence.
        proprio = encode_proprio(observation)
        payload = {"type": "infer", "examples": [{"image": images, "lang": self.prompt}]}
        started = time.monotonic()
        response = self._rpc("predict", payload)
        actions = decode_actions(response["data"]["action"], self.use_length)
        model_actions = decode_actions(response["data"]["model_actions"], self.use_length)
        return actions, {"raw_actions": actions.copy(), "model_actions": model_actions,
                         "proprio": proprio, "latency_seconds": time.monotonic() - started}

    def close(self):
        self.connection.close()
