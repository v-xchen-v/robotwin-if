#!/usr/bin/env python3
"""Bounded X-VLA smoke evaluation: exact raw seeds or a complete IF block.

Run in the RoboTwin environment. The model stays in its existing HTTP server.
This is an integration runner, not a production benchmark release runner.
"""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time
import traceback

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from if_benchmark.seed_contracts import IF_SEED_CONTRACTS, describe_seed  # noqa: E402
from if_benchmark.seed_manifest import load_manifest, manifest_sha256  # noqa: E402
from policies.xvla.outputs import camera_strip, episode_path, write_episode_artifacts, write_json  # noqa: E402


def git_identity(path):
    def git(*args):
        result = subprocess.run(["git", "-C", str(path), *args], text=True, capture_output=True)
        return result.stdout.strip() if result.returncode == 0 else None
    return {"path": str(path), "commit": git("rev-parse", "HEAD"),
            "status": git("status", "--short", "--untracked-files=no")}


def select_seeds(args):
    manifest = None
    is_if = args.task in IF_SEED_CONTRACTS
    if args.seed_manifest:
        manifest = load_manifest(args.seed_manifest)
        if manifest["task"] != args.task or manifest["task_config"] != args.task_config:
            raise ValueError("Seed manifest task/config do not match the requested run")
        seeds = list(manifest["seeds"])
        if args.blocks is not None:
            count = args.blocks * IF_SEED_CONTRACTS[args.task].block_size
            if args.blocks < 1 or count > len(seeds):
                raise ValueError("--blocks must select existing complete blocks")
            seeds = seeds[:count]
    else:
        if is_if:
            raise ValueError("IF smoke evaluation requires --seed-manifest")
        if args.blocks is not None:
            raise ValueError("--blocks requires --seed-manifest")
        seeds = args.seeds if args.seeds is not None else [2000]
    if not seeds or any(s < 0 or s >= 2**32 for s in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("Provide distinct uint32 episode seeds")
    split = args.instruction_type or ("unseen" if is_if else "task-name")
    if is_if and split == "task-name":
        raise ValueError("IF tasks require generated language, not their task name")
    return seeds, manifest, split


def load_task(target, task_name, task_config):
    # Reuse RoboTwin's config/embodiment resolution, without running collection.
    os.chdir(target)
    sys.path[:0] = [str(target / "script"), str(target), str(target / "description/utils")]
    import collect_data
    captured = {}
    original = collect_data.run
    collect_data.run = lambda task, config: captured.update(task=task, config=deepcopy(config))
    try:
        collect_data.main(task_name=task_name, task_config=task_config)
    finally:
        collect_data.run = original
    config = captured["config"]
    config.update(eval_mode=True, render_freq=0, need_plan=True, save_data=False,
                  collect_data=False, eval_video_log=False, eval_video_save_dir=None,
                  policy_name="xvla", ckpt_setting="smoke")
    return captured["task"], config


def instruction_for(task, episode_info, split, seed):
    if split == "task-name":
        return task.replace("_", " ")
    from generate_episode_instructions import generate_episode_descriptions
    state = random.getstate()
    try:
        # Experimental arm pairs share a template, changing only the arm word.
        paired = (task == "arm_select" and
                  episode_info.get("arm_select_scene", {}).get("version") == "jitter-v2")
        random.seed(seed // 2 if paired else seed)
        descriptions = generate_episode_descriptions(task, [episode_info["info"]], 1)[0][split]
    finally:
        random.setstate(state)
    if not descriptions:
        raise ValueError(f"No {split} instruction generated for {task}")
    return descriptions[0]


def run_episode(env, config, client, args, seed, split, directory, block=None):
    directory.mkdir(parents=True, exist_ok=True)
    prefix = f"{args.task}_ep{seed}"
    if any(directory.glob(prefix + "_*")) or (directory / f"{prefix}.log").exists():
        raise FileExistsError(f"Episode artifacts already exist: {directory / prefix}")
    with (directory / f"{prefix}.log").open("x", buffering=1) as log, redirect_stdout(log), redirect_stderr(log):
        print(f"X-VLA evaluation: task={args.task}, seed={seed}, instruction_type={split}", flush=True)
        return _run_episode(env, config, client, args, seed, split, directory, block)


def _run_episode(env, config, client, args, seed, split, directory, block):
    import imageio.v2 as imageio
    import numpy as np
    from policies.xvla.client import CAMERAS, encode_proprio

    def path(suffix):
        return episode_path(directory, args.task, seed, suffix)

    record = {"seed": seed, "task": args.task, "status": "error", "success": False,
              "instruction_type": split, "instruction": None, "action_calls": 0,
              "chunks": 0, "oracle_success": False, "mode": None}
    if args.task in IF_SEED_CONTRACTS:
        record["mode"] = describe_seed(args.task, seed).mode
    started = time.monotonic()
    raw_chunks, decoded_actions, measured_poses, request_proprio, latencies = [], [], [], [], []
    timings = []
    writer = None
    stage = "oracle_setup"
    try:
        random.seed(seed)
        env.setup_demo(now_ep_num=0, seed=seed, is_test=True, **config)
        if record["mode"] is not None and str(env.mode) != record["mode"]:
            raise RuntimeError("Oracle scene mode does not match the seed contract")
        stage = "oracle_qualification"
        info = deepcopy(env.play_once())
        record["oracle_success"] = bool(env.plan_success and env.check_success())
        write_json(path("_oracle.json"), info)
        if not record["oracle_success"]:
            raise RuntimeError("Exact seed failed oracle qualification; no seed substitution")
        env.close_env()

        stage = "policy_setup"
        random.seed(seed)
        env.setup_demo(now_ep_num=0, seed=seed, is_test=True, **config)
        if record["mode"] is not None and str(env.mode) != record["mode"]:
            raise RuntimeError("Policy scene mode does not match the seed contract")
        # This runner currently validates only arm_select among the IF tasks.
        # Its scene must initialize the success baseline before policy control.
        if args.task == "arm_select" and env._init_box_z is None:
            raise RuntimeError("arm_select did not initialize its policy success baseline")
        instruction = instruction_for(args.task, info, split, seed)
        env.set_instruction(instruction)
        record["instruction"] = instruction
        record["step_limit"] = env.step_lim
        client.reset()
        obs = env.get_obs()
        np.savez_compressed(path("_initial_observation.npz"), proprio=encode_proprio(obs),
                            **{name: obs["observation"][name]["rgb"] for name in CAMERAS})
        writer = imageio.get_writer(path("_rollout.mp4"), fps=10, codec="libx264")
        writer.append_data(camera_strip({name: obs["observation"][name]["rgb"] for name in CAMERAS}))
        print(f"Policy seed={seed}, instruction={instruction!r}, limit={env.step_lim}", flush=True)
        while env.take_action_cnt < env.step_lim and not env.eval_success:
            stage = "inference"
            inference_started = time.monotonic()
            actions, prediction = client.predict(obs, instruction)
            inference_time = time.monotonic() - inference_started
            raw_chunks.append(prediction["raw_actions"])
            request_proprio.append(prediction["proprio"])
            latencies.append(prediction["latency_seconds"])
            record["chunks"] += 1
            print(f"chunk={record['chunks']} shape={actions.shape} latency={latencies[-1]:.2f}s", flush=True)
            for action_index, action in enumerate(actions):
                if env.take_action_cnt >= env.step_lim or env.eval_success:
                    break
                stage = "action_execution"
                measured_poses.append(np.concatenate((obs["endpose"]["left_endpose"],
                                                     obs["endpose"]["right_endpose"])))
                before = env.take_action_cnt
                action_started = time.monotonic()
                env.take_action(action, action_type="ee")
                env_time = time.monotonic() - action_started
                if env.take_action_cnt <= before:
                    raise RuntimeError("take_action did not advance the action counter")
                decoded_actions.append(action)
                client.record_action(action)
                record["action_calls"] = env.take_action_cnt
                charged_inference = inference_time if action_index == 0 else 0.0
                timings.append({"step": len(decoded_actions) - 1, "inference_time_sec": charged_inference,
                                "env_step_time_sec": env_time, "total_time_sec": charged_inference + env_time})
                obs = env.get_obs()
                writer.append_data(camera_strip({name: obs["observation"][name]["rgb"] for name in CAMERAS}))
                if env.eval_success or env.check_success():
                    record["success"] = True
                    break
            if record["success"]:
                break
        record["status"] = "success" if record["success"] else "failure"
        record["termination"] = "task_success" if record["success"] else "action_limit"
        if hasattr(env, "eval_signals"):
            record["signals"] = env.eval_signals()
    except (Exception, SystemExit) as exc:
        record["error"] = {"stage": stage, "type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc()
    finally:
        if writer is not None:
            try:
                writer.close()
                if path("_rollout.mp4").exists():
                    path("_rollout.mp4").rename(path(f"_{int(record['success'])}.mp4"))
            except Exception as exc:
                record["status"] = "error"
                record["video_error"] = str(exc)
        try:
            env.close_env()
        except Exception as exc:
            record["status"] = "error"
            record["close_error"] = str(exc)
        record["elapsed_seconds"] = time.monotonic() - started
        np.savez_compressed(path("_actions.npz"),
                            raw_actions=np.concatenate(raw_chunks) if raw_chunks else np.empty((0, 20)),
                            chunk_lengths=np.array([len(c) for c in raw_chunks]),
                            executed_actions=np.array(decoded_actions).reshape(-1, 16),
                            measured_poses=np.array(measured_poses).reshape(-1, 14),
                            request_proprio=np.array(request_proprio).reshape(-1, 20),
                            request_latency_seconds=np.array(latencies))
        write_json(path("_result.json"), record)
        write_episode_artifacts(directory, record, getattr(args, "task_config", "demo_clean"),
                                block=block, timings=timings)
        print(json.dumps(record, ensure_ascii=False, allow_nan=False), flush=True)
    return record


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="click_bell")
    parser.add_argument("--task-config", default="demo_clean")
    parser.add_argument("--robotwin-dir", type=Path, default=REPO_ROOT / "third_party/robotwin")
    parser.add_argument("--server-url", default="http://127.0.0.1:8010")
    parser.add_argument("--checkpoint", default="2toINF/X-VLA-RoboTwin2")
    parser.add_argument("--checkpoint-revision", help="Declared server checkpoint revision; /act cannot attest it")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="New task directory, e.g. outputs/policy-eval/<run>/xvla/<task>")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--seeds", type=int, nargs="+")
    selection.add_argument("--seed-manifest", type=Path)
    parser.add_argument("--blocks", type=int, help="Smoke subset: first N complete manifest blocks")
    parser.add_argument("--instruction-type", choices=("task-name", "seen", "unseen"))
    parser.add_argument("--feedback", choices=("commanded", "measured"), default="commanded")
    parser.add_argument("--gripper-threshold", type=float, default=0.7)
    parser.add_argument("--denoising-steps", type=int, default=10)
    parser.add_argument("--request-timeout", type=float, default=120)
    parser.add_argument("--sim-gpu", default="1", help="CUDA_VISIBLE_DEVICES for simulation only")
    args = parser.parse_args()
    if not args.task.isidentifier() or Path(args.task_config).name != args.task_config:
        parser.error("Task and task-config must be simple names")
    if args.task in IF_SEED_CONTRACTS and args.task != "arm_select":
        parser.error("This initial runner currently supports arm_select as its IF validation task")
    return args


def main():
    args = parse_args()
    seeds, manifest, split = select_seeds(args)
    target = args.robotwin_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ["CUDA_VISIBLE_DEVICES"] = args.sim_gpu
    os.environ["PYTHONNOUSERSITE"] = "1"
    metadata = {"created_at": datetime.now(timezone.utc).isoformat(), "purpose": "integration_smoke",
                "arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                "seeds": seeds, "instruction_type": split, "output_format": "cogact_episode_v1",
                "server_rng": "Not controlled by the official HTTP API",
                "checkpoint_identity": "User-declared; HTTP API has no checkpoint metadata endpoint",
                "robotwin": git_identity(target), "robotwin_if": git_identity(REPO_ROOT),
                "xvla": git_identity(REPO_ROOT / "third_party/xvla"),
                "client_sha256": {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                                  for name in ("client.py", "eval.py", "outputs.py")},
                "task_config_sha256": hashlib.sha256((target / "task_config" / f"{args.task_config}.yml").read_bytes()).hexdigest(),
                "task_source_sha256": hashlib.sha256((target / "envs" / f"{args.task}.py").read_bytes()).hexdigest(),
                "manifest_sha256": manifest_sha256(manifest) if manifest else None}
    write_json(output / "run.json", metadata)
    records = []
    failure = None
    print(f"Running {args.task} seeds={seeds}; log: {output / 'console.log'}", flush=True)
    with (output / "console.log").open("w", buffering=1) as log, redirect_stdout(log), redirect_stderr(log):
        client = None
        try:
            from policies.xvla.client import XVLAClient
            client = XVLAClient(args.server_url, args.request_timeout, args.denoising_steps,
                                args.feedback, args.gripper_threshold)
            env, config = load_task(target, args.task, args.task_config)
            write_json(output / "resolved_config.json", config)
            for index, seed in enumerate(seeds):
                block = index // IF_SEED_CONTRACTS[args.task].block_size if manifest else None
                record = run_episode(env, config, client, args, seed, split, output, block=block)
                records.append(record)
                print(f"seed={seed} status={record['status']} log={args.task}_ep{seed}.log", flush=True)
                with (output / "results.jsonl").open("a") as stream:
                    stream.write(json.dumps(record, allow_nan=False) + "\n")
                if record["status"] == "error":
                    break
        except (Exception, SystemExit) as exc:
            failure = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        finally:
            if client is not None:
                client.close()
    complete = len(records) == len(seeds) and all(r["status"] != "error" for r in records) and failure is None
    summary = {"task": args.task, "complete": complete, "expected_episodes": len(seeds),
               "recorded_episodes": len(records), "successes": sum(r["status"] == "success" for r in records),
               "error": failure, "per_mode": {}}
    modes = sorted({describe_seed(args.task, seed).mode for seed in seeds}) if manifest else []
    for mode in modes:
        selected = [r for r in records if r["mode"] == mode]
        summary["per_mode"][mode] = {"successes": sum(r["status"] == "success" for r in selected),
                                     "recorded": len(selected), "expected": sum(describe_seed(args.task, s).mode == mode for s in seeds)}
    write_json(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)
    return 2 if not complete else (0 if summary["successes"] else 1)


if __name__ == "__main__":
    sys.exit(main())
