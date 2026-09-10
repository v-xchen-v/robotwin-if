#!/usr/bin/env python3
"""Serial translation-only grasp probe: paired oracles, repeats, wrong directions.

Uses one simulator and no model servers. A GPU/heartbeat watchdog stops the
worker without retry. Only a fully passing probe exports an evaluation manifest.
Run with the RoboTwin Python environment, after installing the v2 task config.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.probe_arm_select_variation import gpu_sample, sha, write_json

TASK = "grasp_cube_approach"
CONFIG = "demo_clean_grasp_approach_v2"
CAMERAS = ("head_camera", "left_camera", "right_camera")


def worker(args):
    import numpy as np
    from PIL import Image
    from tools.sim_device import pin_renderer
    from policies.xvla.eval import load_task, instruction_for

    def beat(stage, seed=None):
        write_json(args.output / "heartbeat.json", {"time": time.time(), "stage": stage, "seed": seed})

    beat("renderer_init")
    pci = pin_renderer()
    env, config = load_task(args.robotwin_dir, TASK, CONFIG)
    rows = []
    original_move = env.move
    current = [None]
    move_stages = []

    def move(*actions, **kwargs):
        beat("oracle_move_start", current[0])
        result = original_move(*actions, **kwargs)
        move_stages.append({"stage": "grasp" if not move_stages else "lift",
                            "plan_success": bool(env.plan_success),
                            "cube_position": env.cube.get_pose().p.tolist()})
        beat("oracle_move_end", current[0])
        return result

    env.move = move

    def episode(seed, phase, *, version="translate-v2", wrong_direction=False):
        current[0] = seed
        move_stages.clear()
        mode = ("top", "side")[seed % 2]
        row = {"seed": seed, "phase": phase, "mode": mode, "version": version}
        started = time.monotonic()
        beat("setup", seed)
        env.ORACLE_IDS = ([env.SIDE_FACE] if mode == "top" else env.TOP_IDS) if wrong_direction else None
        try:
            env.setup_demo(now_ep_num=0, seed=seed, is_test=True,
                           **dict(config, grasp_approach_scene_version=version))
            assert env.mode == mode
            beat("initial_observation", seed)
            obs = env.get_obs()
            images = {name: obs["observation"][name]["rgb"] for name in CAMERAS}
            row["initial_rgb"] = {name: sha(rgb.tobytes()) for name, rgb in images.items()}
            row["initial_poses"] = {}
            for name in ("cube", "riser"):
                pose = getattr(env, name).get_pose()
                row["initial_poses"][name] = np.concatenate([pose.p, pose.q]).tolist()
            row["scene"] = env.info.get("grasp_approach_scene", {"version": version})
            row["initial_success"] = bool(env.check_success())
            assert not row["initial_success"], "Unmoved scene succeeded"
            np.savez_compressed(args.output / f"{phase}-{seed}-initial.npz", **images,
                                **{f"{k}_pose": v for k, v in row["initial_poses"].items()},
                                joint_state=obs["joint_action"]["vector"])
            Image.fromarray(images["head_camera"]).save(args.output / f"{phase}-{seed}-initial.png")
            if version == "fixed-v1":
                reference = args.reference / f"xvla/{TASK}/{TASK}_ep{seed}_initial_observation.npz"
                with np.load(reference, allow_pickle=False) as old:
                    row["matches_archived_v1"] = all(np.array_equal(images[c], old[c]) for c in CAMERAS)
                assert row["matches_archived_v1"], "Fixed v1 differs from archived RGB"
            beat("oracle", seed)
            info = env.play_once()
            row["move_stages"] = list(move_stages)
            row["plan_success"] = bool(env.plan_success)
            row["success"] = bool(env.check_success())
            row["signals"] = env.eval_signals()
            row["oracle_arm"] = str(env.arm_tag)
            row["instruction"] = instruction_for(TASK, info, "unseen", seed)
            row["oracle_info"] = info
            az = row["signals"]["approach_axis_z"]
            actual_top, actual_side = az >= env.VERT_COS, az <= env.HORIZ_COS
            actual_expected = ((actual_side if mode == "top" else actual_top) if wrong_direction
                               else (actual_top if mode == "top" else actual_side))
            row["actual_direction_expected"] = bool(actual_expected)
            row["passed"] = bool(row["plan_success"] and row["signals"]["lifted"] and actual_expected and
                                 (not row["success"] and not row["signals"]["orientation_match"]
                                  if wrong_direction else row["success"] and row["signals"]["orientation_match"]))
            if version == "translate-v2":
                assert row["oracle_arm"] == info["info"]["{a}"] == "right", "v2 must use right arm"
            beat("final_observation", seed)
            final = env.get_obs()["observation"]["head_camera"]["rgb"]
            Image.fromarray(final).save(args.output / f"{phase}-{seed}-final.png")
        except Exception as exc:
            import traceback
            traceback.print_exc()
            row.update(passed=False, error=f"{type(exc).__name__}: {exc}")
        finally:
            beat("close", seed)
            env.ORACLE_IDS = None
            env.close_env()
        row["elapsed_seconds"] = time.monotonic() - started
        rows.append(row)
        write_json(args.output / "episodes.json", rows)
        print(phase, seed, mode, "PASS" if row["passed"] else "FAIL", row.get("signals"), flush=True)
        beat("episode_complete", seed)
        return row

    def same_scene(a, b):
        rgb = "initial_rgb" in a and a["initial_rgb"] == b.get("initial_rgb")
        poses = all(name in a.get("initial_poses", {}) and name in b.get("initial_poses", {}) and
                    np.allclose(a["initial_poses"][name], b["initial_poses"][name], rtol=0, atol=1e-6)
                    for name in ("cube", "riser"))
        return bool(rgb), bool(poses)

    for seed in (100000, 100001):
        episode(seed, "fixed", version="fixed-v1")
    blocks = []
    for index in range(args.blocks):
        seed = args.seed_start + 2 * index
        a, b = episode(seed, "candidate"), episode(seed + 1, "candidate")
        rgb, poses = same_scene(a, b)
        language = ("instruction" in a and "instruction" in b and
                    "from the top" in a["instruction"] and "from the side" in b["instruction"] and
                    a["instruction"].replace("from the top", "from the DIRECTION") ==
                    b["instruction"].replace("from the side", "from the DIRECTION"))
        blocks.append({"seeds": [seed, seed + 1], "same_rgb": rgb, "same_poses": poses,
                       "same_template": language, "region": a.get("scene", {}).get("region"),
                       "candidate_passed": bool(a["passed"] and b["passed"] and rgb and poses and language)})
        write_json(args.output / "blocks.json", blocks)
    # Predetermined first three blocks cover all three x strata.
    for seed in range(args.seed_start, args.seed_start + 2 * min(3, args.blocks)):
        episode(seed, "repeat")
        episode(seed, "wrong-direction", wrong_direction=True)

    originals = {r["seed"]: r for r in rows if r["phase"] == "candidate"}
    for block in blocks:
        controls = [r for r in rows if r["seed"] in block["seeds"] and
                    r["phase"] in ("repeat", "wrong-direction")]
        block["controls_count"] = len(controls)
        block["controls_passed"] = all(r["passed"] and all(same_scene(r, originals[r["seed"]])) for r in controls)
        block["accepted"] = block["candidate_passed"] and block["controls_passed"]
    signatures = {tuple(r["initial_rgb"][c] for c in CAMERAS) for r in originals.values() if "initial_rgb" in r}
    repeat_identity = all(all(same_scene(r, originals[r["seed"]])) for r in rows
                          if r["phase"] in ("repeat", "wrong-direction"))
    passed = (all(r["passed"] for r in rows) and all(b["accepted"] for b in blocks) and
              len(signatures) == args.blocks and repeat_identity)
    report = {"complete": True, "all_checks_passed": passed, "task": TASK, "task_config": CONFIG,
              "pci": pci, "blocks": blocks, "episodes": rows, "unique_candidate_scenes": len(signatures),
              "repeat_initial_scene_match": repeat_identity, "manifest_exported": passed,
              "note": "Oracle feasibility only, not policy rates. All predetermined failures retained; no replacement seeds."}
    write_json(args.output / "blocks.json", blocks)
    write_json(args.output / "report.json", report)
    # Never silently qualify a failed repeat or export while control checks fail.
    if passed:
        write_json(args.output / f"{TASK}.json", {"schema_version": 1, "task": TASK, "task_config": CONFIG,
                                                "seeds": [s for block in blocks for s in block["seeds"]]})
    beat("complete")
    print("PROBE_COMPLETE", passed, "accepted", sum(b["accepted"] for b in blocks), flush=True)
    return 0 if passed else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blocks", type=int, default=12)
    parser.add_argument("--seed-start", type=int, default=100000)
    parser.add_argument("--robotwin-dir", type=Path, default=ROOT / "third_party/robotwin")
    parser.add_argument("--reference", type=Path, default=ROOT / "outputs/policy-eval/if-seven-tasks-2blocks-001")
    parser.add_argument("--sim-gpu", choices=("0", "1"), default="0")
    parser.add_argument("--memory-limit-mib", type=int, default=40000)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.blocks <= 32 or args.seed_start < 0 or args.seed_start % 2:
        parser.error("Use 1..32 complete blocks and a non-negative even seed-start")
    args.output, args.reference, args.robotwin_dir = args.output.resolve(), args.reference.resolve(), args.robotwin_dir.resolve()
    if args.worker:
        return worker(args)
    config = args.robotwin_dir / "task_config" / f"{CONFIG}.yml"
    if not config.is_file():
        parser.error(f"Install tasks/task_config/{CONFIG}.yml at {config}")
    args.output.mkdir(parents=True, exist_ok=False)
    sources = [ROOT / f"tasks/envs/{TASK}.py", ROOT / "tasks/envs/_if_eval.py",
               ROOT / f"tasks/task_instruction/{TASK}.json",
               ROOT / "policies/xvla/eval.py", config,
               Path(__file__), ROOT / "tools/probe_arm_select_variation.py",
               ROOT / "tools/sim_device.py", args.robotwin_dir / "envs/_base_task.py",
               args.robotwin_dir / "description/utils/generate_episode_instructions.py"]
    shared_evaluation = ROOT / "policies/evaluation.py"
    if shared_evaluation.is_file():
        sources.append(shared_evaluation)
    for path in sources:
        dest = args.output / "source" / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())
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
                if time.time() - last > 180 or time.time() - started > 1800:
                    raise TimeoutError("Worker heartbeat or total timeout; stop without retry")
        except BaseException as exc:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
            write_json(args.output / "supervisor.json", {"complete": False, "error": str(exc)})
            raise
    gpu_sample(args)
    write_json(args.output / "supervisor.json", {"complete": True, "exit_code": process.returncode,
               "elapsed_seconds": time.time() - started})
    print("Probe exited", process.returncode, args.output, flush=True)
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
