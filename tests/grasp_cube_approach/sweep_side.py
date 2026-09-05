#!/usr/bin/env python3
"""Side-grasp reachability sweep for grasp_cube_approach (push ~73% -> ~90%).

At the spec's single FIXED pose, the horizontal side grasp fails ~27% of the
time, all `plan=False` (motion planning), stochastic across RRT seeds. This
sweep isolates the lever that matters most: WHICH side face is grasped. It runs
the fixed-pose side grasp forcing each of the four side contacts (ids 4/5/6/7)
individually, plus the default "let choose_grasp_pose pick" (SIDE_FACE=None),
and reports the plan/success rate per config so we can lock the most reliable
face (optionally then sweep pre_grasp/lift on the winner).

Run inside the RoboTwin conda env, after bridging:
    ./bridge_tasks.sh
    conda activate RoboTwin
    python tests/grasp_cube_approach/sweep_side.py [N]
"""
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _parent = os.path.dirname(_REPO)
    if _parent == _REPO:
        raise RuntimeError("could not locate repo root (no third_party/robotwin above this file)")
    _REPO = _parent
_RT = os.path.join(_REPO, "third_party", "robotwin")
os.chdir(_RT)
sys.path.insert(0, os.path.join(_RT, "script"))
sys.path.insert(0, _RT)

import numpy as np  # noqa: E402
import collect_data as cd  # noqa: E402

TASK_NAME = "grasp_cube_approach"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 15
GATE = 0.90

_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run
cd.main(task_name=TASK_NAME, task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0

# Fixed spec pose, side approach.
TASK.POSE_JITTER = False
TASK.APPROACH = "side"
TASK.ORACLE_IDS = None

FACE_NAME = {4: "front", 5: "right", 6: "left", 7: "back", None: "auto(all)"}


def run_config(side_face, n):
    TASK.SIDE_FACE = side_face
    n_ok = n_run = n_plan = 0
    for ep in range(n):
        seed = ep
        last = None
        for _ in range(20):
            try:
                TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
                last = None
                break
            except Exception as e:
                last = e
                seed += n
        if last is not None:
            continue
        try:
            TASK.play_once()
        except Exception:
            n_run += 1
            continue
        n_run += 1
        n_ok += int(bool(TASK.check_success()))
        n_plan += int(getattr(TASK, "plan_success", False) is True)
    rate = n_ok / n_run if n_run else 0.0
    plan_rate = n_plan / n_run if n_run else 0.0
    return rate, plan_rate, n_run


print(f"==== grasp_cube_approach side-face sweep: fixed pose, N={N}, gate {GATE:.0%} ====")
print(f"(arm is chosen by cube x; FIXED_XY={TASK.FIXED_XY})\n")
results = {}
for face in [None, 4, 5, 6, 7]:
    rate, plan_rate, n_run = run_config(face, N)
    results[face] = rate
    mark = "PASS" if rate >= GATE else ""
    print(f"  face={str(face):4} ({FACE_NAME[face]:9})  "
          f"success {rate:5.1%}  plan_ok {plan_rate:5.1%}  (n={n_run})  {mark}")

best = max(results, key=results.get)
print("\n==== summary ====")
print(f"best: face={best} ({FACE_NAME[best]}) at {results[best]:.1%}")
if results[best] >= GATE:
    print(f"-> lock SIDE_FACE={best}; if <95%, sweep PRE_GRASP_DIS/LIFT_Z/FIXED_XY on it next")
else:
    print("-> no single face clears the gate; try shifting FIXED_XY toward the arm "
          "and/or lowering PRE_GRASP_DIS, then re-sweep")
sys.exit(0)
