#!/usr/bin/env python3
"""Run paired oracle checks, optionally followed by an X-VLA experiment.

No task bridge or maintained-suite registration is needed. This process adds the
local experimental modules to RoboTwin's env package search path only.
"""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback


ROOT = Path(__file__).resolve().parents[1]
TASK = "bottle_hold_place"
sys.path.insert(0, str(ROOT))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def pair_seeds(start_pair, pairs):
    if start_pair < 0 or pairs < 1 or 2 * (start_pair + pairs) > 2**32:
        raise ValueError("provide a nonnegative start pair and a positive uint32-range pair count")
    return list(range(2 * start_pair, 2 * (start_pair + pairs)))


def summarize_pairs(records):
    from tasks.envs._bottle_hold_place import MODES

    grouped = {}
    for record in records:
        grouped.setdefault(record["seed"] // 2, []).append(record)
    return {
        "episodes": len(records),
        "per_mode": {mode: {
            "episodes": sum(r["mode"] == mode for r in records),
            "successes": sum(r["mode"] == mode and bool(r["success"]) for r in records),
        } for mode in MODES},
        "pairs": len(grouped),
        "both_success": sum(len(rows) == 2 and {r["mode"] for r in rows} == set(MODES)
                            and all(r["success"] for r in rows) for rows in grouped.values()),
    }


def qualify(env, config, seeds, directory, video):
    import imageio.v2 as imageio
    import numpy as np
    from policies.xvla.client import CAMERAS, encode_proprio
    from policies.xvla.outputs import camera_strip
    from tasks.envs._bottle_hold_place import mode_for_seed

    directory.mkdir()
    records, observations, pairs = [], {}, []
    for seed in seeds:
        record = dict(seed=seed, mode=mode_for_seed(seed), success=False, status="error")
        prefix = directory / f"{TASK}_ep{seed}"
        writer = None
        stage = "setup"
        with prefix.with_suffix(".log").open("w") as log, redirect_stdout(log), redirect_stderr(log):
            try:
                env.setup_demo(seed=seed, now_ep_num=0, is_test=True, **config)
                if env.mode != record["mode"]:
                    raise RuntimeError("seed and actual mode differ")
                initial = env.get_obs()
                arrays = {name: initial["observation"][name]["rgb"].copy() for name in CAMERAS}
                arrays["proprio"] = encode_proprio(initial).copy()
                np.savez_compressed(str(prefix) + "_initial.npz", **arrays)
                imageio.imwrite(str(prefix) + "_initial.png", camera_strip(arrays))
                observations[seed] = arrays
                if video:
                    writer = imageio.get_writer(str(prefix) + "_oracle.mp4", fps=10, codec="libx264")
                    writer.append_data(camera_strip(arrays))
                next_frame = 0.1
                with Path(str(prefix) + "_trace.jsonl").open("w") as trace:
                    def observe(task):
                        nonlocal next_frame
                        if task.monitor.time + 1e-9 < next_frame:
                            return
                        next_frame = task.monitor.time + 0.1
                        trace.write(json.dumps(task.eval_signals(), allow_nan=False) + "\n")
                        if writer is not None:
                            obs = task.get_obs()
                            writer.append_data(camera_strip({n: obs["observation"][n]["rgb"] for n in CAMERAS}))

                    env.trace_callback = observe
                    stage = "oracle"
                    info = env.play_once()
                    success = bool(env.plan_success and env.check_success())
                    record.update(success=success, status="success" if success else "oracle_failed",
                                  instruction=env.policy_instruction("unseen"), info=info,
                                  signals=env.eval_signals())
                    terminal = env.get_obs()
                    imageio.imwrite(str(prefix) + "_terminal.png", camera_strip(
                        {n: terminal["observation"][n]["rgb"] for n in CAMERAS}))
            except (Exception, SystemExit) as exc:
                record["error"] = dict(stage=stage, type=type(exc).__name__, message=str(exc))
                traceback.print_exc()
            finally:
                env.trace_callback = None
                if writer is not None:
                    writer.close()
                try:
                    env.close_env()
                except Exception as exc:
                    record.update(success=False, status="error", close_error=str(exc))
        records.append(record)
        write_json(Path(str(prefix) + "_result.json"), record)
        print(f"oracle seed={seed} mode={record['mode']} status={record['status']}", flush=True)
        if seed % 2:
            left, right = observations.pop(seed - 1, None), observations.pop(seed, None)
            equal = {key: bool(np.array_equal(left[key], right[key])) for key in left} if left is not None and right is not None else {}
            pairs.append(dict(scene_seed=seed // 2, seeds=[seed - 1, seed],
                              initial_arrays_equal=equal,
                              qualified=bool(equal and all(equal.values()) and
                                             all(r["success"] for r in records[-2:]))))
    report = dict(summarize_pairs(records), records=records, pair_checks=pairs,
                  qualified=all(p["qualified"] for p in pairs) and len(pairs) * 2 == len(seeds))
    write_json(directory / "qualification.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robotwin-dir", type=Path, default=ROOT / "third_party/robotwin")
    parser.add_argument("--task-config", default="demo_clean")
    parser.add_argument("--pairs", type=int, default=4)
    parser.add_argument("--start-pair", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sim-gpu", default="0")
    parser.add_argument("--no-video", action="store_true", help="Skip oracle video; keep images and traces")
    parser.add_argument("--policy", choices=("oracle", "xvla"), default="oracle")
    parser.add_argument("--server-url", default="http://127.0.0.1:8010")
    parser.add_argument("--checkpoint", default="2toINF/X-VLA-RoboTwin2", help="Declared server checkpoint")
    args = parser.parse_args(argv)
    try:
        seeds = pair_seeds(args.start_pair, args.pairs)
    except ValueError as exc:
        parser.error(str(exc))
    if Path(args.task_config).name != args.task_config:
        parser.error("task config must be a simple name")
    target, output = args.robotwin_dir.resolve(), args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ["CUDA_VISIBLE_DEVICES"] = args.sim_gpu
    os.environ["PYTHONNOUSERSITE"] = "1"
    os.chdir(target)
    sys.path.insert(0, str(target))
    import envs
    envs.__path__.append(str(ROOT / "tasks/envs"))
    from policies.xvla.eval import git_identity, load_task, run_episode

    source_files = ("tasks/envs/bottle_hold_place.py", "tasks/envs/_bottle_hold_place.py",
                    "tasks/task_instruction/bottle_hold_place.json", "tools/bottle_hold_place.py",
                    "policies/evaluation.py", "policies/xvla/eval.py")
    write_json(output / "run.json", dict(
        created_at=datetime.now(timezone.utc).isoformat(), purpose="experimental-bottle-hold-place",
        task=TASK, policy=args.policy, seeds=seeds, checkpoint=args.checkpoint if args.policy != "oracle" else None,
        server_url=args.server_url if args.policy != "oracle" else None,
        robotwin=git_identity(target), robotwin_if=git_identity(ROOT),
        source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_files},
        task_config_sha256=hashlib.sha256((target / "task_config" / f"{args.task_config}.yml").read_bytes()).hexdigest()))
    env, config = load_task(target, TASK, args.task_config)
    # The pilot deliberately fixes clean conditions; record the effective config.
    config["domain_randomization"] = dict(config["domain_randomization"], random_background=False,
        cluttered_table=False, random_head_camera_dis=0, random_table_height=0,
        random_light=False, crazy_random_light_rate=0)
    config["save_freq"] = None
    write_json(output / "resolved_config.json", config)
    qualification = qualify(env, config, seeds, output / "oracle", not args.no_video)
    if not qualification["qualified"] or args.policy == "oracle":
        summary = {key: qualification[key] for key in ("qualified", "episodes", "per_mode", "pairs", "both_success")}
        write_json(output / "summary.json", summary)
        print(json.dumps(summary), flush=True)
        return 0 if qualification["qualified"] else 2

    from policies.xvla.client import XVLAClient
    records = []
    args.task = TASK
    client = XVLAClient(args.server_url)
    try:
        for seed in seeds:
            record = run_episode(env, config, client, args, seed, "unseen", output / "xvla", block=seed // 2)
            records.append(record)
            print(f"policy seed={seed} status={record['status']}", flush=True)
            if record["status"] == "error":
                break
    finally:
        client.close()
    summary = dict(summarize_pairs(records),
                   complete=len(records) == len(seeds) and all(r["status"] != "error" for r in records),
                   expected_episodes=len(seeds), oracle_qualified=True)
    write_json(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)
    return 0 if summary["complete"] else 2


if __name__ == "__main__":
    sys.exit(main())
