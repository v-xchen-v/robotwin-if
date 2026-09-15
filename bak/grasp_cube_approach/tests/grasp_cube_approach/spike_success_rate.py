#!/usr/bin/env python3
"""Oracle spike for IF-Grasp-Approach (grasp_cube_approach): top vs side approach.

Before committing to the cube-on-riser design (mitigation C), confirm the risky
*side* grasp reaches the lift band at ~90% while keeping the gripper horizontal.
Top grasp is trivial and only sanity-checked. A counter-example phase runs the
side instruction but grasps with the TOP contact group -- the orientation check
must REJECT it (lifting with the wrong approach is not success).

Runs setup_demo + play_once + check_success over N seeds per phase and reports,
per episode, the cube rise and the gripper approach-axis world-z (|z|~1 vertical,
|z|~0 horizontal), so a failure reads as "stalled / wrong orientation" not a bare
rate.

Run inside the RoboTwin conda env, after bridging the env into the submodule:
    ./bridge_tasks.sh
    conda activate RoboTwin
    python tests/grasp_cube_approach/spike_success_rate.py [N]

Exit code is non-zero if the side-grasp rate is below the ~90% gate or the
counter-example is not reliably rejected.
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
import collect_data as cd  # noqa: E402  (RoboTwin's collector; reused for arg construction)

TASK_NAME = "grasp_cube_approach"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
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


def run_phase(label, approach, oracle_ids, expect_success):
    """Run N episodes; return success rate. expect_success=False for the
    counter-example phase (we want it rejected)."""
    TASK.APPROACH = approach
    TASK.ORACLE_IDS = oracle_ids
    # GRASP_CUBE_FIXED=1 tests the spec's single fixed pose (jitter off).
    TASK.POSE_JITTER = os.environ.get("GRASP_CUBE_FIXED", "0") != "1"
    n_ok = 0
    n_run = 0
    print(f"\n== phase '{label}': approach={approach} "
          f"oracle_ids={oracle_ids or 'match'}  {N} episodes ==")
    for ep in range(N):
        seed = ep
        last = None
        for _ in range(20):
            try:
                TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
                last = None
                break
            except Exception as e:
                last = e
                seed += N
        if last is not None:
            print(f"[ep {ep:02d}] SKIP: no stable scene ({last})")
            continue

        z0 = float(TASK.cube.get_pose().p[2])
        try:
            TASK.play_once()
        except Exception as e:
            print(f"[ep {ep:02d}] ERROR phase-crash: {e}")
            n_run += 1
            continue
        rise = float(TASK.cube.get_pose().p[2]) - z0
        az = abs(TASK._approach_axis_z)
        ok = bool(TASK.check_success())
        plan = getattr(TASK, "plan_success", "?")
        n_run += 1
        n_ok += int(ok)
        orient = "vert" if az >= TASK.VERT_COS else ("horiz" if az <= TASK.HORIZ_COS else "mid ")
        print(f"[ep {ep:02d}] {'OK ' if ok else 'FAIL'} "
              f"rise {rise:+.3f}m  approach|z|={az:.2f} ({orient})  plan={plan}")

    rate = n_ok / n_run if n_run else 0.0
    print(f"  -> {n_ok}/{n_run} success ({rate:.1%})")
    return rate, n_run


print(f"==== grasp_cube_approach spike: N={N}, gate {GATE:.0%} ====")
side_rate, _ = run_phase("side (RISK)", "side", None, expect_success=True)
top_rate, _ = run_phase("top (sanity)", "top", None, expect_success=True)
# Counter-example: commanded side, but grasp with the top group -> horizontal
# check must reject even though the cube lifts.
ce_rate, _ = run_phase("counter-example", "side", TASK.TOP_IDS, expect_success=False)

print("\n==== summary ====")
print(f"side grasp   : {side_rate:.1%}   gate {GATE:.0%}   {'PASS' if side_rate >= GATE else 'BELOW GATE'}")
print(f"top grasp    : {top_rate:.1%}   (sanity)")
print(f"counter-ex.  : {ce_rate:.1%}   want <=10%   {'PASS' if ce_rate <= 0.10 else 'LEAK'}")

side_pass = side_rate >= GATE
ce_pass = ce_rate <= 0.10
if side_pass and ce_pass:
    print("\nPASS -> cube-on-riser side grasp is viable; lock approach C geometry")
else:
    print("\nBELOW GATE -> raise RISER_HALF[2] / shrink cube / adjust side contacts and re-run")
sys.exit(0 if (side_pass and ce_pass) else 1)
