#!/usr/bin/env python3
"""Fixed cross-arm physical gate for the upright Apple top-down grasp.

The scene seeds were frozen from setup-only coverage inspection before observing any
of their grasp outcomes. Failures are not retried with replacement seeds.
"""
import os
import sys
from types import MethodType

import transforms3d as t3d

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RT = os.path.join(REPO, "third_party", "robotwin")
os.chdir(RT)
sys.path[:0] = [os.path.join(RT, "script"), RT]

import collect_data as cd  # noqa: E402


SCENES = (
    ("left", 42000),
    ("left", 42002),
    ("left", 42004),
    ("left", 42006),
    ("left", 42009),
    ("left", 42016),
    ("right", 42100),
    ("right", 42102),
    ("right", 42104),
    ("right", 42111),
    ("right", 42112),
    ("right", 42119),
)
MIN_SUCCESSES_PER_ARM = 5
MIN_VERTICAL_AXIS = 0.90
OVERRIDES = (
    "FAMILIARITY_OVERRIDE",
    "TARGET_NOUN_OVERRIDE",
    "TARGET_MODEL_ID_OVERRIDE",
    "TARGET_SIDE_OVERRIDE",
    "POOL_OVERRIDE",
    "DISTRACTOR_NOUNS_OVERRIDE",
)

capture = {}
cd.run = lambda task, args: capture.update(task=task, args=args)
cd.main(task_name="pick_diverse_object", task_config="demo_clean")
TASK = capture["task"]
ARGS = dict(capture["args"])
ARGS["render_freq"] = 0


def production_radius_first_indices(self, variants, pool, rng):
    """Keep the frozen gate's production placement without a runtime override hook."""
    self.placement_policy = "radius-first"
    tie_breakers = rng.random(len(variants))
    return sorted(
        range(len(variants)),
        key=lambda i: (-pool[variants[i][0]]["placement_radius"], tie_breakers[i]),
    )


TASK._placement_indices = MethodType(production_radius_first_indices, TASK)


def clear_overrides():
    for name in OVERRIDES:
        setattr(TASK, name, None)


def configure(side):
    clear_overrides()
    TASK.FAMILIARITY_OVERRIDE = "unseen"
    TASK.TARGET_NOUN_OVERRIDE = "apple"
    TASK.TARGET_MODEL_ID_OVERRIDE = 1
    TASK.TARGET_SIDE_OVERRIDE = side
    TASK.DISTRACTOR_NOUNS_OVERRIDE = (
        "dumbbell", "wooden mallet", "paintbrush",
    )


rows = []
for requested_side, seed in SCENES:
    configure(requested_side)
    row = {
        "requested_side": requested_side,
        "actual_side": None,
        "seed": seed,
        "setup": False,
        "plan": None,
        "xyz": None,
        "yaw": None,
        "approach_axis_z": None,
        "z_rise": None,
        "held": False,
        "success": False,
        "failure_stage": None,
        "exception": None,
    }
    try:
        TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
        row["setup"] = True
        initial_pose = TASK.target.get_pose()
        row["xyz"] = tuple(round(float(value), 5) for value in initial_pose.p)
        row["yaw"] = round(float(t3d.euler.quat2euler(initial_pose.q)[2]), 4)
        row["actual_side"] = "right" if initial_pose.p[0] > 0 else "left"

        TASK.play_once()
        row["plan"] = bool(TASK.plan_success)
        row["approach_axis_z"] = TASK._approach_axis_z
        row["z_rise"] = float(TASK.target.get_pose().p[2] - TASK.target_origin_z)
        row["held"] = bool(TASK.check_success())
        vertical = (
            row["approach_axis_z"] is not None
            and abs(row["approach_axis_z"]) >= MIN_VERTICAL_AXIS
        )
        row["success"] = bool(
            row["actual_side"] == requested_side
            and row["plan"]
            and vertical
            and row["held"]
        )
        if row["actual_side"] != requested_side:
            row["failure_stage"] = "side"
        elif not row["plan"]:
            row["failure_stage"] = "plan"
        elif not vertical:
            row["failure_stage"] = "orientation"
        elif not row["held"]:
            row["failure_stage"] = "lift-and-held"
    except Exception as exc:
        row["plan"] = bool(getattr(TASK, "plan_success", False))
        if row["setup"]:
            row["z_rise"] = float(TASK.target.get_pose().p[2] - TASK.target_origin_z)
        row["failure_stage"] = "execution" if row["setup"] else "setup"
        row["exception"] = f"{type(exc).__name__}: {exc}"
    rows.append(row)
    print(
        f"[{'PASS' if row['success'] else 'FAIL'}] "
        f"side={requested_side} seed={seed} xyz={row['xyz']} yaw={row['yaw']} "
        f"plan={row['plan']} axis_z={row['approach_axis_z']} "
        f"z_rise={row['z_rise']} held={row['held']} "
        f"stage={row['failure_stage']} exception={row['exception']}"
    )

clear_overrides()
all_ok = True
for side in ("left", "right"):
    arm_rows = [row for row in rows if row["requested_side"] == side]
    successes = sum(row["success"] for row in arm_rows)
    arm_ok = successes >= MIN_SUCCESSES_PER_ARM
    all_ok &= arm_ok
    print(
        f"[{'PASS' if arm_ok else 'FAIL'}] {side} arm gate: "
        f"{successes}/{len(arm_rows)} >= {MIN_SUCCESSES_PER_ARM}/{len(arm_rows)}"
    )

successful_rows = [row for row in rows if row["success"]]
orientation_ok = bool(successful_rows) and all(
    abs(row["approach_axis_z"]) >= MIN_VERTICAL_AXIS
    for row in successful_rows
)
all_ok &= orientation_ok
print(
    f"[{'PASS' if orientation_ok else 'FAIL'}] successful grasps are top-down: "
    f"{len(successful_rows)}/{len(rows)} satisfy |axis_z| >= {MIN_VERTICAL_AXIS}"
)
print(f"\n==== {'PASS' if all_ok else 'FAIL'}: {len(successful_rows)}/{len(rows)} scenes ====")
sys.exit(0 if all_ok else 1)
