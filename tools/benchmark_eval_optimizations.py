#!/usr/bin/env python3
"""Serial, model-free replay of recorded actions to validate eval optimizations.

All three variants keep every camera observation and video frame. The benchmark
measures simulator/setup savings, not model inference speed or policy rankings.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.sim_device import pin_renderer
CASES = [("lingbot_va", "bottle_verb", 100003),
         ("lingbot_vla", "pick_diverse_object", 100004),
         ("hy_vla", "attribute_select", 100000),
         ("xvla", "arm_select", 100002),
         ("hy_vla", "stack_sequence", 100008),
         ("vlact", "place_relative", 100014),
         ("dm05", "grasp_cube_approach", 100000)]


def summarize(output):
    """Regenerate the human-readable report from completed, compared cases."""
    from policies.evaluation import atomic_json
    path = output / "report.json"
    report = json.loads(path.read_text())
    lines = ["# 渲染同步与 oracle 缓存对照", "",
             f"完成状态：{report['complete']}；已验证任务：{len(report['cases'])}/7。", "",
             "三组使用同一批动作，保留每步观测及视频。EE 组使用同一份参考关节规划，"
             "避免原生规划器重复求解的波动；关节动作直接回放。时间包含 oracle、policy setup、"
             "物理/渲染、取图、视频写入及缓存指纹计算，不含模型推理和 EE 求解。", "",
             "| Task | 动作数 | 原版秒 | 首次缓存秒 | 命中秒 | 命中加速比 |",
             "|---|---:|---:|---:|---:|---:|"]
    totals = {v: 0. for v in ("baseline", "cold", "hit")}
    for row in report["cases"]:
        results = {v: json.loads((output / row["task"] / v / "result.json").read_text()) for v in totals}
        row["identity_seconds"] = {v: results[v]["optimization"]["identity_seconds"] for v in totals}
        row["baseline_success"] = results["baseline"]["success"]
        row["source_success"] = results["baseline"]["source_success"]
        row["source_actions"] = results["baseline"]["source_actions"]
        values = row["seconds"]
        for v in totals:
            totals[v] += values[v]
        lines.append(f"| {row['task']} | {row['actions']} | {values['baseline']:.2f} | {values['cold']:.2f} | "
                     f"{values['hit']:.2f} | {values['baseline']/values['hit']:.2f}× |")
    if totals["hit"]:
        report["total_seconds"] = totals
        report["cache_hit_speedup"] = totals["baseline"] / totals["hit"]
        lines.append(f"| 合计 | {sum(r['actions'] for r in report['cases'])} | {totals['baseline']:.2f} | "
                     f"{totals['cold']:.2f} | {totals['hit']:.2f} | {report['cache_hit_speedup']:.2f}× |")
    lines += ["", "逐步三路 RGB 哈希一致；机器人状态绝对误差不超过 1e-6；成功信号、终止步数、"
              "视频帧数一致。缓存命中组使用不同 policy_name 验证跨 policy 复用。", "",
              "这是固定动作/规划的回放对照，不能直接外推为六个模型完整评测的加速比或新成功率。"
              "历史 EE 动作重新规划时可能与历史结果不同；优化对照使用同一次参考规划。", "",
              "[机器可读报告](report.json) · [GPU 记录](gpu-observations.jsonl)"]
    atomic_json(path, report)
    (output / "report.md").write_text("\n".join(lines) + "\n")


def worker(args):
    import numpy as np
    import imageio.v2 as imageio
    from policies.evaluation import prepare_evaluation, setup_episode, initial_signature, render_counters
    from policies.xvla.eval import load_task
    from policies.xvla.outputs import camera_strip, write_json
    from if_benchmark.seed_contracts import describe_seed

    os.environ["CUDA_VISIBLE_DEVICES"] = args.sim_gpu
    pci = pin_renderer()
    policy, task, seed = args.case.split(":")
    seed = int(seed)
    source = args.suite / policy / task / f"{task}_ep{seed}"
    original = json.loads(Path(str(source) + "_result.json").read_text())
    with np.load(str(source) + "_actions.npz") as trace:
        actions = trace["executed_actions"].copy()
    target = args.output / task / args.variant
    target.mkdir(parents=True, exist_ok=False)
    record = {"mode": describe_seed(task, seed).mode, "oracle_success": False}
    env, config = load_task(ROOT / "third_party/robotwin", task, "demo_clean")
    # Exercise cross-policy sharing: policy_name must not change the cache key.
    config["policy_name"] = policy if args.variant != "hit" else "cache_reuse_check"
    args.task, args.task_config = task, "demo_clean"
    args.robotwin_dir = ROOT / "third_party/robotwin"
    args.render_sync = "legacy" if args.variant in ("reference", "baseline") else "observation"
    args.no_oracle_cache = args.variant in ("reference", "baseline")
    metadata = prepare_evaluation(env, config, args)
    started = time.monotonic()
    poses, joints, frames, signals = [], [], [], []
    action_seconds = observation_seconds = video_seconds = 0.
    action_type = "ee" if policy in ("xvla", "lingbot_va", "hy_vla") else "qpos"
    plans = {}
    planning_seconds = [0.]
    reference = None
    if action_type == "ee" and args.variant != "reference":
        reference_dir = args.output / task / "reference"
        reference = json.loads((reference_dir / "result.json").read_text())
        actions = actions[:reference["actions"]]
        with np.load(reference_dir / "plans.npz") as data:
            plans = {k: data[k].copy() for k in data.files}
    writer = None
    try:
        instruction, obs = setup_episode(env, config, args, seed, original["instruction_type"],
                                         record, lambda suffix: target / ("episode" + suffix))
        assert instruction == original["instruction"]
        with np.load(str(source) + "_initial_observation.npz") as initial:
            for name in ("head_camera", "left_camera", "right_camera"):
                np.testing.assert_array_equal(obs["observation"][name]["rgb"], initial[name])
        initial = initial_signature(obs, env, record["mode"])
        if action_type == "ee":
            for arm in ("left", "right"):
                original_plan = getattr(env.robot, arm + "_plan_path")
                count = [0]
                def plan(pose, _arm=arm, _original=original_plan, _count=count):
                    prefix = f"{_arm}_{_count[0]}_"
                    _count[0] += 1
                    if args.variant == "reference":
                        tick = time.monotonic()
                        result = _original(pose)
                        planning_seconds[0] += time.monotonic() - tick
                        plans[prefix + "target"] = np.asarray(pose).copy()
                        for key in ("status", "position", "velocity"):
                            if key in result:
                                plans[prefix + key] = np.asarray(result[key]).copy()
                        return result
                    np.testing.assert_array_equal(pose, plans[prefix + "target"])
                    return {key: (plans[prefix + key].item() if key == "status" else plans[prefix + key].copy())
                            for key in ("status", "position", "velocity") if prefix + key in plans}
                setattr(env.robot, arm + "_plan_path", plan)
        writer = imageio.get_writer(target / "replay.mp4", fps=10, codec="libx264")

        def capture(obs):
            images = {name: obs["observation"][name]["rgb"] for name in ("head_camera", "left_camera", "right_camera")}
            frames.append({name: hashlib.sha256(rgb.tobytes()).hexdigest() for name, rgb in images.items()})
            started = time.monotonic()
            writer.append_data(camera_strip(images))
            return time.monotonic() - started

        video_seconds += capture(obs)
        for action in actions:
            poses.append(np.concatenate([obs["endpose"][arm + "_endpose"] for arm in ("left", "right")]))
            joints.append(obs["joint_action"]["vector"])
            tick = time.monotonic()
            env.take_action(action, action_type=action_type)
            action_seconds += time.monotonic() - tick
            tick = time.monotonic()
            obs = env.get_obs()
            observation_seconds += time.monotonic() - tick
            video_seconds += capture(obs)
            success = bool(env.eval_success or env.check_success())
            signals.append(env.eval_signals() if hasattr(env, "eval_signals") else {"success": success})
            if success:
                break
        if reference:
            assert len(poses) == reference["actions"] and success == reference["success"]
        np.savez_compressed(target / "plans.npz", **plans)
        record.update(actions=len(poses), success=success,
                      elapsed_seconds=time.monotonic() - started + metadata["identity_seconds"],
                      action_seconds=action_seconds, observation_seconds=observation_seconds,
                      video_seconds=video_seconds, pci=pci, optimization=metadata,
                      initial=initial, frame_hashes=frames, signals=signals, render_sync=render_counters(env),
                      source_actions=original["action_calls"], source_success=original["success"],
                      planning_seconds=planning_seconds[0],
                      planning_mode="recorded_joint_plans" if reference else "native")
        np.savez_compressed(target / "states.npz", poses=poses, joints=joints)
    finally:
        if writer is not None:
            writer.close()
        env.close_env()
    with imageio.get_reader(target / "replay.mp4") as reader:
        record["video_frames"] = reader.count_frames()
    assert record["video_frames"] == record["actions"] + 1
    write_json(target / "result.json", record)
    print("REPLAY COMPLETE", task, args.variant, record["elapsed_seconds"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--oracle-cache-dir", type=Path, required=True)
    parser.add_argument("--sim-gpu", default="0")
    parser.add_argument("--case")
    parser.add_argument("--variant", choices=("reference", "baseline", "cold", "hit"))
    args = parser.parse_args()
    args.suite, args.output, args.oracle_cache_dir = args.suite.resolve(), args.output.resolve(), args.oracle_cache_dir.resolve()
    if args.case:
        worker(args)
        return
    import numpy as np
    from policies.evaluation import atomic_json
    if any((args.oracle_cache_dir / "entries").glob("*.json")):
        parser.error("Use a fresh oracle cache directory to measure cold and hit separately")
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"complete": False, "cases": [], "scope": "same-action replay; EE variants share one recorded joint plan; excludes model inference and EE planning"}
    for policy, task, seed in CASES:
        variants = ("reference", "baseline", "cold", "hit") if policy in ("xvla", "lingbot_va", "hy_vla") else ("baseline", "cold", "hit")
        for variant in variants:
            print("START", task, variant, flush=True)
            command = [sys.executable, "-u", __file__, "--suite", str(args.suite), "--output", str(args.output),
                       "--oracle-cache-dir", str(args.oracle_cache_dir), "--sim-gpu", args.sim_gpu,
                       "--case", f"{policy}:{task}:{seed}", "--variant", variant]
            with (args.output / f"{task}-{variant}.log").open("x") as log:
                subprocess.run(command, cwd=ROOT, check=True, timeout=1800,
                               stdout=log, stderr=subprocess.STDOUT,
                               env=dict(os.environ, PYTHONNOUSERSITE="1", CUDA_VISIBLE_DEVICES=args.sim_gpu))
            gpu = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu", "--format=csv"],
                                 capture_output=True, text=True, check=True, timeout=10)
            with (args.output / "gpu-observations.jsonl").open("a") as log:
                log.write(json.dumps({"task": task, "variant": variant, "output": gpu.stdout}) + "\n")
        results = {v: json.loads((args.output / task / v / "result.json").read_text()) for v in ("baseline", "cold", "hit")}
        for variant in ("cold", "hit"):
            for key in ("actions", "success", "initial", "frame_hashes", "signals", "video_frames"):
                assert results[variant][key] == results["baseline"][key], (task, variant, key)
            with np.load(args.output / task / "baseline/states.npz") as a, np.load(args.output / task / variant / "states.npz") as b:
                for key in a.files:
                    np.testing.assert_allclose(a[key], b[key], rtol=0, atol=1e-6)
        assert results["cold"]["oracle_cache"]["status"] == "miss"
        assert results["hit"]["oracle_cache"]["status"] == "hit"
        report["cases"].append({"task": task, "seed": seed, "source_policy": policy,
                                "actions": results["baseline"]["actions"], "rgb_every_step_identical": True,
                                "states_and_success_match": True,
                                "seconds": {v: results[v]["elapsed_seconds"] for v in results},
                                "identity_seconds": {v: results[v]["optimization"]["identity_seconds"] for v in results},
                                "oracle_seconds": {v: results[v]["oracle_seconds"] for v in results},
                                "action_seconds": {v: results[v]["action_seconds"] for v in results}})
        atomic_json(args.output / "report.json", report)
        print("VERIFIED", task, report["cases"][-1], flush=True)
    report["complete"] = True
    atomic_json(args.output / "report.json", report)
    summarize(args.output)
    print("ALL REPLAYS VERIFIED", flush=True)


if __name__ == "__main__":
    main()
