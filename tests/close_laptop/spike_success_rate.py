#!/usr/bin/env python3
"""Oracle spike for the IF-Verb-Select close direction (close_laptop).

Purpose: before locking asset B (015_laptop) for IF-Verb-Select, confirm the
self-written close oracle reaches the closed band at ~90% from the shared
mid-state (~50% open). The open direction reuses native open_laptop and is
already validated; this spike stresses the new, risky close motion.

Runs setup_demo + play_once + check_success over N seeds and reports the
success rate plus the hinge qpos trajectory (init -> final vs the closed band),
so a failure reads as "stalled at X% open" rather than a bare rate.

Run inside the RoboTwin conda env, after bridging the env into the submodule:
    ./bridge_tasks.sh
    conda activate RoboTwin
    python tests/close_laptop/spike_success_rate.py [N]

Exit code is non-zero if the success rate is below the ~90% gate.
"""
import os
import sys

# Locate repo root, then run with cwd = submodule root so ./assets, ./task_config
# resolve (same convention as collect_data and the operate_stapler tests).
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

TASK_NAME = "close_laptop"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
GATE = 0.90

# --- Reuse collect_data.main()'s exact arg build by intercepting run() ---------
_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run
cd.main(task_name=TASK_NAME, task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0


def _frac_open(qpos):
    """Hinge opening as a fraction of the joint range (0=closed, 1=open)."""
    lo, hi = TASK.laptop.get_qlimits()[0]
    return (qpos - lo) / (hi - lo)


n_ok = 0
n_run = 0
print(f"== close_laptop spike: {N} episodes, gate {GATE:.0%} ==")
for ep in range(N):
    seed = ep
    # Retry on unstable scene, preserving nothing special (any seed is fine here).
    last = None
    for _ in range(20):
        try:
            TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
            last = None
            break
        except Exception as e:
            last = e
            seed += N  # jump to a fresh seed
    if last is not None:
        print(f"[ep {ep:02d}] SKIP: no stable scene ({last})")
        continue

    mid = TASK.model_id
    bases = [TASK.laptop.config["contact_points"][i]["base"] for i in range(4)]
    inv = "INV" if bases[0] == "link_0" else "   "  # inverted screen/base semantics
    init_frac = _frac_open(TASK.laptop.get_qpos()[0])
    try:
        TASK.play_once()
    except Exception as e:
        print(f"[ep {ep:02d}] ERROR  mid={mid:2d} {inv} phase-crash: {e}")
        n_run += 1
        continue
    final_frac = _frac_open(TASK.laptop.get_qpos()[0])
    ok = bool(TASK.check_success())
    plan = getattr(TASK, "plan_success", "?")
    n_run += 1
    n_ok += int(ok)
    print(f"[ep {ep:02d}] {'OK ' if ok else 'FAIL'} mid={mid:2d} {inv} "
          f"open {init_frac:5.1%} -> {final_frac:5.1%}  "
          f"(target <= {TASK.CLOSE_TARGET:.0%})  plan_success={plan}")

rate = n_ok / n_run if n_run else 0.0
print("\n==== summary ====")
print(f"{n_ok}/{n_run} closed  ({rate:.1%})   gate {GATE:.0%}")
print("PASS -> lock asset B" if rate >= GATE else "BELOW GATE -> consider fallback A (036_cabinet drawer)")
sys.exit(0 if rate >= GATE else 1)
