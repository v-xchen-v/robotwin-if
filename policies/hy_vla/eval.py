#!/usr/bin/env python3
"""Exact-seed Hy-VLA smoke runner: native task first, then one complete IF block."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from if_benchmark.seed_contracts import IF_SEED_CONTRACTS, describe_seed  # noqa: E402
from policies.evaluation import setup_episode  # noqa: E402
from if_benchmark.seed_manifest import manifest_sha256  # noqa: E402
from policies.xvla.eval import git_identity, load_task, select_seeds  # noqa: E402
from policies.xvla.outputs import camera_strip, episode_path, write_json  # noqa: E402
from policies.hy_vla.outputs import write_episode_artifacts  # noqa: E402


def run_episode(env, config, client, args, seed, split, directory, block=None):
    directory.mkdir(parents=True, exist_ok=True)
    prefix = f"{args.task}_ep{seed}"
    if any(directory.glob(prefix + "_*")) or (directory / f"{prefix}.log").exists():
        raise FileExistsError(f"Episode already recorded: {prefix}")
    with (directory / f"{prefix}.log").open("x", buffering=1) as log, redirect_stdout(log), redirect_stderr(log):
        return _run_episode(env, config, client, args, seed, split, directory, block)


def _run_episode(env, config, client, args, seed, split, directory, block):
    import imageio.v2 as imageio
    import numpy as np
    from policies.hy_vla.client import CAMERAS, encode_proprio

    def path(suffix):
        return episode_path(directory, args.task, seed, suffix)

    def frame(obs):
        return camera_strip({name: obs["observation"][name]["rgb"] for name in CAMERAS})

    record = {"task": args.task, "seed": seed, "status": "error", "success": False,
              "instruction_type": split, "instruction": None, "action_calls": 0, "chunks": 0,
              "oracle_success": False, "mode": describe_seed(args.task, seed).mode if args.task in IF_SEED_CONTRACTS else None}
    raw_chunks, model_chunks, executed_actions, measured_poses, measured_joints, timings = [], [], [], [], [], []
    reset_started = False
    writer = None
    started = time.monotonic()
    stage = "episode_setup"
    try:
        print(f"Hy-VLA task={args.task} seed={seed}", flush=True)
        instruction, obs = setup_episode(env, config, args, seed, split, record, path)
        np.savez_compressed(path("_initial_observation.npz"), proprio=encode_proprio(obs),
                            joint_state=obs["joint_action"]["vector"],
                            **{name: obs["observation"][name]["rgb"] for name in CAMERAS})
        writer = imageio.get_writer(path("_rollout.mp4"), fps=10, codec="libx264")
        writer.append_data(frame(obs))
        stage = "server_reset"
        reset_started = True
        client.reset(instruction, seed)
        print(f"Policy instruction={instruction!r}; limit={env.step_lim}", flush=True)
        while env.take_action_cnt < env.step_lim and not record["success"]:
            stage = "inference"
            action, prediction = client.predict(obs)
            if prediction["new_chunk"]:
                raw_chunks.append(prediction["raw_actions"])
                model_chunks.append(prediction["model_actions"])
                record["chunks"] += 1
                print(f"chunk={record['chunks']} execute_horizon=7 latency={prediction['latency_seconds']:.2f}s", flush=True)
            stage = "action_execution"
            measured = encode_proprio(obs)
            before = env.take_action_cnt
            action_started = time.monotonic()
            env.take_action(action, action_type="ee")
            env_time = time.monotonic() - action_started
            if env.take_action_cnt <= before:
                raise RuntimeError("take_action did not advance action counter")
            executed_actions.append(action)
            measured_poses.append(measured)
            measured_joints.append(np.asarray(obs["joint_action"]["vector"]).copy())
            record["action_calls"] = env.take_action_cnt
            inference_time = prediction["latency_seconds"]
            timings.append({"step": len(executed_actions) - 1, "inference_time_sec": inference_time,
                            "new_chunk": prediction["new_chunk"],
                            "env_step_time_sec": env_time, "total_time_sec": inference_time + env_time})
            obs = env.get_obs()
            writer.append_data(frame(obs))
            record["success"] = bool(env.eval_success or env.check_success())
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
                record.update(status="error", video_error=str(exc))
        try:
            env.close_env()
        except Exception as exc:
            record.update(status="error", close_error=str(exc))
        record["elapsed_seconds"] = time.monotonic() - started
        np.savez_compressed(path("_actions.npz"), raw_actions=np.asarray(raw_chunks).reshape(-1, 20, 16),
                            model_actions=np.asarray(model_chunks).reshape(-1, 40, 20),
                            measured_joints=np.asarray(measured_joints).reshape(-1, 14),
                            executed_actions=np.asarray(executed_actions).reshape(-1, 16),
                            measured_poses=np.asarray(measured_poses).reshape(-1, 16))
        write_json(path("_result.json"), record)
        write_json(path("_requests.json"), client.requests if reset_started else [])
        write_episode_artifacts(directory, record, args.task_config, block, timings, raw_chunks)
        print(json.dumps(record, ensure_ascii=False), flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="click_bell")
    parser.add_argument("--task-config", default="demo_clean")
    parser.add_argument("--robotwin-dir", type=Path, default=REPO_ROOT / "third_party/robotwin")
    parser.add_argument("--server-url", default="ws://127.0.0.1:8015")
    parser.add_argument("--request-timeout", type=float, default=600)
    parser.add_argument("--output-dir", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--seeds", type=int, nargs="+")
    selection.add_argument("--seed-manifest", type=Path)
    parser.add_argument("--blocks", type=int)
    parser.add_argument("--instruction-type", choices=("seen", "unseen", "task-name"))
    parser.add_argument("--sim-gpu", default="0")
    args = parser.parse_args()
    if not args.task.isidentifier() or Path(args.task_config).name != args.task_config:
        parser.error("Task and task-config must be simple names")
    if args.task not in IF_SEED_CONTRACTS and args.instruction_type is None:
        args.instruction_type = "unseen"  # Pinned Hy-VLA native evaluation uses generated unseen instructions.
    seeds, manifest, split = select_seeds(args)
    target, output = args.robotwin_dir.resolve(), args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ["CUDA_VISIBLE_DEVICES"] = args.sim_gpu
    os.environ["PYTHONNOUSERSITE"] = "1"
    metadata = {"created_at": datetime.now(timezone.utc).isoformat(), "purpose": "integration_smoke",
                "policy": "hy_vla", "output_format": "cogact_episode_v1",
                "arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                "seeds": seeds, "instruction_type": split,
                "robotwin": git_identity(target), "robotwin_if": git_identity(REPO_ROOT),
                "hy_vla": git_identity(REPO_ROOT / "third_party/hy-vla"),
                "source_sha256": {str(p.relative_to(REPO_ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in [*Path(__file__).parent.glob("*.py"),
                                            REPO_ROOT / "policies/xvla/eval.py", REPO_ROOT / "policies/xvla/outputs.py",
                                            REPO_ROOT / "policies/lingbot_va/client.py"]},
                "task_config_sha256": hashlib.sha256((target / "task_config" / f"{args.task_config}.yml").read_bytes()).hexdigest(),
                "task_source_sha256": hashlib.sha256((target / "envs" / f"{args.task}.py").read_bytes()).hexdigest(),
                "evaluation_source_sha256": hashlib.sha256((REPO_ROOT / "policies/evaluation.py").read_bytes()).hexdigest(),
                "manifest_sha256": manifest_sha256(manifest) if manifest else None}
    write_json(output / "run.json", metadata)
    records, failure = [], None
    print(f"Running {args.task} seeds={seeds}; output={output}", flush=True)
    with (output / "console.log").open("w", buffering=1) as log, redirect_stdout(log), redirect_stderr(log):
        client = None
        try:
            from policies.hy_vla.client import HyVLAClient
            client = HyVLAClient(args.server_url, args.request_timeout)
            metadata["server_metadata"] = client.server_metadata
            write_json(output / "run.json", metadata)
            env, config = load_task(target, args.task, args.task_config)
            config["policy_name"] = "hy_vla"
            write_json(output / "resolved_config.json", config)
            for index, seed in enumerate(seeds):
                block = index // IF_SEED_CONTRACTS[args.task].block_size if manifest else None
                record = run_episode(env, config, client, args, seed, split, output, block)
                records.append(record)
                with (output / "results.jsonl").open("a") as stream:
                    stream.write(json.dumps(record, allow_nan=False) + "\n")
                print(f"seed={seed} status={record['status']}", flush=True)
                if record["status"] == "error":
                    break
        except (Exception, SystemExit) as exc:
            failure = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception as exc:
                    failure = f"Client close failed: {type(exc).__name__}: {exc}"
                    traceback.print_exc()
    complete = len(records) == len(seeds) and all(r["status"] != "error" for r in records) and failure is None
    summary = {"task": args.task, "complete": complete, "expected_episodes": len(seeds),
               "recorded_episodes": len(records), "successes": sum(r["status"] == "success" for r in records),
               "error": failure, "per_mode": {}}
    for mode in sorted({describe_seed(args.task, s).mode for s in seeds}) if manifest else []:
        selected = [r for r in records if r["mode"] == mode]
        summary["per_mode"][mode] = {"successes": sum(r["status"] == "success" for r in selected),
                                     "recorded": len(selected),
                                     "expected": sum(describe_seed(args.task, s).mode == mode for s in seeds)}
    write_json(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)
    return 2 if not complete else (0 if summary["successes"] else 1)


if __name__ == "__main__":
    sys.exit(main())
