#!/usr/bin/env python3
"""Per-variant, per-direction reliability sweep for laptop_verb.

Forces each 015_laptop variant and runs K open + K close episodes, measuring the
RAW single-direction success (`_raw_success`, NOT the pair-gated `check_success`
which would trial-run the partner direction). This is how the reliable subset
{1,9} was chosen — a variant is usable only if BOTH directions clear the bar.
Re-run this if the subset or the asset ever changes.

(Supersedes the earlier close-only `tests/close_laptop/sweep_per_variant.py`,
which drove the now-deleted close_laptop spike env.)

Run inside the RoboTwin conda env, after ./bridge_tasks.sh:
    python tests/laptop_verb/sweep_per_variant.py [K=6] [max_variants=11]
"""
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _parent = os.path.dirname(_REPO)
    if _parent == _REPO:
        raise RuntimeError("could not locate repo root")
    _REPO = _parent
_RT = os.path.join(_REPO, "third_party", "robotwin")
os.chdir(_RT)
sys.path.insert(0, os.path.join(_RT, "script"))
sys.path.insert(0, _RT)

import numpy as np  # noqa: E402
import collect_data as cd  # noqa: E402

K = int(sys.argv[1]) if len(sys.argv) > 1 else 6
N_VARIANTS = int(sys.argv[2]) if len(sys.argv) > 2 else 11

_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run
cd.main(task_name="laptop_verb", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0


def _run(mid, seed):
    """Force variant `mid`; run the episode at `seed` (parity picks open/close).
    Returns (mode, raw_success | None-on-crash)."""
    TASK.ALLOWED_MODEL_IDS = [mid]
    s = seed
    ok_setup = False
    for _ in range(20):
        try:
            TASK.setup_demo(now_ep_num=0, seed=s, **ARGS)
            ok_setup = True
            break
        except Exception:
            s += 202  # even bump keeps seed parity (= direction)
    if not ok_setup:
        return None, None
    mode = TASK.mode
    try:
        TASK.play_once()
    except Exception:
        return mode, None  # hard crash (e.g. degenerate first-grasp -> None pose)
    return mode, bool(TASK._raw_success(mode))


print(f"== laptop_verb per-variant sweep: {K} open + {K} close x {N_VARIANTS} variants ==")
tally = {}
for mid in range(N_VARIANTS):
    res = {"open": [0, 0, 0], "close": [0, 0, 0]}  # [ok, crash, n]
    inv = None
    for direction, parity in (("open", 0), ("close", 1)):
        for k in range(K):
            mode, ok = _run(mid, seed=1000 * mid + 2 * k + parity)
            if inv is None:
                try:
                    inv = TASK.laptop.config["contact_points"][0]["base"] == "link_0"
                except Exception:
                    inv = False
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

    tally[mid] = (rate("open"), rate("close"))
    print(f"  mid={mid:2d} {'INV' if inv else '   '}  "
          f"open {res['open'][0]}/{res['open'][2]} ({rate('open'):5.1%})  "
          f"close {res['close'][0]}/{res['close'][2]} ({rate('close'):5.1%})  "
          f"crash o{res['open'][1]}/c{res['close'][1]}")

print("\n==== reliable subset (BOTH directions >= 90%) ====")
good = [m for m, (ro, rc) in tally.items() if ro >= 0.90 and rc >= 0.90]
print(f"  {good}   ({len(good)}/{N_VARIANTS} variants)")
