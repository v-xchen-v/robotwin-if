#!/usr/bin/env python3
"""Run paired oracle checks, optionally followed by an open-source policy experiment.

No task bridge or maintained-suite registration is needed. This process adds the
local experimental modules to RoboTwin's env package search path only.
"""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import traceback


ROOT = Path(__file__).resolve().parents[1]
TASK = "press_lift_bell"
sys.path.insert(0, str(ROOT))
POLICIES = {
    "xvla": ("XVLAClient", "http://127.0.0.1:8010", "2toINF/X-VLA-RoboTwin2"),
    "lingbot_va": ("LingBotClient", "ws://127.0.0.1:8011", "robbyant/lingbot-va-posttrain-robotwin"),
    "lingbot_vla": ("LingBotVLAClient", "ws://127.0.0.1:8012", "robbyant/lingbot-vla-4b-posttrain-robotwin"),
    "vlact": ("VLActClient", "ws://127.0.0.1:8013", "StarVLA/VLAct_Qwen3OFT_Robotwin_all_Finetune"),
    "dm05": ("DM05Client", "http://127.0.0.1:8014", "Dexmal/DM05-robotwin2"),
    "hy_vla": ("HyVLAClient", "ws://127.0.0.1:8015", "tencent/Hy-Embodied-0.5-VLA-RoboTwin"),
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def pair_seeds(start_pair, pairs):
    if start_pair < 0 or pairs < 1 or 2 * (start_pair + pairs) > 2**32:
        raise ValueError("provide a nonnegative start pair and a positive uint32-range pair count")
    return list(range(2 * start_pair, 2 * (start_pair + pairs)))


def selected_seeds(start_pair, pairs, scene_seeds):
    if scene_seeds is None:
        return pair_seeds(start_pair, 4 if pairs is None else pairs)
    if start_pair != 0 or pairs is not None or not scene_seeds or len(set(scene_seeds)) != len(scene_seeds):
        raise ValueError("provide distinct scene seeds, without --start-pair or --pairs/--blocks")
    return [seed for scene in scene_seeds for seed in pair_seeds(scene, 1)]


def make_policy_client(policy, server_url, timeout):
    module = importlib.import_module(f"policies.{policy}.client")
    return getattr(module, POLICIES[policy][0])(server_url, timeout)


def check_policy_observation(oracle_dir, seed, instruction, obs, env, task_name=TASK):
    """Compare canonical RGB/state before the first policy request or action."""
    import numpy as np
    from policies.xvla.client import CAMERAS, encode_proprio
    from tasks.envs._press_lift_bell import mode_for_seed
    instructions = importlib.import_module(f"tasks.envs._{task_name}").INSTRUCTIONS

    if instruction != instructions[mode_for_seed(seed)] or env.step_lim != env.ACTION_LIMIT:
        raise RuntimeError("Policy instruction or action budget differs from the experiment")
    with np.load(oracle_dir / f"{task_name}_ep{seed}_initial.npz") as expected:
        for camera in CAMERAS:
            np.testing.assert_array_equal(obs["observation"][camera]["rgb"], expected[camera])
        np.testing.assert_array_equal(encode_proprio(obs), expected["proprio"])


def summarize_pairs(records):
    from tasks.envs._press_lift_bell import MODES

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


def qualify(env, config, seeds, directory, video, task_name=TASK):
    import imageio.v2 as imageio
    import numpy as np
    from policies.xvla.client import CAMERAS, encode_proprio
    from policies.xvla.outputs import camera_strip
    from tasks.envs._press_lift_bell import mode_for_seed

    directory.mkdir()
    records, observations, pairs = [], {}, []
    for seed in seeds:
        record = dict(seed=seed, mode=mode_for_seed(seed), success=False, status="error")
        prefix = directory / f"{task_name}_ep{seed}"
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


def main(argv=None, *, task_name=TASK, canonical_output=False):
    if task_name not in (TASK, "press_lift_stapler"):
        raise ValueError(f"Unsupported press/lift pilot: {task_name}")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robotwin-dir", type=Path, default=ROOT / "third_party/robotwin")
    parser.add_argument("--task-config", default="demo_clean")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--pairs", "--blocks", type=int, help="Number of consecutive scene pairs (default: 4)")
    selection.add_argument("--scene-seeds", type=int, nargs="+", help="Explicit scene IDs, always running both modes")
    parser.add_argument("--start-pair", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sim-gpu", default="0")
    parser.add_argument("--scene-layout", choices=("context", "bare"), default="context",
                        help="Target with mouse/toycar context, or the single-object baseline")
    parser.add_argument("--no-video", action="store_true", help="Skip oracle video; keep images and traces")
    parser.add_argument("--policy", choices=("oracle", *POLICIES), default="oracle")
    parser.add_argument("--server-url", help="Defaults to the selected policy's local endpoint")
    parser.add_argument("--request-timeout", type=float, default=600)
    parser.add_argument("--checkpoint", help="Declared server checkpoint; server metadata is recorded when available")
    args = parser.parse_args(argv)
    try:
        seeds = selected_seeds(args.start_pair, args.pairs, args.scene_seeds)
    except ValueError as exc:
        parser.error(str(exc))
    if Path(args.task_config).name != args.task_config:
        parser.error("task config must be a simple name")
    if args.request_timeout <= 0:
        parser.error("request timeout must be positive")
    if args.policy != "oracle":
        args.server_url = args.server_url or POLICIES[args.policy][1]
        args.checkpoint = args.checkpoint or POLICIES[args.policy][2]
    target, output = args.robotwin_dir.resolve(), args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ["CUDA_VISIBLE_DEVICES"] = args.sim_gpu
    os.environ["PYTHONNOUSERSITE"] = "1"
    os.chdir(target)
    sys.path.insert(0, str(target))
    import envs
    envs.__path__.append(str(ROOT / "tasks/envs"))
    from tools.sim_device import pin_renderer
    pin_renderer()
    from policies.xvla.eval import git_identity, load_task

    source_files = (f"tasks/envs/{task_name}.py", f"tasks/envs/_{task_name}.py",
                    f"tasks/task_instruction/{task_name}.json", "tools/press_lift_bell.py",
                    "policies/evaluation.py", "policies/xvla/eval.py")
    source_files = set(source_files) | {"tools/sim_device.py", "policies/xvla/client.py", "policies/xvla/outputs.py",
                                       "tasks/envs/_press_lift_bell.py"}
    if task_name != TASK:
        source_files.add(f"tools/{task_name}.py")
    if args.policy != "oracle":
        source_files.update(str(p.relative_to(ROOT)) for p in (ROOT / "policies" / args.policy).glob("*.py"))
    metadata = dict(
        created_at=datetime.now(timezone.utc).isoformat(), purpose=f"experimental-{task_name.replace('_', '-')}",
        task=task_name, policy=args.policy, seeds=seeds, checkpoint=args.checkpoint if args.policy != "oracle" else None,
        server_url=args.server_url if args.policy != "oracle" else None,
        robotwin=git_identity(target), robotwin_if=git_identity(ROOT),
        arguments={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sorted(source_files)},
        task_config_sha256=hashlib.sha256((target / "task_config" / f"{args.task_config}.yml").read_bytes()).hexdigest())
    write_json(output / "run.json", metadata)
    for name in source_files:
        snapshot = output / "source-snapshot" / name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes((ROOT / name).read_bytes())
    env, config = load_task(target, task_name, args.task_config)
    # The pilot deliberately fixes clean conditions; record the effective config.
    config["domain_randomization"] = dict(config["domain_randomization"], random_background=False,
        cluttered_table=False, random_head_camera_dis=0, random_table_height=0,
        random_light=False, crazy_random_light_rate=0)
    config["save_freq"] = None
    config["policy_name"] = args.policy
    config[f"{task_name.removeprefix('press_lift_')}_scene_layout"] = args.scene_layout
    write_json(output / "resolved_config.json", config)
    qualification = qualify(env, config, seeds, output / "oracle", not args.no_video, task_name)
    if not qualification["qualified"] or args.policy == "oracle":
        summary = {key: qualification[key] for key in ("qualified", "episodes", "per_mode", "pairs", "both_success")}
        write_json(output / "summary.json", summary)
        print(json.dumps(summary), flush=True)
        return 0 if qualification["qualified"] else 2

    module = importlib.import_module(f"policies.{args.policy}.eval")
    records = []
    args.task = task_name
    client, error = None, None
    original_setup = module.setup_episode
    policy_trace = None

    def checked_setup(env, config, args, seed, split, record, path):
        instruction, obs = original_setup(env, config, args, seed, split, record, path)
        check_policy_observation(output / "oracle", seed, instruction, obs, env, task_name)
        write_json(path("_scene_check.json"), dict(seed=seed, exact_rgb=True, exact_proprio=True,
                   instruction=instruction, action_limit=env.step_lim))
        def observe(task):
            policy_trace.write(json.dumps(task.eval_signals(), allow_nan=False) + "\n")
        env.trace_callback = observe
        return instruction, obs

    try:
        client = make_policy_client(args.policy, args.server_url, args.request_timeout)
        metadata["server_metadata"] = getattr(client, "server_metadata", None)
        write_json(output / "run.json", metadata)
        module.setup_episode = checked_setup
        for index, seed in enumerate(seeds):
            run_dir = output / args.policy
            if canonical_output:
                run_dir = run_dir / task_name
            trace_dir = run_dir / "physics"
            trace_dir.mkdir(parents=True, exist_ok=True)
            with (trace_dir / f"{task_name}_ep{seed}.jsonl").open("x") as policy_trace:
                record = module.run_episode(env, config, client, args, seed, "unseen", run_dir, block=index // 2)
            records.append(record)
            with (output / "results.jsonl").open("a") as stream:
                stream.write(json.dumps(record, allow_nan=False) + "\n")
            print(f"policy seed={seed} status={record['status']}", flush=True)
            if record["status"] == "error":
                break
    except (Exception, SystemExit) as exc:
        error = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    finally:
        module.setup_episode = original_setup
        if client is not None:
            try:
                client.close()
            except Exception as exc:
                error = f"Client close failed: {type(exc).__name__}: {exc}"
    summary = dict(summarize_pairs(records),
                   complete=len(records) == len(seeds) and all(r["status"] != "error" for r in records) and error is None,
                   expected_episodes=len(seeds), oracle_qualified=True, policy=args.policy, error=error)
    write_json(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)
    return 0 if summary["complete"] else 2


if __name__ == "__main__":
    sys.exit(main())
