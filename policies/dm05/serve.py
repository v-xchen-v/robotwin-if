#!/usr/bin/env python3
"""Serve the pinned DM05 RoboTwin2 model using official OpenDM transforms."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from policies.dm05.client import PROTOCOL, ROBOT_TYPE, decode_actions  # noqa: E402
from policies.dm05.download_checkpoint import (  # noqa: E402
    CHECKPOINT, REVISION, SOURCE_REVISION, WEIGHTS_SHA256, sha256,
)


def validate_request(body):
    import numpy as np
    if not isinstance(body, dict) or not isinstance(body.get("observation"), dict):
        raise ValueError("observation must be a JSON object")
    obs = body["observation"]
    if not isinstance(obs.get("prompt"), str) or not obs["prompt"].strip():
        raise ValueError("A nonempty prompt is required")
    if obs.get("robot_type", ROBOT_TYPE) != ROBOT_TYPE:
        raise ValueError("Only Aloha RoboTwin2 is supported")
    if not isinstance(obs.get("images"), dict) or set(obs["images"]) != {"1", "2", "3"}:
        raise ValueError("Expected head/left-wrist/right-wrist image slots 1, 2, 3")
    if "history_images" in obs:
        raise ValueError("This checkpoint uses current observations without history")
    state = np.asarray(obs.get("state"), dtype=np.float32)
    if state.shape != (14,) or not np.isfinite(state).all():
        raise ValueError("Expected finite 14D state")
    sampling = body.get("sampling")
    if not isinstance(sampling, dict):
        raise ValueError("sampling with a uint32 seed is required")
    if type(sampling.get("seed")) is not int or not 0 <= sampling["seed"] < 2**32:
        raise ValueError("sampling.seed must be a uint32 integer")
    if type(sampling.get("num_steps")) is not int or sampling["num_steps"] != 10:
        raise ValueError("sampling.num_steps must be 10")


def create_app(runtime, metadata, request_log=None):
    from flask import Flask, jsonify, request
    from werkzeug.exceptions import BadRequest
    import torch

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024**2

    @app.get("/healthz")
    def health():
        return jsonify({"status": "ok", "protocol": PROTOCOL})

    @app.get("/metadata")
    def model_metadata():
        return jsonify(metadata)

    @app.post("/v1/reset")
    def reset():
        # No episode KV/history state: every infer request contains its prompt and seed.
        return jsonify({"status": "ok", "stateless": True})

    @app.post("/v1/infer")
    def infer():
        started = time.monotonic()
        event = {}
        try:
            body = request.get_json(force=True)
            validate_request(body)
            event["sampling"] = body["sampling"]
            event["prompt"] = body["observation"]["prompt"]
            event["state"] = body["observation"]["state"]
            random.seed(body["sampling"]["seed"])
            runtime._apply_v1_sampling(body["sampling"])
            data = runtime._prepare_input(body)
            with torch.inference_mode():
                actions = decode_actions(runtime._predict(data))
            model = runtime.model
            timing = {"latency_ms": round((time.monotonic() - started) * 1000, 3),
                      "model_latency_ms": round(runtime.last_model_latency_sec * 1000, 3),
                      "seed": body["sampling"]["seed"],
                      "suffix_graph_profiles": len(model._suffix_graph_profiles),
                      "suffix_graph_disabled_profiles": len(model._suffix_graph_disabled_profiles)}
            event.update(status="ok", metadata=timing)
            return jsonify({"actions": actions.tolist(), "metadata": timing})
        except (BadRequest, TypeError, ValueError) as exc:
            event.update(status="bad_request", error=str(exc))
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            app.logger.exception("DM05 inference failed")
            event.update(status="error", error=f"{type(exc).__name__}: {exc}")
            return jsonify({"error": event["error"]}), 500
        finally:
            if request_log is not None:
                event["elapsed_seconds"] = time.monotonic() - started
                with request_log.open("a") as stream:
                    stream.write(json.dumps(event, allow_nan=False) + "\n")

    return app


def build_runtime(model, checkpoint):
    from playground.dm05_robotwin2 import DM05InferenceConfig
    runtime = DM05InferenceConfig()
    runtime._initialize(model, str(checkpoint), str(checkpoint / "norm_stats.json"),
                        n_bins=256, model_max_length=1024, use_absolute_action=False,
                        add_state=True, is_history=False)
    return runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=REPO_ROOT / "third_party/opendm")
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8014)
    parser.add_argument("--gpu", default="0")
    args = parser.parse_args()
    source, checkpoint, output = args.source_dir.resolve(), args.checkpoint_dir.resolve(), args.output_dir.resolve()
    os.environ.update(CUDA_VISIBLE_DEVICES=args.gpu, LOCAL_RANK="0", PYTHONNOUSERSITE="1",
                      HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", NO_ALBUMENTATIONS_UPDATE="1")
    if "DM05_INFERENCE_SEED" in os.environ:
        raise ValueError("Unset DM05_INFERENCE_SEED: it overrides per-request sampling seeds")
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"], text=True)
    if revision != SOURCE_REVISION or dirty:
        raise ValueError("Expected clean pinned OpenDM source")
    identity = json.loads((checkpoint / "checkpoint.json").read_text())
    if identity.get("repo_id") != CHECKPOINT or identity.get("revision") != REVISION:
        raise ValueError("Download the pinned checkpoint with download_checkpoint.py")
    if sha256(checkpoint / "model.safetensors") != WEIGHTS_SHA256:
        raise ValueError("Checkpoint weights checksum mismatch")
    required = {"config.json", "norm_stats.json", "tokenizer.json", "tokenizer_config.json",
                "processor_config.json", "chat_template.jinja"}
    hashes = identity.get("files_sha256", {})
    if not required <= hashes.keys() or any(sha256(checkpoint / name) != hashes[name] for name in required):
        raise ValueError("Checkpoint config/processor/statistics checksum mismatch")
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(source))
    import torch
    import transformers
    from opendm.model.dm05.dm05_arch import DM05Config, DM05ForConditionalGeneration

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    config = DM05Config.from_pretrained(checkpoint, local_files_only=True)
    if config.chunk_size != 50 or config.action_dim != 32:
        raise ValueError("Expected the released DM05 50-step/32D padded action architecture")
    # Avoid loading the checkpoint's training FlashAttention/Flex backends before
    # selecting official default-inference eager LLM / SDPA vision and action.
    for part in (config, config.vlm_config, config.vlm_config.text_config,
                 config.vlm_config.vision_config, config.action_config):
        part._attn_implementation = "eager"
    model, loading = DM05ForConditionalGeneration.from_pretrained(
        checkpoint, config=config, dtype=torch.bfloat16, local_files_only=True, output_loading_info=True,
    )
    if any(loading.get(key) for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")):
        raise RuntimeError(f"Checkpoint did not load strictly: {loading}")
    loading = {key: sorted(value) if isinstance(value, set) else value for key, value in loading.items()}
    model.set_precision_policy("bf16_mixed")
    model.set_attention_implementation(llm_attn_implementation="eager", vision_attn_implementation="sdpa",
                                       action_attn_implementation="sdpa", bf16=True)
    model.enable_gradient_checkpointing(vlm_gradient_checkpointing=False, ae_gradient_checkpointing=False)
    runtime = build_runtime(model, checkpoint)
    metadata = {"protocol": PROTOCOL, "checkpoint": identity, "source_revision": revision,
                "created_at": datetime.now(timezone.utc).isoformat(), "use_length": 50,
                "action_type": "qpos", "action_mode": "absolute", "robot_type": ROBOT_TYPE,
                "state_action_order": "left joints 0:6, left gripper 6, right joints 7:13, right gripper 13",
                "cameras": ["head_camera", "left_camera", "right_camera"],
                "diffusion_steps": 10, "precision": "bf16_mixed", "liger_kernel": False,
                "attention": {"llm": "eager", "vision": "sdpa", "action": "sdpa"},
                "suffix_cuda_graphs": "official automatic capture/replay; counts recorded per request",
                "normalization": "official q01/q99; state clipped to bounds; absolute action denormalization only",
                "sampling": "stateless per-request uint32 seed; client uses (episode_seed + chunk_index) modulo 2**32",
                "torch": torch.__version__, "transformers": transformers.__version__,
                "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(),
                "loading_info": loading, "parameter_count": sum(p.numel() for p in model.parameters()),
                "source_sha256": {p.name: sha256(p) for p in Path(__file__).parent.glob("*.py")}}
    (output / "server.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata), flush=True)
    create_app(runtime, metadata, output / "requests.jsonl").run(
        host=args.host, port=args.port, threaded=False, use_reloader=False,
    )


if __name__ == "__main__":
    main()
