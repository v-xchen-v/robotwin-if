#!/usr/bin/env python3
"""Per-variant, per-direction reliability sweep for bottle_verb.

Forces each 001_bottle variant and runs K pick + K shake episodes, measuring the
RAW single-direction success (_raw_success, which reads the trajectory
accumulators populated during the oracle play_once). Use this to pick a reliable
ALLOWED_MODEL_IDS subset if some variants grasp/shake unreliably.

Run inside the RoboTwin conda env, after ./bridge_tasks.sh:
    python tests/bottle_verb/sweep_per_variant.py [K=6] [n_variants=20]
"""
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _p = os.path.dirname(_REPO)
    if _p == _REPO:
        raise RuntimeError("could not locate repo root")
    _REPO = _p
_RT = os.path.join(_REPO, "third_party", "robotwin")
os.chdir(_RT)
sys.path.insert(0, os.path.join(_RT, "script"))
sys.path.insert(0, _RT)

import numpy as np  # noqa: E402
import collect_data as cd  # noqa: E402

K = int(sys.argv[1]) if len(sys.argv) > 1 else 6
N_VARIANTS = int(sys.argv[2]) if len(sys.argv) > 2 else 20

_cap = {}


def _capture(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture
cd.main(task_name="bottle_verb", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0


def _run(mid, seed):
    """Force variant mid; run the episode at seed (parity picks pick/shake).
    Returns (mode, raw_success | None-on-crash)."""
    TASK.ALLOWED_MODEL_IDS = [mid]
    s = seed
    for _ in range(20):
        try:
            TASK.setup_demo(now_ep_num=0, seed=s, **ARGS)
            break
        except Exception:
            s += 202  # even bump keeps parity
    else:
        return None, None
    mode = TASK.mode
    try:
        TASK.play_once()
    except Exception:
        return mode, None
    return mode, bool(TASK._raw_success(mode))


print(f"== bottle_verb per-variant sweep: {K} pick + {K} shake x {N_VARIANTS} variants ==")
tally = {}
for mid in range(N_VARIANTS):
    res = {"pick": [0, 0, 0], "shake": [0, 0, 0]}  # [ok, crash, n]
    for direction, parity in (("pick", 0), ("shake", 1)):
        for k in range(K):
            mode, ok = _run(mid, seed=1000 * mid + 2 * k + parity)
            if mode is None:
                continue
            res[direction][2] += 1
            if ok is None:
                res[direction][1] += 1
            elif ok:
                res[direction][0] += 1

    def rate(d):
        o, _c, n = res[d]
        return o / n if n else 0.0

    tally[mid] = (rate("pick"), rate("shake"))
    print(f"  mid={mid:2d}  pick {res['pick'][0]}/{res['pick'][2]} ({rate('pick'):5.1%})  "
          f"shake {res['shake'][0]}/{res['shake'][2]} ({rate('shake'):5.1%})  "
          f"crash p{res['pick'][1]}/s{res['shake'][1]}")

print("\n==== reliable subset (BOTH directions >= 90%) ====")
good = [m for m, (rp, rs) in tally.items() if rp >= 0.90 and rs >= 0.90]
print(f"  {good}   ({len(good)}/{N_VARIANTS} variants)")
