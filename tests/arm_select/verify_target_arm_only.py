#!/usr/bin/env python3
"""Real cube-v3 oracle regression: wrong arm, put down, then commanded arm.

Run with the RoboTwin environment and one CUDA_VISIBLE_DEVICES GPU. This is a
diagnostic control, not a policy evaluation. Never overwrite an existing output.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", type=Path, default=Path(
        "/Data/robotwin-if/evaluations/robotwin-if-cube-v3-20blocks-001/xvla/arm_select"))
    args = parser.parse_args()
    output, reference = args.output.resolve(), args.reference.resolve()
    output.mkdir(parents=True, exist_ok=False)

    import imageio.v2 as imageio
    import numpy as np
    from PIL import Image
    from tools.sim_device import pin_renderer
    from policies.xvla.client import CAMERAS, encode_proprio
    from policies.xvla.eval import load_task

    pci = pin_renderer()
    env, config = load_task(ROOT / "third_party/robotwin", "arm_select", "demo_clean_arm_select_v3")
    from envs.utils import ArmTag

    sources = [ROOT / name for name in (
        "tasks/envs/arm_select.py", "tasks/envs/_if_grounding.py",
        "tasks/task_config/demo_clean_arm_select_v3.yml",
        "tests/arm_select/verify_target_arm_only.py")]
    (output / "source").mkdir()
    for path in sources:
        (output / "source" / path.name).write_bytes(path.read_bytes())
    report = dict(diagnostic_only=True, complete=False, all_checks_passed=False,
                  simulator_pci=pci, task_config="demo_clean_arm_select_v3", episodes=[],
                  sources_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sources})
    write(output / "report.json", report)
    for seed in (500000, 500001):
        for wrong_first in (False, True):
            name = f'{seed}-' + ('wrong-then-target' if wrong_first else 'target-only')
            directory = output / name
            directory.mkdir()
            row = dict(seed=seed, wrong_first=wrong_first, passed=False, phases=[])
            trace = []
            video, original_step = None, None
            phase = ["initial"]
            try:
                env.setup_demo(now_ep_num=0, seed=seed, is_test=True, **config)
                obs = env.get_obs()
                initial = dict(proprio=encode_proprio(obs),
                               **{c: obs["observation"][c]["rgb"] for c in CAMERAS})
                np.savez_compressed(directory / "initial.npz", **initial)
                with np.load(reference / f"arm_select_ep{seed}_initial_observation.npz") as prior:
                    row["initial_matches_parent"] = (set(prior.files) == set(initial) and
                        all(np.array_equal(prior[key], initial[key]) for key in prior.files))
                assert row["initial_matches_parent"], "Initial scene changed"
                row["target_arm"] = env.mode
                original_step = env.scene.step
                video = imageio.get_writer(directory / "rollout.mp4", fps=10, codec="libx264")

                def frame():
                    rgb = env.get_obs()["observation"]["head_camera"]["rgb"]
                    video.append_data(rgb)
                    return rgb

                def scene_step():
                    result = original_step()
                    sig = env._pick_monitor.signals()
                    trace.append(dict(phase=phase[0], **sig))
                    if len(trace) % 32 == 0:
                        frame()
                    return result

                env.scene.step = scene_step

                def capture(label):
                    sig = env.eval_signals()
                    row["phases"].append(dict(phase=label, success=bool(env.check_success()),
                                              plan_success=bool(env.plan_success), signals=sig))
                    Image.fromarray(frame()).save(directory / f"{label}.png")
                    write(directory / "phases.json", row["phases"])
                    print(name, label, sig, flush=True)
                    assert env.plan_success, f"Oracle motion failed: {label}"
                    return sig

                capture("initial")
                if wrong_first:
                    phase[0] = "wrong-arm-lift"
                    env.ORACLE_ARM = ArmTag(env.mode).opposite
                    env.play_once()
                    wrong = capture("wrong-arm-lift")
                    assert wrong["lifted"] and wrong["wrong_arm_lifted_ever"]
                    assert not env.check_success()
                    wrong_arm = ArmTag(env.ORACLE_ARM)
                    phase[0] = "put-down-and-retreat"
                    env.move(env.move_by_displacement(wrong_arm, z=-env.LIFT_Z))
                    env.move(env.open_gripper(wrong_arm))
                    env.move(env.move_by_displacement(wrong_arm, z=env.LIFT_Z))
                    env.move(env.back_to_origin(wrong_arm))
                    down = capture("put-down-and-retreat")
                    assert not down["lifted"]
                phase[0] = "target-arm-lift"
                env.ORACLE_ARM = None
                env.play_once()
                final = capture("target-arm-lift")
                row["old_end_state_success"] = bool(final["lifted"] and final["arm_match"])
                row["new_success"] = bool(env.check_success())
                assert row["old_end_state_success"], "Target arm did not complete a real lift"
                assert row["new_success"] == (not wrong_first)
                assert final["wrong_arm_lifted_ever"] == wrong_first
                row["passed"] = True
            except Exception as exc:
                import traceback
                traceback.print_exc()
                row["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                if original_step is not None:
                    env.scene.step = original_step
                if video is not None:
                    video.close()
                env.close_env()
                env.ORACLE_ARM = None
                write(directory / "physics-trace.json", trace)
                write(directory / "result.json", row)
                report["episodes"].append(row)
                write(output / "report.json", report)
    report["complete"] = True
    report["all_checks_passed"] = all(row["passed"] for row in report["episodes"])
    write(output / "report.json", report)
    print("REGRESSION_COMPLETE", report["all_checks_passed"], flush=True)
    return 0 if report["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
