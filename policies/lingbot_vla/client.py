"""LingBot-VLA WebSocket client: three RGB views and absolute Agilex joint chunks."""

import time

import numpy as np
from websockets.sync.client import connect

# Both official LingBot repositories use the same OpenPI NumPy wire envelope.
from policies.lingbot_va.client import CAMERAS as CAMERAS
from policies.lingbot_va.client import format_observation, packb, unpackb

PROTOCOL = "lingbot_vla_robotwin_v1"


def encode_proprio(observation):
    state = np.asarray(observation["joint_action"]["vector"], dtype=np.float32)
    if state.shape != (14,) or not np.isfinite(state).all():
        raise ValueError("Expected finite Agilex 14D joint/gripper state")
    return state.copy()


def decode_actions(actions, use_length=50):
    """Official robotwin.yaml uses absolute joints and continuous gripper positions."""
    values = np.asarray(actions, dtype=np.float32)
    if values.shape != (use_length, 14) or not np.isfinite(values).all():
        raise ValueError(f"Expected finite ({use_length}, 14) joint actions, got {values.shape}")
    return values.copy()


class LingBotVLAClient:
    def __init__(self, server_url="ws://127.0.0.1:8012", timeout=600):
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
                raise ValueError("Expected the LingBot-VLA RoboTwin server protocol")
            self.use_length = self.server_metadata.get("use_length")
            if type(self.use_length) is not int or not 1 <= self.use_length <= 50:
                raise ValueError("Server use_length must be an integer in [1, 50]")
            if self.server_metadata.get("action_type") != "qpos":
                raise ValueError("Server must return absolute qpos actions")
        except Exception:
            self.connection.close()
            raise

    def _receive(self):
        response = self.connection.recv(timeout=self.timeout)
        if isinstance(response, str):
            raise RuntimeError(f"LingBot-VLA server error: {response}")
        result = unpackb(response)
        if not isinstance(result, dict):
            raise ValueError("Expected a mapping from the server")
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
        self._rpc("reset", {"reset": True, "robo_name": "robotwin", "seed": seed})
        self.prompt = instruction

    def predict(self, observation):
        if self.prompt is None:
            raise RuntimeError("Reset the episode before inference")
        payload = format_observation(observation, self.prompt)
        payload["observation.state"] = encode_proprio(observation)
        started = time.monotonic()
        response = self._rpc("predict", payload)
        actions = decode_actions(response.get("action"), self.use_length)
        return actions, {"raw_actions": actions.copy(), "proprio": payload["observation.state"].copy(),
                         "latency_seconds": time.monotonic() - started}

    def close(self):
        self.connection.close()
