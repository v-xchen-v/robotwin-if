"""Run in the dedicated DM05 environment with the pinned OpenDM checkout."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "third_party/opendm"))
from policies.dm05.serve import build_runtime, create_app  # noqa: E402
from policies.dm05.client import CAMERAS, format_observation, ROBOT_TYPE  # noqa: E402


def observation():
    return {"observation": {name: {"rgb": np.full((12, 20, 3), i * 40, dtype=np.uint8)}
                            for i, name in enumerate(CAMERAS)},
            "joint_action": {"vector": np.arange(14, dtype=np.float32)}}


class ServiceTests(unittest.TestCase):
    def test_invalid_inputs_never_reach_model(self):
        runtime = Mock()
        app = create_app(runtime, {}).test_client()
        good = {"observation": format_observation(observation(), "Bell"), "sampling": {"seed": 0, "num_steps": 10}}
        cases = [None, {}, {"observation": {}}]
        for key, value in [("state", [0]*13), ("state", [float("nan")]*14), ("prompt", ""),
                           ("images", {"1": "bad"}), ("robot_type", "Other robot")]:
            bad = deepcopy(good)
            bad["observation"][key] = value
            cases.append(bad)
        for seed in [True, -1, 2**32, 1.5]:
            bad = deepcopy(good)
            bad["sampling"]["seed"] = seed
            cases.append(bad)
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertEqual(app.post("/v1/infer", json=payload).status_code, 400)
        runtime._predict.assert_not_called()

    def test_stateless_http_sampling_and_error_recovery(self):
        runtime = Mock()
        runtime.model._suffix_graph_profiles = {}
        runtime.model._suffix_graph_disabled_profiles = {}
        runtime.last_model_latency_sec = 0.1
        runtime._predict.side_effect = [RuntimeError("Inference failed"), np.zeros((50, 14))]
        payload = {"observation": format_observation(observation(), "Bell"), "sampling": {"seed": 2000, "num_steps": 10}}
        with tempfile.TemporaryDirectory() as tmp:
            logfile = Path(tmp) / "requests.jsonl"
            app = create_app(runtime, {"model": "dm05"}, logfile).test_client()
            self.assertEqual(app.get("/healthz").status_code, 200)
            self.assertEqual(app.get("/metadata").json, {"model": "dm05"})
            self.assertEqual(app.post("/v1/reset").json["status"], "ok")
            self.assertEqual(app.post("/v1/infer", json=payload).status_code, 500)
            response = app.post("/v1/infer", json=payload)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(np.asarray(response.json["actions"]).shape, (50, 14))
            runtime._apply_v1_sampling.assert_called_with({"seed": 2000, "num_steps": 10})
            self.assertEqual([json.loads(s)["status"] for s in logfile.read_text().splitlines()], ["error", "ok"])

    def test_official_pipeline_absolute_actions_and_rgb_parity(self):
        # A synthetic asymmetric stats profile exposes arm swaps and accidental
        # addition of current state to already absolute model predictions.
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = Path(tmp)
            low, high = np.arange(14, dtype=np.float32), np.arange(14, dtype=np.float32) + 2
            stats = {"mean": low.tolist(), "std": [1]*14, "q01": low.tolist(), "q99": high.tolist()}
            (checkpoint / "norm_stats.json").write_text(json.dumps({"norm_stats": {"state": stats, "action": stats}}))
            with patch("opendm.exp.dm05_exp.AutoProcessor.from_pretrained"), patch("torch.cuda.is_available", return_value=False):
                runtime = build_runtime(Mock(), checkpoint)
            obs = observation()
            body = {"observation": format_observation(obs, "Use the right arm")}
            data = runtime._prepare_input(body)
            self.assertEqual(data["meta_data"]["robot_type"], ROBOT_TYPE)
            self.assertEqual(data["prompt"], "Use the right arm")
            for i, name in enumerate(("head_camera", "left_camera", "right_camera")):
                np.testing.assert_array_equal(np.asarray(data["images"][i]), obs["observation"][name]["rgb"])
            normalized = np.zeros((50, 14), dtype=np.float32)
            result = runtime.output_transform({"action": normalized, "state": np.full(14, 100.), "meta_data": data["meta_data"]})
            np.testing.assert_allclose(result["action"], np.broadcast_to(low + 1, (50, 14)), atol=1e-6)
            self.assertFalse(runtime.use_absolute_action)
            self.assertFalse(runtime.is_history)


if __name__ == "__main__":
    unittest.main()
