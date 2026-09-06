"""CogACT-compatible episode artifacts and lossless export of older X-VLA runs.

Run the offline converter with ``python -m policies.xvla.outputs --help``.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

import imageio.v2 as imageio
import numpy as np
from scipy.spatial.transform import Rotation

from if_benchmark.seed_contracts import IF_SEED_CONTRACTS
from policies.xvla.client import CAMERAS, decode_rotation


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def episode_path(directory, task, seed, suffix):
    return directory / f"{task}_ep{seed}{suffix}"


def camera_strip(images):
    """Head, left wrist, right wrist, matching the reference step0000 image."""
    return np.concatenate([images[name] for name in CAMERAS], axis=1)


def action_logs(raw, lengths):
    """One entry per predicted chunk, including its unexecuted tail."""
    logs = []
    offset = 0
    for length in lengths:
        chunk = raw[offset:offset + int(length)]
        entry = {}
        for arm, start in (("LEFT", 0), ("RIGHT", 10)):
            rotation = chunk[:, start + 3:start + 9]
            entry.update({
                f"ROBOT_{arm}_GRIPPER": chunk[:, start + 9:start + 10].tolist(),
                f"ROBOT_{arm}_ROT_6D": rotation.tolist(),
                f"ROBOT_{arm}_ROT_MAT": Rotation.from_quat(decode_rotation(rotation)).as_matrix().tolist(),
                f"ROBOT_{arm}_TRANS": chunk[:, start:start + 3].tolist(),
            })
        logs.append(entry)
        offset += int(length)
    if offset != len(raw):
        raise ValueError("Chunk lengths do not cover the raw action trace")
    return logs


def legacy_timings(trace):
    """Charge each saved request latency to its first action; never invent env time."""
    latencies = {}
    offset = 0
    for length, latency in zip(trace["chunk_lengths"], trace["request_latency_seconds"]):
        latencies[offset] = float(latency)
        offset += int(length)
    return [{"step": step, "inference_time_sec": latencies.get(step, 0.0),
             "env_step_time_sec": None, "total_time_sec": None}
            for step in range(len(trace["executed_actions"]))]


def write_episode_artifacts(directory, record, task_config, *, block=None, timings=None, legacy=False):
    """Write the reference files from the episode's detailed record and NPZ trace."""
    def path(suffix):
        return episode_path(directory, record["task"], record["seed"], suffix)

    with np.load(path("_actions.npz")) as trace:
        logs = action_logs(trace["raw_actions"], trace["chunk_lengths"])
        request_total = float(trace["request_latency_seconds"].sum())
        if timings is None:
            timings = legacy_timings(trace)
        executed = len(trace["executed_actions"])
    write_json(path("_action_logs.json"), logs)
    write_json(path("_timings.json"), timings)

    errors = {key: record[key] for key in ("error", "video_error", "close_error") if key in record}
    duration = record["elapsed_seconds"]

    def total(key):
        values = [row[key] for row in timings]
        return sum(values) if not legacy and all(v is not None for v in values) else None

    # These generic CogACT grasp diagnostics were not collected by this runner.
    # Null distinguishes unavailable evidence from a measured negative outcome.
    unavailable = ("target_key", "grasp_target_key", "grasp_target_correct",
                   "grasp_dist_threshold_m", "grasp_target_dist_m", "grasp_target_correct_within_th",
                   "grasp_events", "min_gripper", "lift_threshold_m", "max_lift_m", "lift_step",
                   "target_lift_step", "lifted_keys", "target_lifted")
    summary = {"task": record["task"], "config": task_config, "instruction": record["instruction"],
               "instruction_type": record["instruction_type"], "episode_id": record["seed"],
               "seed": record["seed"], "steps": record["action_calls"], "duration_sec": duration,
               "fps": record["action_calls"] / duration if duration > 0 else None,
               "success": record["success"], "execution_runtime_error": errors or None,
               "total_inference_time_sec": request_total if legacy else total("inference_time_sec"),
               "total_env_step_time_sec": total("env_step_time_sec"),
               "total_step_time_sec": total("total_time_sec"),
               **dict.fromkeys(unavailable), "signals": record.get("signals")}
    write_json(path("_summary.json"), summary)
    status = {"success": "policy_success", "failure": "policy_failure", "error": "execution_error"}
    write_json(path("_status.json"), {
        "task": record["task"], "seed": record["seed"], "mode": record["mode"], "block": block,
        "status": status[record["status"]], "detail": errors or None, "attempts": 1,
    })
    path("_instruction.txt").write_text(
        f"task: {record['task']}\nepisode_id: {record['seed']}\n"
        f"instruction_type: {record['instruction_type']}\ninstruction: {record['instruction'] or ''}\n")
    if path("_initial_observation.npz").exists():
        with np.load(path("_initial_observation.npz")) as obs:
            imageio.imwrite(path("_step0000.png"), camera_strip(obs))
    write_json(path("_diagnostics.json"), {
        "format": "cogact_episode_v1", "policy": "xvla", "converted_from_legacy": legacy,
        "duration_scope": "Whole episode including oracle qualification, policy setup and environment close",
        "timing_scope": ("Saved HTTP/decode latency charged to first action of each chunk; "
                         "environment and total step times were not recorded" if legacy else
                         "predict() time charged to first action of each chunk, zero for cached actions; "
                         "env time covers take_action(); total is their sum, excluding observation/video IO"),
        "unavailable_summary_fields": list(unavailable),
        "action_log_semantics": {
            "entries": "Full predicted chunks; executed_actions in _actions.npz is authoritative for execution",
            "gripper": "Raw X-VLA sigmoid probabilities, before thresholding/clipping",
            "rotation": "Interleaved rot6d and orthonormalized matrix in the checkpoint's numeric convention; "
                        "decoded execution quaternions use RoboTwin wxyz (see policy README)",
        },
        "predicted_chunks": len(logs), "executed_actions": executed,
        "block_semantics": "Zero-based block ordinal in this run; null for native tasks",
        "initial_image_views": list(CAMERAS),
        "video_views": ["head_camera"] if legacy else list(CAMERAS),
        "video_frames": "Initial observation followed by one frame per executed action",
    })


def convert_legacy(source, destination):
    """Copy an old task run to a new flat directory, retaining original provenance."""
    source, destination = source.resolve(), destination.resolve()
    metadata = json.loads((source / "run.json").read_text())
    task = metadata["arguments"]["task"]
    seeds = metadata["seeds"]
    results = [json.loads(p.read_text()) for p in sorted(source.glob("seed-*/result.json"))]
    if not results or any(r["task"] != task or r["seed"] not in seeds for r in results):
        raise ValueError("Legacy episode results do not match the run metadata")
    destination.mkdir(parents=True, exist_ok=False)
    for filename in ("run.json", "resolved_config.json", "console.log", "results.jsonl", "summary.json"):
        if (source / filename).exists():
            shutil.copy2(source / filename, destination / filename)
    console = (source / "console.log").read_text()
    markers = list(re.finditer(r"^Policy seed=(\d+),", console, re.MULTILINE))
    excerpts = {int(match[1]): console[match.start():markers[i + 1].start() if i + 1 < len(markers) else len(console)]
                for i, match in enumerate(markers)}
    for record in results:
        seed = record["seed"]
        old = source / f"seed-{seed}"

        def path(suffix):
            return episode_path(destination, task, seed, suffix)

        for file in old.iterdir():
            if file.name == "rollout.mp4":
                suffix = f"_{int(record['success'])}.mp4"
            else:
                suffix = "_" + file.name.replace("-", "_")
            shutil.copy2(file, path(suffix))
        path(".log").write_text(
            f"Offline export from {source}; no inference rerun.\n"
            "Excerpt starts at policy setup; full shared log is retained in console.log.\n"
            + excerpts.get(seed, "No separable policy log found; see console.log.\n"))
        block = seeds.index(seed) // IF_SEED_CONTRACTS[task].block_size if task in IF_SEED_CONTRACTS else None
        write_episode_artifacts(destination, record, metadata["arguments"]["task_config"], block=block, legacy=True)
    write_json(destination / "conversion.json", {
        "created_at": datetime.now(timezone.utc).isoformat(), "source": str(source),
        "destination": str(destination), "inference_rerun": False,
        "converter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "note": "run.json and detailed results are original evidence; unavailable measurements remain null",
        "source_sha256": {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(source.rglob("*")) if p.is_file()},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="New task directory; must not exist")
    args = parser.parse_args()
    convert_legacy(args.legacy_dir, args.output_dir)
