"""Seeded three-camera transport for absolute Agilex joint-action chunks."""

import time

import numpy as np
from websockets.sync.client import connect

from policies.lingbot_va.client import CAMERAS, packb, unpackb

PROTOCOL = "wam_robotwin_qpos_v1"
CONTRACTS = {"fastwam": (32, 24), "motus": (16, 16)}


def encode_proprio(observation):
    state = np.asarray(observation["joint_action"]["vector"], dtype=np.float32)
    if state.shape != (14,) or not np.isfinite(state).all():
        raise ValueError("Expected finite Agilex 14D joint/gripper state")
    return state.copy()


def format_observation(observation):
    images = {}
    for name in CAMERAS:
        rgb = np.asarray(observation["observation"][name]["rgb"])
        if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8 or min(rgb.shape[:2]) < 1:
            raise ValueError(f"{name} must be nonempty HWC uint8 RGB")
        images[name] = rgb.copy()
    return {"images": images, "state": encode_proprio(observation)}


def decode_actions(actions, length):
    values = np.asarray(actions, dtype=np.float32)
    if values.shape != (length, 14) or not np.isfinite(values).all():
        raise ValueError(f"Expected finite ({length}, 14) joint actions, got {values.shape}")
    # Preserve the upstream policy's qpos values; no VLAct-specific wrapping or clipping.
    return values.copy()


class WAMClient:
    def __init__(self, policy, server_url, timeout=600, *, contract=None):
        if (contract is None and policy not in CONTRACTS) or timeout <= 0:
            raise ValueError("Expected a supported WAM and positive timeout")
        self.policy, self.timeout = policy, timeout
        if contract is None:
            horizon, length = CONTRACTS[policy]
            contract = {"protocol": PROTOCOL, "action_type": "qpos", "action_dim": 14,
                        "action_horizon": horizon, "use_length": length}
        self.horizon, self.use_length = contract["action_horizon"], contract["use_length"]
        self.ready = False
        self.requests = []
        self.connection = connect(server_url, compression=None, max_size=64 * 1024**2,
                                  open_timeout=timeout, close_timeout=5, ping_interval=None)
        try:
            self.server_metadata = self._receive()
            expected = {"policy": policy, **contract}
            if any(self.server_metadata.get(key) != value for key, value in expected.items()):
                raise ValueError(f"Server does not implement the pinned {policy} action contract")
        except Exception:
            self.connection.close()
            raise

    def _receive(self):
        response = self.connection.recv(timeout=self.timeout)
        if isinstance(response, str):
            raise RuntimeError(f"WAM server error: {response}")
        result = unpackb(response)
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError(f"WAM server error: {result}")
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
            self.ready = False
            event["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            event["latency_seconds"] = time.monotonic() - started
            self.requests.append(event)

    def reset(self, instruction, seed):
        self.ready = False
        self.requests = []
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("A nonempty instruction is required")
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError("Seed must be a uint32 integer")
        self._rpc("reset", {"type": "reset", "seed": seed, "instruction": instruction})
        self.chunk = 0
        self.ready = True

    def predict(self, observation):
        if not self.ready:
            raise RuntimeError("Reset the episode before inference")
        payload = {"type": "infer", "chunk": self.chunk, "observation": format_observation(observation)}
        started = time.monotonic()
        response = self._rpc("predict", payload)
        try:
            if type(response.get("chunk")) is not int or response["chunk"] != self.chunk:
                raise ValueError("Server returned an incorrect chunk index")
            full = decode_actions(response["actions"], self.horizon)
        except Exception:
            self.ready = False
            raise
        self.chunk += 1
        actions = full[:self.use_length].copy()
        return actions, {"raw_actions": actions.copy(), "model_actions": full,
                         "latency_seconds": time.monotonic() - started}

    def close(self):
        self.ready = False
        self.connection.close()
