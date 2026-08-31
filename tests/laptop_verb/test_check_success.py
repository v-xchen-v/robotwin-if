#!/usr/bin/env python3
"""Layer-B + scene-pairing tests for the merged IF-Verb-Select env laptop_verb.

Two things this env must guarantee:
  (1) Scene/verb decoupling: seeds (2k, 2k+1) produce the IDENTICAL scene
      (same variant, pose, init angle) with OPPOSITE modes — the structural
      "same frame, only the verb differs" property that motivated merging.
  (2) check_success grades the hinge angle in the mode's direction, and the
      REVERSAL (opened when told to close, or vice versa) MUST fail.

Run inside the RoboTwin conda env, after ./bridge_tasks.sh:
    conda activate RoboTwin
    python tests/laptop_verb/test_check_success.py
Exit code is non-zero if any case fails.
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

_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run
cd.main(task_name="laptop_verb", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0

_results = []


def _record(name, ok, note=""):
    _results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


def setup(seed):
    last = None
    s = seed
    for _ in range(20):
        try:
            TASK.setup_demo(now_ep_num=0, seed=s, **ARGS)
            return
        except Exception as e:
            last = e
            s += 2  # keep parity so mode is preserved
    raise RuntimeError(f"no stable scene near {seed}: {last}")


def sig():
    p = TASK.laptop.get_pose()
    return (TASK.model_id, np.round(p.p, 5).tolist(), np.round(p.q, 5).tolist())


def set_frac(frac):
    lo, hi = TASK.laptop.get_qlimits()[0]
    TASK.laptop.set_qpos([lo + (hi - lo) * frac])


def cs():
    # Test the pure single-direction predicate (_raw_success), not the pair-gated
    # check_success — the latter would trial-run the partner direction (full
    # setup+play), which is exercised by the native collect_data validation, not
    # here. check_success = _raw_success AND partner-scene-also-doable.
    return bool(TASK._raw_success(TASK.mode))


# ===================== (1) scene/verb decoupling ============================
# Seeds 4 and 5 -> scene_seed 2 -> identical scene; modes open vs close.
setup(4)
mode4, sig4 = TASK.mode, sig()
setup(5)
mode5, sig5 = TASK.mode, sig()
_record("pair (4,5) same scene", sig4 == sig5, note=f"{sig4[0]} vs {sig5[0]}")
_record("pair (4,5) opposite modes", {mode4, mode5} == {"open", "close"},
        note=f"{mode4} / {mode5}")

# ===================== (2) check_success direction + reversal ===============
# Even seed -> open mode.
setup(4)
assert TASK.mode == "open", TASK.mode
set_frac(0.78)
_record("open positive (78%)", cs())
set_frac(0.05)
_record("open reversal (closed 5%) <-KEY", not cs(),
        note="closed when told to open -> must fail")
set_frac(0.50)
_record("open not-moved (50%)", not cs())
set_frac(0.72)
_record("open just-inside (72%)", cs())
set_frac(0.68)
_record("open just-outside (68%)", not cs())

# Odd seed -> close mode.
setup(5)
assert TASK.mode == "close", TASK.mode
set_frac(0.05)
_record("close positive (5%)", cs())
set_frac(0.78)
_record("close reversal (open 78%) <-KEY", not cs(),
        note="opened when told to close -> must fail")
set_frac(0.50)
_record("close not-moved (50%)", not cs())
set_frac(0.18)
_record("close just-inside (18%)", cs())
set_frac(0.22)
_record("close just-outside (22%)", not cs())

print("\n==== summary ====")
print(f"{sum(_results)}/{len(_results)} passed")
sys.exit(0 if _results and all(_results) else 1)
