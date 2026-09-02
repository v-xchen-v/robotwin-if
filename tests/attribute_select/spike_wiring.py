#!/usr/bin/env python3
"""Stage-③ wiring spike for attribute_select.

Confirms the IF wiring, not a polished success rate:
  - seed -> (axis, value) derivation is correct,
  - the oracle grasps the commanded TARGET and check_success passes (positive),
  - a Layer-B phase grasps the DISTRACTOR and check_success REJECTS it,
per feature axis (color / decal / shape / size).

Run:
    ./bridge_tasks.sh
    conda activate RoboTwin
    python tests/attribute_select/spike_wiring.py [N]
"""
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _p = os.path.dirname(_REPO)
    if _p == _REPO:
        raise RuntimeError("repo root not found")
    _REPO = _p
_RT = os.path.join(_REPO, "third_party", "robotwin")
os.chdir(_RT)
sys.path.insert(0, os.path.join(_RT, "script"))
sys.path.insert(0, _RT)

import collect_data as cd  # noqa: E402

TASK_NAME = "attribute_select"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 6
AXES = ["color", "decal", "shape", "size"]
if os.environ.get("AXES"):
    AXES = os.environ["AXES"].split(",")

_cap = {}
cd.run = lambda task, args: _cap.update(task=task, args=args)
cd.main(task_name=TASK_NAME, task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"]); ARGS["render_freq"] = 0


def run_phase(axis, oracle_target, expect_pass):
    TASK.AXIS = axis
    TASK.VALUE = None                # let seed % 2 drive which value is target
    TASK.ORACLE_TARGET = oracle_target
    n_ok = n_run = 0
    by_val = {0: [0, 0], 1: [0, 0]}   # value -> [ok, run]
    for ep in range(N):
        seed = ep
        last = None
        for _ in range(15):
            try:
                TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
                last = None
                break
            except Exception as e:
                last = e
                seed += N
        if last is not None:
            print(f"  [ep {ep:02d}] SKIP scene: {last}")
            continue
        try:
            TASK.play_once()
        except Exception as e:
            print(f"  [ep {ep:02d}] ERROR: {e}")
            n_run += 1
            continue
        ok = bool(TASK._raw_success())   # per-episode oracle rate (NOT the pair-gate)
        sig = TASK.eval_signals()
        v = int(sig["value"])
        n_run += 1; n_ok += int(ok)
        by_val[v][1] += 1; by_val[v][0] += int(ok)
    rate = n_ok / n_run if n_run else 0.0
    tag = "PASS" if ((rate >= 0.8) == expect_pass) else "??"
    v0, v1 = by_val[0], by_val[1]
    print(f"  -> {axis} {oracle_target}: {n_ok}/{n_run} ({rate:.0%}) "
          f"[val0 {v0[0]}/{v0[1]}, val1 {v1[0]}/{v1[1]}] expect_pass={expect_pass} [{tag}]")
    return rate


print(f"==== attribute_select wiring spike N={N} ====")
for ax in AXES:
    print(f"\n== axis '{ax}' positive (grasp target) ==")
    run_phase(ax, "target", True)
    print(f"== axis '{ax}' Layer-B (grasp distractor -> must reject) ==")
    run_phase(ax, "distractor", False)
