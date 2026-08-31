#!/usr/bin/env python3
"""Layer-B check_success discrimination tests for the IF-Verb-Select laptop pair.

Positive collection only proves "correct direction -> True". It does NOT prove
"wrong direction -> False" — a check_success that ignored the hinge angle would
pass collection yet make the verb benchmark meaningless (a policy could open
when told to close and still score). This script sets the hinge to specific
end-states and asserts check_success returns the expected boolean per task.

The KEY cases are the reversals (design doc 09-IF-Ext s1, Layer B "必过"):
  - close_laptop: lid OPEN (wrong direction) -> must be False.
  - open_laptop_mid: lid CLOSED (wrong direction) -> must be False.

Run inside the RoboTwin conda env, after ./bridge_tasks.sh:
    conda activate RoboTwin
    python tests/close_laptop/test_check_success.py
Exit code is non-zero if any case fails (usable as a regression gate).
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

import collect_data as cd  # noqa: E402

_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run


def build_task(task_name):
    cd.main(task_name=task_name, task_config="demo_clean")
    task = _cap["task"]
    args = dict(_cap["args"])
    args["render_freq"] = 0
    # Retry on unstable scene.
    last = None
    for s in range(0, 40, 2):
        try:
            task.setup_demo(now_ep_num=0, seed=s, **args)
            return task
        except Exception as e:
            last = e
    raise RuntimeError(f"{task_name}: no stable scene ({last})")


def set_open_fraction(task, frac):
    """Force the hinge to `frac` of its range (0=closed, 1=open) and return it."""
    lo, hi = task.laptop.get_qlimits()[0]
    task.laptop.set_qpos([lo + (hi - lo) * frac])
    return frac


_results = []


def _record(name, got, expect, note=""):
    got = bool(got)
    ok = got == expect
    _results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: got={got} expect={expect}  {note}")


# ============================ close_laptop (success = qpos <= 15%) ============
close = build_task("close_laptop")
assert abs(close.CLOSE_TARGET - 0.15) < 1e-9, close.CLOSE_TARGET

set_open_fraction(close, 0.05)
_record("close positive (lid closed ~5%)", close.check_success(), True)

set_open_fraction(close, 0.78)
_record("close reversal (lid OPEN ~78%) <-KEY", close.check_success(), False,
        note="opened when told to close -> must fail")

set_open_fraction(close, 0.50)
_record("close not-moved (still mid ~50%)", close.check_success(), False)

set_open_fraction(close, 0.13)
_record("close just-inside (13% < 15%)", close.check_success(), True)

set_open_fraction(close, 0.17)
_record("close just-outside (17% > 15%)", close.check_success(), False,
        note="pins threshold near 15%, not 50%")

# ============================ open_laptop_mid (success = qpos >= 70%) =========
opn = build_task("open_laptop_mid")
assert abs(opn.OPEN_TARGET - 0.70) < 1e-9, opn.OPEN_TARGET

set_open_fraction(opn, 0.78)
_record("open positive (lid open ~78%)", opn.check_success(), True)

set_open_fraction(opn, 0.05)
_record("open reversal (lid CLOSED ~5%) <-KEY", opn.check_success(), False,
        note="closed when told to open -> must fail")

set_open_fraction(opn, 0.50)
_record("open not-moved (still mid ~50%)", opn.check_success(), False)

set_open_fraction(opn, 0.72)
_record("open just-inside (72% > 70%)", opn.check_success(), True)

set_open_fraction(opn, 0.68)
_record("open just-outside (68% < 70%)", opn.check_success(), False,
        note="pins threshold near 70%, not 50%")

print("\n==== summary ====")
print(f"{sum(_results)}/{len(_results)} passed")
sys.exit(0 if _results and all(_results) else 1)
