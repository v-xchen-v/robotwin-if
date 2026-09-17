#!/usr/bin/env python3
"""Oracle spike for IF-Arm-Select (arm_select): grasp a center box with the
COMMANDED arm (left vs right).

The box is pinned at x=0 (the arm-choice decision boundary), so the only design
risk is whether BOTH arms independently reach the center box at ~90%. This runs
the left-arm and right-arm oracles over N seeds each and reports, per episode,
the box rise and the box->commanded-TCP distance, so a failure reads as
"stalled / wrong arm" not a bare rate.

A counter-example phase commands one arm but executes with the OTHER arm
(ORACLE_ARM); arm_match must REJECT it even though the box lifts (lifting with
the wrong arm is not success).

Run inside the RoboTwin conda env, after bridging the env into the submodule:
    ./bridge_tasks.sh
    conda activate RoboTwin
    python tests/arm_select/spike_success_rate.py [N]

Exit code is non-zero if either arm's rate is below the ~90% gate or the
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

TASK_NAME = "arm_select"
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


def run_phase(label, arm, oracle_arm, expect_success):
    """Run N episodes; return success rate. expect_success=False for the
    counter-example phase (we want it rejected)."""
    TASK.ARM_OVERRIDE = arm
    TASK.ORACLE_ARM = oracle_arm
    n_ok = 0
    n_run = 0
    print(f"\n== phase '{label}': arm={arm} "
          f"exec={oracle_arm or 'match'}  {N} episodes ==")
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

        z0 = float(TASK.box.get_pose().p[2])
        try:
            TASK.play_once()
        except Exception as e:
            print(f"[ep {ep:02d}] ERROR phase-crash: {e}")
            n_run += 1
            continue
        rise = float(TASK.box.get_pose().p[2]) - z0
        sig = TASK.eval_signals()
        ok = bool(TASK.check_success())
        plan = getattr(TASK, "plan_success", "?")
        n_run += 1
        n_ok += int(ok)
        print(f"[ep {ep:02d}] {'OK ' if ok else 'FAIL'} "
              f"rise {rise:+.3f}m  d_cmd={sig['dist_cmd_tcp']:.3f} "
              f"d_other={sig['dist_other_tcp']:.3f}  match={sig['arm_match']}  plan={plan}")

    rate = n_ok / n_run if n_run else 0.0
    print(f"  -> {n_ok}/{n_run} success ({rate:.1%})")
    return rate, n_run


print(f"==== arm_select spike: N={N}, gate {GATE:.0%} ====")
left_rate, _ = run_phase("left arm", "left", None, expect_success=True)
right_rate, _ = run_phase("right arm", "right", None, expect_success=True)
# Counter-example: command left, execute with the right arm -> arm_match must
# reject even though the box lifts.
ce_rate, _ = run_phase("counter-example", "left", "right", expect_success=False)

print("\n==== summary ====")
print(f"left arm     : {left_rate:.1%}   gate {GATE:.0%}   {'PASS' if left_rate >= GATE else 'BELOW GATE'}")
print(f"right arm    : {right_rate:.1%}   gate {GATE:.0%}   {'PASS' if right_rate >= GATE else 'BELOW GATE'}")
print(f"counter-ex.  : {ce_rate:.1%}   want <=10%   {'PASS' if ce_rate <= 0.10 else 'LEAK'}")

arms_pass = left_rate >= GATE and right_rate >= GATE
ce_pass = ce_rate <= 0.10
if arms_pass and ce_pass:
    print("\nPASS -> center box is reachable by both arms; lock Propose A geometry")
else:
    print("\nBELOW GATE -> widen overlap / adjust box pose or contacts and re-run")
sys.exit(0 if (arms_pass and ce_pass) else 1)
