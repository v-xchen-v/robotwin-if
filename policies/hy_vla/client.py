"""Hy-VLA per-step WebSocket client; fresh RGB history and native wxyz EE state."""
import time

import numpy as np
from websockets.sync.client import connect

from policies.lingbot_va.client import CAMERAS as CAMERAS
from policies.lingbot_va.client import packb, unpackb

PROTOCOL = "hy_vla_robotwin_v1"


def encode_proprio(observation):
    endpose = observation["endpose"]
    state = np.concatenate([np.r_[endpose[f"{arm}_endpose"], endpose[f"{arm}_gripper"]]
                            for arm in ("left", "right")]).astype(np.float32)
    if state.shape != (16,) or not np.isfinite(state).all():
        raise ValueError("Expected finite dual-arm 16D EE/gripper state")
    if any(np.linalg.norm(state[start:start + 4]) < 1e-8 for start in (3, 11)):
        raise ValueError("EE quaternions must be nonzero")
    return state


def format_observation(observation):
    images = {}
    for name in CAMERAS:
        rgb = np.asarray(observation["observation"][name]["rgb"])
        if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8 or min(rgb.shape[:2]) < 1:
            raise ValueError(f"{name} must be nonempty HWC uint8 RGB")
        images[name] = rgb.copy()
    return {"images": images, "state": encode_proprio(observation)}


def validate_array(value, shape, name):
    array = np.asarray(value)
    if array.shape != shape or array.dtype.kind not in "fi" or not np.isfinite(array).all():
        raise ValueError(f"Expected finite {name} with shape {shape}, got {array.shape}")
    return array.copy()


class HyVLAClient:
    def __init__(self, server_url="ws://127.0.0.1:8015", timeout=600):
        if timeout <= 0:
            raise ValueError("Request timeout must be positive")
        self.timeout, self.prompt = timeout, None
        self.requests = []
        self.connection = connect(server_url, compression=None, max_size=64 * 1024**2,
                                  open_timeout=timeout, close_timeout=5, ping_interval=None)
        try:
            self.server_metadata = self._receive()
            expected = {"protocol": PROTOCOL, "action_type": "ee", "action_dim": 16,
                        "model_shape": [40, 20], "decoded_shape": [20, 16],
                        "execute_horizon": 7, "history_size": 6, "history_interval": 5,
                        "blend_mode": "rel_abs"}
            if any(self.server_metadata.get(k) != v for k, v in expected.items()):
                raise ValueError("Expected the Hy-VLA RoboTwin rel+abs/MEM contract")
        except Exception:
            self.connection.close()
            raise

    def _receive(self):
        response = self.connection.recv(timeout=self.timeout)
        if isinstance(response, str):
            raise RuntimeError(f"Hy-VLA server error: {response}")
        result = unpackb(response)
        if not isinstance(result, dict) or result.get("error"):
            raise RuntimeError(f"Hy-VLA response error: {result}")
        return result

    def _rpc(self, kind, payload):
        started = time.monotonic()
        event = {"kind": kind}
        try:
            self.connection.send(packb(payload))
            result = self._receive()
            event["server_timing"] = result.get("server_timing")
            event["episode_step"] = result.get("episode_step")
            return result
        except Exception as exc:
            self.prompt = None
            event["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            event["latency_seconds"] = time.monotonic() - started
            self.requests.append(event)

    def reset(self, instruction, seed):
        self.prompt, self.requests = None, []
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("A nonempty instruction is required")
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError("Seed must be a uint32 integer")
        response = self._rpc("reset", {"type": "reset", "instruction": instruction, "seed": seed})
        if response.get("ok") is not True:
            raise RuntimeError("Server reset failed")
        self.prompt, self.step = instruction, 0

    def predict(self, observation):
        if self.prompt is None:
            raise RuntimeError("Reset the episode before inference")
        started = time.monotonic()
        response = self._rpc("step", {"type": "step", "step": self.step,
                                      "observation": format_observation(observation)})
        try:
            if response.get("episode_step") != self.step or type(response.get("new_chunk")) is not bool:
                raise ValueError("Server step/refresh response is invalid")
            if response["new_chunk"] != (self.step % 7 == 0):
                raise ValueError("Server action-cache cadence differs from seven steps")
            action = validate_array(response.get("action"), (16,), "EE action")
            prediction = {"latency_seconds": time.monotonic() - started,
                          "new_chunk": response["new_chunk"], "proprio": encode_proprio(observation)}
            if response["new_chunk"]:
                prediction["model_actions"] = validate_array(response.get("model_actions"), (40, 20), "model output")
                prediction["raw_actions"] = validate_array(response.get("decoded_actions"), (20, 16), "decoded output")
            self.step += 1
            return action, prediction
        except Exception:
            self.prompt = None
            raise

    def close(self):
        self.connection.close()
