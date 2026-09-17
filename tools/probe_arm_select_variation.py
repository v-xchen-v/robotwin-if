#!/usr/bin/env python3
"""Bounded serial oracle probe for arm_select v2 / cube-v3 with paired controls.

Run with the RoboTwin Python environment. One worker uses one simulator on GPU
0; no model servers. The supervisor stops on GPU-query failure, heartbeat stall,
memory limit, or total timeout, without automatic retries.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CONFIGS = {"jitter-v2": "demo_clean_arm_select_v2", "cube-v3": "demo_clean_arm_select_v3"}
CAMERAS = ("head_camera", "left_camera", "right_camera")


def write_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def worker(args):
    import numpy as np
    from PIL import Image
    from tools.sim_device import pin_renderer
    from policies.xvla.eval import load_task, instruction_for

    def beat(stage, seed=None):
        write_json(args.output / "heartbeat.json", {"time": time.time(), "stage": stage, "seed": seed})

    beat("renderer_init")
    pci = pin_renderer()
    task_config = CONFIGS[args.scene_version]
    env, config = load_task(args.robotwin_dir, "arm_select", task_config)
    rows = []
    original_move = env.move

    def move(*actions, **kwargs):
        beat("oracle_move_start", current[0])
        result = original_move(*actions, **kwargs)
        beat("oracle_move_end", current[0])
        return result

    current = [None]
    env.move = move

    def episode(seed, phase, *, version=None, wrong_arm=False, pose_override=None):
        version = version or args.scene_version
        current[0] = seed
        mode = ("left", "right")[seed % 2]
        row = {"seed": seed, "phase": phase, "mode": mode, "version": version}
        started = time.monotonic()
        beat("setup", seed)
        env.ORACLE_ARM = ("right" if mode == "left" else "left") if wrong_arm else None
        original_sampler = env.scene_pose
        if pose_override is not None:
            env.scene_pose = lambda scene_seed, version: (*pose_override, "boundary")
            row["pose_override"] = list(pose_override)
        try:
            cfg = dict(config, arm_select_scene_version=version)
            env.setup_demo(now_ep_num=0, seed=seed, is_test=True, **cfg)
            assert env.mode == mode
            beat("initial_observation", seed)
            obs = env.get_obs()
            images = {name: obs["observation"][name]["rgb"] for name in CAMERAS}
            row["initial_rgb"] = {name: sha(rgb.tobytes()) for name, rgb in images.items()}
            pose = env.box.get_pose()
            row["initial_pose"] = np.concatenate([pose.p, pose.q]).tolist()
            row["scene"] = env.info["arm_select_scene"]
            row["initial_success"] = bool(env.check_success())
            assert not row["initial_success"]
            np.savez_compressed(args.output / f"{phase}-{seed}-initial.npz", **images,
                                box_pose=row["initial_pose"], joint_state=obs["joint_action"]["vector"])
            Image.fromarray(images["head_camera"]).save(args.output / f"{phase}-{seed}-initial.png")
            if version == "fixed-v1":
                reference = args.reference / "xvla/arm_select" / f"arm_select_ep{seed}_initial_observation.npz"
                with np.load(reference, allow_pickle=False) as old:
                    row["matches_archived_v1"] = all(np.array_equal(images[c], old[c]) for c in CAMERAS)
                assert row["matches_archived_v1"]
            beat("oracle", seed)
            info = env.play_once()
            row["plan_success"] = bool(env.plan_success)
            row["success"] = bool(env.check_success())
            row["signals"] = env.eval_signals()
            row["instruction"] = instruction_for("arm_select", info, "unseen", seed)
            row["passed"] = bool(row["plan_success"] and row["signals"]["lifted"] and
                                 (not row["success"] if wrong_arm else row["success"]))
            row["oracle_info"] = info
            beat("final_observation", seed)
            final = env.get_obs()["observation"]["head_camera"]["rgb"]
            Image.fromarray(final).save(args.output / f"{phase}-{seed}-final.png")
        except Exception as exc:
            import traceback
            traceback.print_exc()
            row.update(passed=False, error=f"{type(exc).__name__}: {exc}")
        finally:
            beat("close", seed)
            env.close_env()
            env.ORACLE_ARM = None
            env.scene_pose = original_sampler
        row["elapsed_seconds"] = time.monotonic() - started
        rows.append(row)
        write_json(args.output / "episodes.json", rows)
        print(phase, seed, mode, "PASS" if row["passed"] else "FAIL", row.get("signals"), flush=True)
        beat("episode_complete", seed)
        return row

    # Historical fixed scenes remain a pixel-identical regression control.
    for seed in (100000, 100001):
        episode(seed, "fixed", version="fixed-v1")
    blocks = []
    for index in range(args.blocks):
        seed = args.seed_start + 2*index
        a, b = episode(seed, "candidate"), episode(seed+1, "candidate")
        same_rgb = a.get("initial_rgb") is not None and a.get("initial_rgb") == b.get("initial_rgb")
        same_pose = "initial_pose" in a and "initial_pose" in b and np.allclose(a["initial_pose"], b["initial_pose"], rtol=0, atol=1e-6)
        same_language = ("instruction" in a and "instruction" in b and
                        a["instruction"].replace("the left arm", "the ARM arm") ==
                        b["instruction"].replace("the right arm", "the ARM arm"))
        blocks.append({"seeds": [seed, seed+1], "same_rgb": same_rgb, "same_pose": bool(same_pose),
                       "same_template": same_language, "region": a.get("scene", {}).get("region"),
                       "accepted": bool(a["passed"] and b["passed"] and same_rgb and same_pose and same_language)})
        write_json(args.output / "blocks.json", blocks)
    # Preselected first three blocks: one per x stratum, both commanded arms.
    for seed in range(args.seed_start, args.seed_start + 2*min(3, args.blocks)):
        episode(seed, "repeat")
        episode(seed, "wrong-arm", wrong_arm=True)
    if args.check_boundaries:
        from itertools import product
        # Exercise every xy corner at both yaw extremes and zero yaw, plus
        # the center. These are explicit controls, never manifest candidates.
        xs = (env.CUBE_X_BINS[0][0], env.CUBE_X_BINS[-1][1])
        ys = env.CUBE_Y_RANGE
        yaws = (-env.CUBE_YAW_LIMIT, 0.0, env.CUBE_YAW_LIMIT)
        poses = [*product(xs, ys, yaws), (0.0, sum(ys)/2, 0.0)]
        for index, pose in enumerate(poses):
            for seed in (args.seed_start, args.seed_start+1):
                episode(seed, f"boundary-{index:02d}", pose_override=pose)
    accepted = [s for block in blocks if block["accepted"] for s in block["seeds"]]
    signatures = {tuple(row["initial_rgb"][c] for c in CAMERAS) for row in rows
                  if row["phase"] == "candidate" and "initial_rgb" in row}
    # Repeated setups must reproduce the recorded candidate's observation.
    originals = {r["seed"]: r for r in rows if r["phase"] == "candidate"}
    repeat_identity = all(r.get("initial_rgb") == originals[r["seed"]].get("initial_rgb")
                          for r in rows if r["phase"] in ("repeat", "wrong-arm"))
    report = {"complete": True, "all_checks_passed": all(r["passed"] for r in rows) and
              all(b["accepted"] for b in blocks) and len(signatures) == args.blocks and repeat_identity,
              "task": "arm_select", "task_config": task_config, "pci": pci,
              "blocks": blocks, "episodes": rows, "unique_candidate_scenes": len(signatures),
              "repeat_initial_rgb_match": repeat_identity,
              "boundary_episodes": sum(r["phase"].startswith("boundary-") for r in rows),
              "note": "Small oracle feasibility probe, not policy success rates; all candidate failures retained."}
    write_json(args.output / "report.json", report)
    # A failed repeat or negative control must not produce a qualified manifest.
    if report["all_checks_passed"]:
        write_json(args.output / "arm_select.json", {"schema_version": 1, "task": "arm_select",
                                                    "task_config": task_config, "seeds": accepted})
    beat("complete")
    print("PROBE_COMPLETE", report["all_checks_passed"], "accepted", len(accepted)//2, flush=True)
    return 0 if report["all_checks_passed"] else 2


def gpu_sample(args):
    query = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.total,utilization.gpu",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True, timeout=8)
    rows = [[int(v.strip()) for v in line.split(",")] for line in query.stdout.strip().splitlines()]
    with (args.output / "gpu-observations.jsonl").open("a") as log:
        log.write(json.dumps({"time": time.time(), "gpus": rows}) + "\n")
    assert any(row[0] == int(args.sim_gpu) for row in rows), "GPU not found"
    assert all(row[1] < args.memory_limit_mib for row in rows if row[0] == int(args.sim_gpu)), "GPU memory limit"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blocks", type=int, default=12)
    parser.add_argument("--seed-start", type=int, default=100000)
    parser.add_argument("--scene-version", choices=tuple(CONFIGS), default="jitter-v2")
    parser.add_argument("--check-boundaries", action="store_true",
                        help="Also check cube-v3 xy corners at extreme/zero yaw, and center, with both arms")
    parser.add_argument("--robotwin-dir", type=Path, default=ROOT / "third_party/robotwin")
    parser.add_argument("--reference", type=Path, default=ROOT / "outputs/policy-eval/if-seven-tasks-2blocks-001")
    parser.add_argument("--sim-gpu", choices=("0", "1"), default="0")
    parser.add_argument("--memory-limit-mib", type=int, default=40000)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.blocks <= 32 or args.seed_start < 0 or args.seed_start % 2:
        parser.error("Use 1..32 complete blocks and a non-negative even seed-start")
    if args.check_boundaries and args.scene_version != "cube-v3":
        parser.error("--check-boundaries requires --scene-version cube-v3")
    args.output, args.reference, args.robotwin_dir = args.output.resolve(), args.reference.resolve(), args.robotwin_dir.resolve()
    if args.worker:
        return worker(args)
    task_config = CONFIGS[args.scene_version]
    config = args.robotwin_dir / "task_config" / f"{task_config}.yml"
    if not config.is_file():
        parser.error(f"Install tasks/task_config/{task_config}.yml at {config}")
    args.output.mkdir(parents=True, exist_ok=False)
    sources = [ROOT / "tasks/envs/arm_select.py", ROOT / "policies/xvla/eval.py", config, Path(__file__)]
    snapshot = args.output / "source"
    snapshot.mkdir()
    for source in sources:
        (snapshot / source.name).write_bytes(source.read_bytes())
    write_json(args.output / "provenance.json", {"argv": sys.argv, "python": sys.executable,
               "sources": {str(p): sha(p.read_bytes()) for p in sources}, "simulators": 1, "model_servers": 0})
    gpu_sample(args)
    command = [sys.executable, "-u", str(Path(__file__).resolve()), *sys.argv[1:], "--worker"]
    with (args.output / "worker.log").open("x") as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   env=dict(os.environ, CUDA_VISIBLE_DEVICES=args.sim_gpu, PYTHONNOUSERSITE="1"),
                                   start_new_session=True)
        started = time.time()
        try:
            while process.poll() is None:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
                if process.poll() is not None:
                    break
                gpu_sample(args)
                heartbeat = args.output / "heartbeat.json"
                last = json.loads(heartbeat.read_text())["time"] if heartbeat.exists() else started
                if time.time()-last > 180 or time.time()-started > 1800:
                    raise TimeoutError("Oracle worker heartbeat or total timeout; stop without retry")
        except BaseException as exc:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
            write_json(args.output / "supervisor.json", {"complete": False, "error": str(exc)})
            raise
    gpu_sample(args)
    write_json(args.output / "supervisor.json", {"complete": True, "exit_code": process.returncode,
               "elapsed_seconds": time.time()-started})
    print("Probe exited", process.returncode, args.output, flush=True)
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
