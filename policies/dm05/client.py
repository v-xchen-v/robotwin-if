"""DM05 HTTP client: three RGB views, measured 14D state, absolute joint targets."""
import base64
from io import BytesIO
import time

import numpy as np
from PIL import Image
import requests

CAMERAS = ("head_camera", "left_camera", "right_camera")
PROTOCOL = "dm05_robotwin_v1"
ROBOT_TYPE = "Aloha RoboTwin2"


def encode_proprio(observation):
    state = np.asarray(observation["joint_action"]["vector"], dtype=np.float32)
    if state.shape != (14,) or not np.isfinite(state).all():
        raise ValueError("Expected finite Agilex 14D joint/gripper state")
    return state.copy()


def decode_actions(actions, use_length=50):
    values = np.asarray(actions, dtype=np.float32)
    if values.shape != (use_length, 14) or not np.isfinite(values).all():
        raise ValueError(f"Expected finite ({use_length}, 14) absolute joint actions, got {values.shape}")
    return values.copy()


def format_observation(observation, instruction):
    images = {}
    for slot, name in enumerate(CAMERAS, 1):
        rgb = np.asarray(observation["observation"][name]["rgb"])
        if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 1:
            raise ValueError(f"{name} must be nonempty HWC uint8 RGB")
        buffer = BytesIO()
        Image.fromarray(rgb).save(buffer, format="PNG")
        images[str(slot)] = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {"prompt": instruction, "state": encode_proprio(observation).tolist(),
            "images": images, "robot_type": ROBOT_TYPE}


class DM05Client:
    def __init__(self, server_url="http://127.0.0.1:8014", timeout=600):
        if timeout <= 0:
            raise ValueError("Request timeout must be positive")
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.prompt = None
        self.requests = []
        self.session = requests.Session()
        try:
            self.server_metadata = self._rpc("metadata", "GET", "/metadata")
            expected = {"protocol": PROTOCOL, "use_length": 50, "action_type": "qpos",
                        "action_mode": "absolute", "robot_type": ROBOT_TYPE, "diffusion_steps": 10}
            if any(self.server_metadata.get(k) != v for k, v in expected.items()):
                raise ValueError("Expected the DM05 RoboTwin2 absolute-joint server contract")
            self.use_length = 50
        except Exception:
            self.session.close()
            raise

    def _rpc(self, kind, method, path, payload=None):
        started = time.monotonic()
        event = {"kind": kind}
        if payload is not None and "sampling" in payload:
            event["sampling"] = payload["sampling"].copy()
        try:
            response = self.session.request(method, self.server_url + path, json=payload, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or "error" in result:
                raise ValueError(f"Invalid DM05 response: {result}")
            event["server_timing"] = result.get("metadata")
            return result
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
        result = self._rpc("reset", "POST", "/v1/reset", {})
        if result.get("status") != "ok":
            raise ValueError("Server reset did not succeed")
        self.seed, self.chunk_index, self.prompt = seed, 0, instruction

    def predict(self, observation):
        if self.prompt is None:
            raise RuntimeError("Reset the episode before inference")
        started = time.monotonic()
        payload = {"observation": format_observation(observation, self.prompt),
                   "sampling": {"num_steps": 10, "seed": (self.seed + self.chunk_index) % 2**32}}
        response = self._rpc("predict", "POST", "/v1/infer", payload)
        actions = decode_actions(response.get("actions"))
        self.chunk_index += 1
        return actions, {"raw_actions": actions.copy(), "proprio": encode_proprio(observation),
                         "latency_seconds": time.monotonic() - started}

    def close(self):
        self.session.close()
