"""Hy-VLA episode files following the existing CogACT/X-VLA output format."""

import imageio.v2 as imageio
import numpy as np
from scipy.spatial.transform import Rotation

from policies.xvla.outputs import camera_strip, episode_path, write_json


def write_episode_artifacts(directory, record, task_config, block, timings, raw_chunks):
    def path(suffix):
        return episode_path(directory, record["task"], record["seed"], suffix)

    logs = []
    for raw in raw_chunks:
        entry = {}
        for arm, start in (("LEFT", 0), ("RIGHT", 8)):
            quaternion = raw[:, start + 3:start + 7]
            matrices = Rotation.from_quat(quaternion[:, [1, 2, 3, 0]]).as_matrix()
            entry.update({f"ROBOT_{arm}_TRANS": raw[:, start:start + 3].tolist(),
                          f"ROBOT_{arm}_GRIPPER": raw[:, start + 7:start + 8].tolist(),
                          f"ROBOT_{arm}_ROT_QUAT": quaternion.tolist(),
                          f"ROBOT_{arm}_ROT_MAT": matrices.tolist(),
                          f"ROBOT_{arm}_ROT_6D": matrices[:, :2, :].reshape(-1, 6).tolist(),
                          f"ROBOT_{arm}_JOINT_POS": None})
        logs.append(entry)
    write_json(path("_action_logs.json"), logs)
    write_json(path("_timings.json"), timings)
    errors = {k: record[k] for k in ("error", "video_error", "close_error") if k in record}
    unavailable = ("target_key", "grasp_target_key", "grasp_target_correct", "grasp_dist_threshold_m",
                   "grasp_target_dist_m", "grasp_target_correct_within_th", "grasp_events", "min_gripper",
                   "lift_threshold_m", "max_lift_m", "lift_step", "target_lift_step", "lifted_keys", "target_lifted")
    duration = record["elapsed_seconds"]
    summary = {"task": record["task"], "config": task_config, "instruction": record["instruction"],
               "instruction_type": record["instruction_type"], "episode_id": record["seed"], "seed": record["seed"],
               "steps": record["action_calls"], "duration_sec": duration,
               "fps": record["action_calls"] / duration if duration else None,
               "success": record["success"], "execution_runtime_error": errors or None,
               "total_inference_time_sec": sum(t["inference_time_sec"] for t in timings),
               "total_env_step_time_sec": sum(t["env_step_time_sec"] for t in timings),
               "total_step_time_sec": sum(t["total_time_sec"] for t in timings),
               **dict.fromkeys(unavailable), "signals": record.get("signals")}
    write_json(path("_summary.json"), summary)
    write_json(path("_status.json"), {"task": record["task"], "seed": record["seed"], "mode": record["mode"],
                                    "block": block, "status": {"success": "policy_success", "failure": "policy_failure",
                                                               "error": "execution_error"}[record["status"]],
                                    "detail": errors or None, "attempts": 1})
    path("_instruction.txt").write_text(f"task: {record['task']}\nepisode_id: {record['seed']}\n"
                                       f"instruction_type: {record['instruction_type']}\n"
                                       f"instruction: {record['instruction'] or ''}\n")
    if path("_initial_observation.npz").exists():
        with np.load(path("_initial_observation.npz")) as obs:
            imageio.imwrite(path("_step0000.png"), camera_strip(obs))
    write_json(path("_diagnostics.json"), {
        "format": "cogact_episode_v1", "policy": "hy_vla", "action_type": "ee",
        "action_log_semantics": "Full 20-step absolute EE chunks from the official rel+abs decoder. "
                                "Quaternions use native RoboTwin wxyz; ROT_6D contains the first two matrix rows. "
                                "Normalized 40x20 model tokens and executed 7-step prefixes are in _actions.npz.",
        "duration_scope": "Whole episode including oracle, scene setup, server reset and environment close",
        "timing_scope": "Every step includes an RPC to append the latest camera frames. "
                        "inference_time_sec includes client packing, transport, and model/cache service time. "
                        "new_chunk distinguishes model calls from cached steps. Observation/video IO excluded.",
        "history_semantics": "One pre-action observation per executed step; six frames at offsets "
                             "[-25,-20,-15,-10,-5,0]; unavailable frames zeroed; all history cleared at reset.",
        "unavailable_summary_fields": list(unavailable),
        "video_views": ["head_camera", "left_camera", "right_camera"],
    })
