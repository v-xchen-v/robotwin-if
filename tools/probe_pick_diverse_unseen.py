#!/usr/bin/env python3
"""Probe metadata-qualified Unseen variants in real Pick-Diverse-Object scenes.

Examples (inside the RoboTwin conda environment):

    python tools/probe_pick_diverse_unseen.py --phase settle --first-id-per-noun
    python tools/probe_pick_diverse_unseen.py --phase grasp --nouns speaker --model-id 1
    python tools/probe_pick_diverse_unseen.py --phase grasp --repeats 2 --arms left right

Every trial uses one forced candidate as target plus three different Unseen candidate
nouns. Results are evidence for pool selection; the script never edits UNSEEN_POOL.
"""
import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
from collections import Counter

import numpy as np

from _pick_diverse_probe_logic import (
    ensure_video_output_available as _ensure_video_output_available,
    qualify_for_oracle as _qualify_for_oracle,
    video_output_path as _video_output_path,
)

INVOCATION_CWD = os.getcwd()
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RT = os.path.join(REPO, "third_party", "robotwin")
os.chdir(RT)
sys.path[:0] = [os.path.join(RT, "script"), RT]

import collect_data as cd  # noqa: E402
from envs._pick_diverse_object_pool import PROBE_UNSEEN_CANDIDATES  # noqa: E402


CANDIDATE_SET = "historical"
ALL_CANDIDATE_NOUNS = tuple(PROBE_UNSEEN_CANDIDATES)


CAPTURE = {}
cd.run = lambda task, args: CAPTURE.update(task=task, args=args)
cd.main(task_name="pick_diverse_object", task_config="demo_clean")
TASK = CAPTURE["task"]
TASK_ARGS = dict(CAPTURE["args"])
TASK_ARGS["render_freq"] = 0

# Compact, visually distinct metadata candidates used as probe clutter. A target from
# this list is replaced so all four scene nouns remain distinct.
CLUTTER_PRIORITY = (
    "speaker",
    "pencil cup",
    "hydrating oil",
    "glue bottle",
    "shampoo bottle",
    "wooden mallet",
)


def _plain(value):
    if isinstance(value, np.ndarray):
        return value.astype(float).tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _component_vector(actor, names):
    for component in actor.actor.get_components():
        for name in names:
            value = getattr(component, name, None)
            if value is None:
                continue
            if callable(value):
                try:
                    value = value()
                except TypeError:
                    continue
            try:
                array = np.asarray(value, dtype=float).reshape(-1)
            except (TypeError, ValueError):
                continue
            if len(array) >= 3:
                return array[:3]
    return None


def _scene_diagnostics():
    objects = []
    positions = []
    max_linear_speed = 0.0
    max_angular_speed = 0.0
    velocity_available = False
    for item in TASK.scene_objects:
        pose = item["actor"].get_pose()
        linear = _component_vector(item["actor"], ("linear_velocity", "get_linear_velocity"))
        angular = _component_vector(item["actor"], ("angular_velocity", "get_angular_velocity"))
        if linear is not None:
            velocity_available = True
            max_linear_speed = max(max_linear_speed, float(np.linalg.norm(linear)))
        if angular is not None:
            velocity_available = True
            max_angular_speed = max(max_angular_speed, float(np.linalg.norm(angular)))
        p = np.asarray(pose.p, dtype=float)
        spawn_position = item.get("spawn_position")
        spawn_quaternion = item.get("spawn_quaternion")
        spawn_p = (
            None if spawn_position is None
            else np.asarray(spawn_position, dtype=float)
        )
        xy_drift = (
            None if spawn_p is None
            else float(np.linalg.norm(p[:2] - spawn_p[:2]))
        )
        positions.append(p)
        objects.append({
            "noun": item["noun"],
            "asset": item["modelname"],
            "model_id": int(item["model_id"]),
            "role": item["role"],
            "placement_index": int(item.get("placement_index", len(objects))),
            "position": p.tolist(),
            "quaternion": np.asarray(pose.q, dtype=float).tolist(),
            "spawn_position": None if spawn_p is None else spawn_p.tolist(),
            "spawn_quaternion": (
                None if spawn_quaternion is None
                else np.asarray(spawn_quaternion, dtype=float).tolist()
            ),
            "spawn_to_settled_xy_drift": xy_drift,
            "linear_velocity": None if linear is None else linear.tolist(),
            "angular_velocity": None if angular is None else angular.tolist(),
        })

    min_xy_sep = None
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            distance = float(np.linalg.norm(positions[i][:2] - positions[j][:2]))
            min_xy_sep = distance if min_xy_sep is None else min(min_xy_sep, distance)
    workspace_ok = all(
        abs(float(p[0])) <= 0.38
        and -0.34 <= float(p[1]) <= 0.16
        and float(p[2]) >= 0.68
        for p in positions
    )
    motion_ok = (
        max_linear_speed <= 0.03 and max_angular_speed <= 0.3
        if velocity_available
        else True
    )
    return {
        "objects": objects,
        "min_xy_separation": min_xy_sep,
        "max_linear_speed": max_linear_speed if velocity_available else None,
        "max_angular_speed": max_angular_speed if velocity_available else None,
        "velocity_available": velocity_available,
        "workspace_ok": workspace_ok,
        "motion_ok": motion_ok,
        "placement_policy": getattr(TASK, "placement_policy", None),
        "placement_sequence": [item["noun"] for item in objects],
        "settle_ok": bool(workspace_ok and motion_ok),
    }


def _distractors(target_noun, candidate_pool):
    nouns = [noun for noun in CLUTTER_PRIORITY if noun != target_noun]
    missing = [noun for noun in nouns if noun not in candidate_pool]
    if missing:
        raise ValueError(f"clutter nouns are not in the candidate pool: {missing}")
    return tuple(nouns[:3])


def _clear_overrides():
    TASK.FAMILIARITY_OVERRIDE = None
    TASK.POOL_OVERRIDE = None
    TASK.TARGET_NOUN_OVERRIDE = None
    TASK.TARGET_MODEL_ID_OVERRIDE = None
    TASK.TARGET_SIDE_OVERRIDE = None
    TASK.DISTRACTOR_NOUNS_OVERRIDE = None


def _run_oracle(record, origin_z):
    try:
        TASK.play_once()
        record["oracle_ok"] = bool(TASK.check_success())
        record["target_z_rise"] = float(TASK.target.get_pose().p[2]) - origin_z
        record["instruction_target"] = TASK.info.get("info", {}).get("{A}")
        if not record["oracle_ok"]:
            record["failure"] = "check_success"
    except Exception as exc:
        record["oracle_ok"] = False
        record["failure"] = f"oracle:{type(exc).__name__}: {exc}"


def _run_oracle_with_video(record, origin_z, video_dir=None, overwrite=False):
    record["video_path"] = None
    record["video_error"] = None
    if video_dir is None:
        _run_oracle(record, origin_z)
        return

    os.makedirs(video_dir, exist_ok=True)
    target_path = _video_output_path(video_dir, record["seed"], record["arm"])
    _ensure_video_output_available(target_path, overwrite=overwrite)
    previous = {
        name: getattr(TASK, name, None)
        for name in ("save_data", "save_dir", "ep_num", "FRAME_IDX", "folder_path")
    }

    with tempfile.TemporaryDirectory(prefix="pick-diverse-video-") as temp_dir:
        try:
            TASK.save_data = True
            TASK.save_dir = temp_dir
            TASK.ep_num = 0
            TASK.FRAME_IDX = 0
            TASK._take_picture()
            _run_oracle(record, origin_z)
            TASK.merge_pkl_to_hdf5_video()
            source_path = os.path.join(temp_dir, "video", "episode0.mp4")
            shutil.copy2(source_path, target_path)
            record["video_path"] = os.path.relpath(target_path, INVOCATION_CWD)
        except Exception as exc:
            record["video_error"] = f"{type(exc).__name__}: {exc}"
            if record["oracle_ok"] is None:
                TASK.save_data = False
                _run_oracle(record, origin_z)
        finally:
            for name, value in previous.items():
                setattr(TASK, name, value)


def run_production_trial(seed, phase, video_dir=None, overwrite=False):
    if seed % 2 != 1:
        raise ValueError(f"production Unseen probe requires an odd raw seed, got {seed}")
    _clear_overrides()
    record = {
        "candidate_set": "production",
        "noun": None,
        "asset": None,
        "model_id": None,
        "arm": None,
        "seed": int(seed),
        "phase": phase,
        "setup_ok": False,
        "settle_ok": False,
        "oracle_ok": None,
        "oracle_attempted": False,
        "video_path": None,
        "video_error": None,
        "failure": None,
    }
    try:
        TASK.setup_demo(now_ep_num=0, seed=seed, **TASK_ARGS)
        record["setup_ok"] = True
        record["noun"] = TASK.target_noun
        record["asset"] = TASK.target_modelname
        record["model_id"] = int(TASK.target_id)
        record.update(_scene_diagnostics())
        actual_arm = "right" if TASK.target.get_pose().p[0] > 0 else "left"
        record["arm"] = actual_arm
        record["actual_arm"] = actual_arm
    except Exception as exc:
        record["failure"] = f"setup:{type(exc).__name__}: {exc}"
        return record

    if phase == "settle":
        if not record["settle_ok"]:
            record["failure"] = "settle"
        return record

    if not _qualify_for_oracle(record):
        return record
    origin_z = float(TASK.target_origin_z)
    _run_oracle_with_video(record, origin_z, video_dir, overwrite)
    return record


def run_pool_trial(seed, phase, candidate_pool, video_dir=None, overwrite=False):
    if seed % 2 != 1:
        raise ValueError(f"candidate-pool probe requires an odd raw seed, got {seed}")
    _clear_overrides()
    TASK.FAMILIARITY_OVERRIDE = "unseen"
    TASK.POOL_OVERRIDE = candidate_pool
    record = {
        "candidate_set": CANDIDATE_SET,
        "noun": None,
        "asset": None,
        "model_id": None,
        "arm": None,
        "seed": int(seed),
        "phase": phase,
        "setup_ok": False,
        "settle_ok": False,
        "oracle_ok": None,
        "oracle_attempted": False,
        "video_path": None,
        "video_error": None,
        "failure": None,
    }
    try:
        TASK.setup_demo(now_ep_num=0, seed=seed, **TASK_ARGS)
        record["setup_ok"] = True
        record["noun"] = TASK.target_noun
        record["asset"] = TASK.target_modelname
        record["model_id"] = int(TASK.target_id)
        record.update(_scene_diagnostics())
        actual_arm = "right" if TASK.target.get_pose().p[0] > 0 else "left"
        record["arm"] = actual_arm
        record["actual_arm"] = actual_arm
    except Exception as exc:
        record["failure"] = f"setup:{type(exc).__name__}: {exc}"
        return record

    if phase == "settle":
        if not record["settle_ok"]:
            record["failure"] = "settle"
        return record

    if not _qualify_for_oracle(record):
        return record
    origin_z = float(TASK.target_origin_z)
    _run_oracle_with_video(record, origin_z, video_dir, overwrite)
    return record


def run_trial(
    noun, model_id, arm, seed, phase, candidate_pool,
    video_dir=None, overwrite=False,
):
    _clear_overrides()
    TASK.FAMILIARITY_OVERRIDE = "unseen"
    TASK.POOL_OVERRIDE = candidate_pool
    TASK.TARGET_NOUN_OVERRIDE = noun
    TASK.TARGET_MODEL_ID_OVERRIDE = model_id
    TASK.TARGET_SIDE_OVERRIDE = arm
    TASK.DISTRACTOR_NOUNS_OVERRIDE = _distractors(noun, candidate_pool)

    record = {
        "candidate_set": CANDIDATE_SET,
        "noun": noun,
        "asset": candidate_pool[noun]["asset"],
        "model_id": int(model_id),
        "arm": arm,
        "seed": int(seed),
        "phase": phase,
        "setup_ok": False,
        "settle_ok": False,
        "oracle_ok": None,
        "oracle_attempted": False,
        "video_path": None,
        "video_error": None,
        "failure": None,
    }
    try:
        TASK.setup_demo(now_ep_num=0, seed=seed, **TASK_ARGS)
        record["setup_ok"] = True
        record.update(_scene_diagnostics())
        actual_arm = "right" if TASK.target.get_pose().p[0] > 0 else "left"
        record["actual_arm"] = actual_arm
        if actual_arm != arm:
            record["failure"] = "side_mismatch"
            record["settle_ok"] = False
            return record
    except Exception as exc:
        record["failure"] = f"setup:{type(exc).__name__}: {exc}"
        return record

    if phase == "settle":
        if not record["settle_ok"]:
            record["failure"] = "settle"
        return record

    if not _qualify_for_oracle(record):
        return record
    origin_z = float(TASK.target_origin_z)
    _run_oracle_with_video(record, origin_z, video_dir, overwrite)
    return record


def write_results(path, args, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    summary = {
        "trials": len(records),
        "setup_ok": sum(bool(r["setup_ok"]) for r in records),
        "settle_ok": sum(bool(r["settle_ok"]) for r in records),
        "oracle_attempted": sum(bool(r["oracle_attempted"]) for r in records),
        "oracle_ok": sum(r["oracle_ok"] is True for r in records),
        "videos": sum(bool(r.get("video_path")) for r in records),
        "video_errors": sum(bool(r.get("video_error")) for r in records),
        "failures": dict(Counter(r["failure"] for r in records if r["failure"])),
    }
    payload = {"args": vars(args), "summary": summary, "records": records}
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2, default=_plain)

    csv_path = os.path.splitext(path)[0] + ".csv"
    fields = (
        "candidate_set", "noun", "asset", "model_id", "arm", "seed", "phase",
        "setup_ok", "settle_ok", "oracle_attempted", "oracle_ok", "actual_arm",
        "target_z_rise", "instruction_target", "workspace_ok", "motion_ok",
        "velocity_available", "min_xy_separation", "max_linear_speed",
        "max_angular_speed", "placement_policy", "placement_sequence", "video_path",
        "video_error", "failure",
    )
    with open(csv_path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = {
                field: (
                    json.dumps(record.get(field))
                    if isinstance(record.get(field), (dict, list, tuple))
                    else record.get(field)
                )
                for field in fields
            }
            writer.writerow(row)
    return summary, csv_path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=("settle", "grasp"), default="settle")
    ap.add_argument("--nouns", nargs="*", choices=ALL_CANDIDATE_NOUNS)
    ap.add_argument("--model-id", type=int,
                    help="probe one exact id; requires exactly one --nouns value")
    ap.add_argument(
        "--variants", nargs="+", metavar="NOUN:MODEL_ID",
        help="probe an explicit exact-variant list; quote nouns containing spaces",
    )
    ap.add_argument(
        "--production-seeds", nargs="+", type=int, metavar="ODD_SEED",
        help="probe real production Unseen episodes with every override cleared",
    )
    ap.add_argument(
        "--pool-seeds", nargs="+", type=int, metavar="ODD_SEED",
        help="probe scheduled episodes from the retained shortlist pool",
    )
    ap.add_argument("--first-id-per-noun", action="store_true")
    ap.add_argument("--arms", nargs="+", choices=("left", "right"), default=("left", "right"))
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--base-seed", type=int, default=1000)
    ap.add_argument("--output", required=True, help="JSON path; a CSV sidecar is also written")
    ap.add_argument(
        "--video-dir",
        help="optional MP4 directory for grasp trials; files are named by seed and arm",
    )
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()
    args.output = os.path.abspath(os.path.join(INVOCATION_CWD, args.output))
    if args.video_dir is not None:
        args.video_dir = os.path.abspath(
            os.path.join(INVOCATION_CWD, args.video_dir)
        )

    csv_output = os.path.splitext(args.output)[0] + ".csv"
    existing_outputs = [
        path for path in (args.output, csv_output) if os.path.exists(path)
    ]
    if existing_outputs and not args.overwrite:
        ap.error(
            f"output exists: {existing_outputs[0]} (pass --overwrite to replace it)"
        )
    if args.video_dir is not None:
        if args.phase != "grasp":
            ap.error("--video-dir requires --phase grasp")
        os.makedirs(args.video_dir, exist_ok=True)
    candidate_pool = PROBE_UNSEEN_CANDIDATES
    candidate_options = (
        bool(args.nouns), args.model_id is not None, bool(args.variants),
        args.first_id_per_noun,
    )
    if args.production_seeds and (args.pool_seeds or any(candidate_options)):
        ap.error(
            "--production-seeds cannot be combined with pool/candidate-selection options"
        )
    if args.pool_seeds and (args.production_seeds or any(candidate_options)):
        ap.error("--pool-seeds cannot be combined with production/candidate-selection options")
    seed_modes = (args.production_seeds or []) + (args.pool_seeds or [])
    if any(seed % 2 != 1 for seed in seed_modes):
        ap.error("--production-seeds/--pool-seeds accept only odd raw seeds")
    if args.variants and (args.nouns or args.model_id is not None or args.first_id_per_noun):
        ap.error("--variants cannot be combined with --nouns/--model-id/--first-id-per-noun")

    variants = []
    if not args.production_seeds and not args.pool_seeds:
        if args.variants:
            for spec in args.variants:
                try:
                    noun, raw_model_id = spec.rsplit(":", 1)
                    model_id = int(raw_model_id)
                except (ValueError, TypeError):
                    ap.error(f"invalid --variants value {spec!r}; expected NOUN:MODEL_ID")
                if noun not in candidate_pool:
                    ap.error(
                        f"unknown candidate noun: {noun!r}"
                    )
                if model_id not in candidate_pool[noun]["model_ids"]:
                    ap.error(f"model id {model_id} is not a candidate for {noun}")
                variants.append((noun, model_id))
        else:
            nouns = args.nouns or list(candidate_pool)
            missing = [noun for noun in nouns if noun not in candidate_pool]
            if missing:
                ap.error(
                    f"unknown candidate nouns: {missing}"
                )
            if args.model_id is not None and len(nouns) != 1:
                ap.error("--model-id requires exactly one --nouns value")
            for noun in nouns:
                model_ids = candidate_pool[noun]["model_ids"]
                if args.model_id is not None:
                    if args.model_id not in model_ids:
                        ap.error(f"model id {args.model_id} is not a candidate for {noun}")
                    model_ids = (args.model_id,)
                elif args.first_id_per_noun:
                    model_ids = model_ids[:1]
                variants.extend((noun, model_id) for model_id in model_ids)

    records = []
    if args.production_seeds:
        for seed in args.production_seeds:
            record = run_production_trial(
                seed, args.phase, args.video_dir, args.overwrite
            )
            records.append(record)
            mark = "OK" if (
                record["oracle_ok"] is True
                if args.phase == "grasp"
                else record["settle_ok"]
            ) else "XX"
            noun = record["noun"] or "<setup failed>"
            print(
                f"[{mark}] production {noun:16s} seed={seed} "
                f"setup={record['setup_ok']} settle={record['settle_ok']} "
                f"oracle={record['oracle_ok']} fail={record['failure']}",
                flush=True,
            )
            write_results(args.output, args, records)
    elif args.pool_seeds:
        for seed in args.pool_seeds:
            record = run_pool_trial(
                seed, args.phase, candidate_pool, args.video_dir, args.overwrite,
            )
            records.append(record)
            mark = "OK" if (
                record["oracle_ok"] is True
                if args.phase == "grasp"
                else record["settle_ok"]
            ) else "XX"
            noun = record["noun"] or "<setup failed>"
            print(
                f"[{mark}] {CANDIDATE_SET} {noun:16s} seed={seed} "
                f"setup={record['setup_ok']} settle={record['settle_ok']} "
                f"oracle={record['oracle_ok']} fail={record['failure']}",
                flush=True,
            )
            write_results(args.output, args, records)
    else:
        trial_index = 0
        for noun, model_id in variants:
            for repeat in range(args.repeats):
                for arm in args.arms:
                    seed = args.base_seed + trial_index
                    record = run_trial(
                        noun, model_id, arm, seed, args.phase, candidate_pool,
                        args.video_dir, args.overwrite,
                    )
                    records.append(record)
                    trial_index += 1
                    mark = "OK" if (
                        record["oracle_ok"] is True
                        if args.phase == "grasp"
                        else record["settle_ok"]
                    ) else "XX"
                    print(
                        f"[{mark}] {noun:16s} b{model_id:<2d} {arm:5s} seed={seed} "
                        f"setup={record['setup_ok']} settle={record['settle_ok']} "
                        f"oracle={record['oracle_ok']} fail={record['failure']}",
                        flush=True,
                    )
                    # Keep recoverable evidence if a long sweep is interrupted.
                    write_results(args.output, args, records)

    summary, csv_path = write_results(args.output, args, records)
    print("\nsummary:", summary)
    print("json ->", args.output)
    print("csv  ->", csv_path)


if __name__ == "__main__":
    main()
