#!/usr/bin/env python3
"""Layer-B + scene-pairing tests for the bottle_verb (pick vs shake) task.

Success keys on the TRAJECTORY accumulators (_z_peak for pick, _z_cum for shake),
not a settable end-state, so we drive those accumulators directly and assert
_raw_success — NOT check_success, which would call _record() and overwrite them
with the real bottle pose.

KEY reversals (the discrimination the whole task rests on):
  - told pick but SHOOK (low peak) -> pick must be False.
  - told shake but PICKED (low cumulative travel) -> shake must be False.

Run inside the RoboTwin conda env, after ./bridge_tasks.sh:
    python tests/bottle_verb/test_check_success.py
Exit code non-zero if any case fails.
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

_cap = {}


def _capture(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture
cd.main(task_name="bottle_verb", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0

_results = []


def _record(name, ok, note=""):
    _results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


def setup(seed):
    s = seed
    for _ in range(20):
        try:
            TASK.setup_demo(now_ep_num=0, seed=s, **ARGS)
            return
        except Exception:
            s += 2  # keep parity so the mode is preserved
    raise RuntimeError(f"no stable scene near {seed}")


def sig():
    p = TASK.bottle.get_pose()
    return (TASK.bottle_id, tuple(np.round(p.p, 5).tolist()))


def set_traj(peak, cum):
    TASK._z_peak = peak
    TASK._z_cum = cum


def rs(mode):
    return bool(TASK._raw_success(mode))


# ===================== scene/verb decoupling =====================
setup(4)
bias = TASK.table_z_bias
mid4, sig4, mode4 = TASK.bottle_id, sig(), TASK.mode
setup(5)
mid5, sig5, mode5 = TASK.bottle_id, sig(), TASK.mode
_record("pair (4,5) same bottle scene", sig4 == sig5, note=f"{mid4} vs {mid5}")
_record("pair (4,5) opposite modes", {mode4, mode5} == {"pick", "shake"}, note=f"{mode4}/{mode5}")

PH = TASK.PICK_HIGH + bias
ST = TASK.SHAKE_TRAVEL

# ===================== pick criterion (peak z, height gap) =====================
set_traj(peak=PH + 0.03, cum=0.20)
_record("pick positive (high lift, no oscillation)", rs("pick"))
set_traj(peak=0.933, cum=0.40)  # a SHAKE trajectory
_record("pick reversal (shook: peak below gap) <-KEY", not rs("pick"),
        note="shook when told pick -> must fail")
set_traj(peak=PH + 0.02, cum=0.20)
_record("pick just-inside (peak above PICK_HIGH)", rs("pick"))
set_traj(peak=PH - 0.02, cum=0.20)
_record("pick just-outside (peak below PICK_HIGH)", not rs("pick"))

# ===================== shake criterion (cumulative |dz|) =====================
set_traj(peak=0.933, cum=ST + 0.10)
_record("shake positive (oscillated)", rs("shake"))
set_traj(peak=PH + 0.03, cum=0.20)  # a PICK trajectory (high, monotonic)
_record("shake reversal (picked: low travel) <-KEY", not rs("shake"),
        note="picked when told shake -> must fail")
set_traj(peak=0.90, cum=ST + 0.05)
_record("shake just-inside (travel above SHAKE_TRAVEL)", rs("shake"))
set_traj(peak=0.90, cum=ST - 0.05)
_record("shake just-outside (travel below SHAKE_TRAVEL)", not rs("shake"))

print("\n==== summary ====")
print(f"{sum(_results)}/{len(_results)} passed")
sys.exit(0 if _results and all(_results) else 1)
