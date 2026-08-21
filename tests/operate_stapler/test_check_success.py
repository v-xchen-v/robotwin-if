#!/usr/bin/env python3
"""Layer-B check_success discrimination tests for the operate_stapler task.

Positive collection runs only prove "correct action -> True". They do NOT prove
"wrong action -> False" — a check_success that always returned True would pass them
all yet make the IF benchmark meaningless. This script constructs specific end-states
and asserts check_success returns the expected boolean, per mode.

Design + rationale: notes/2026-08-20-operate-stapler/negative-test-plan.md

Run from anywhere, inside the RoboTwin conda env:
    conda activate RoboTwin
    python tests/operate_stapler/test_check_success.py

Exit code is non-zero if any case fails (usable as a regression gate).
"""
import os
import sys

# Locate the repo root by walking up until third_party/robotwin is found, then run with
# cwd = submodule root so ./assets, ./task_config resolve (same as collect_data).
# This keeps the script location-independent (works at any nesting depth under tools/).
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
import sapien  # noqa: E402
import collect_data as cd  # noqa: E402  (RoboTwin's collector; reused for arg construction)

# --- Reuse collect_data.main()'s exact arg build by intercepting run() ---------
# main() builds `task` + `args` (config load + embodiment resolution) then calls
# run(task, args). We swap run() for a capture, so we get identical args with zero
# copy-paste drift and never enter the collection loop.
_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run
cd.main(task_name="operate_stapler", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0

# Orientation whose |components| are all equal -> passes the move check's
# (abs(q).max() - abs(q).min()) < 0.02 alignment test.
ALIGN_Q = [0.5, 0.5, 0.5, 0.5]

_results = []


def _setup(seed):
    """setup_demo with retry on UnStableError, preserving seed parity (=> mode)."""
    s = seed
    last = None
    for _ in range(20):
        try:
            TASK.setup_demo(now_ep_num=0, seed=s, **ARGS)
            return s
        except Exception as e:  # UnStableError etc. -> try next same-parity seed
            last = e
            s += 2
    raise RuntimeError(f"no stable scene near seed {seed}: {last}")


def _record(name, got, expect, note=""):
    got = bool(got)
    ok = got == expect
    _results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: got={got} expect={expect}  {note}")


# ============================ MOVE mode (odd seed) ============================
seed = _setup(1)
assert TASK.mode == "move", f"expected move, got {TASK.mode}"
pad_p = TASK.pad.get_pose().p

# T1 positive control: place the STAPLER on the pad (aligned), grippers open by default.
TASK.stapler.actor.set_pose(sapien.Pose(pad_p, ALIGN_Q))
_record("T1 move positive (stapler on pad)", TASK.check_success(), True)

# T2 (KEY) wrong-object: place a DISTRACTOR on the pad, stapler left at spawn.
_setup(1)
pad_p = TASK.pad.get_pose().p
if TASK.distractors:
    try:
        TASK.distractors[0].actor.set_pose(sapien.Pose(pad_p, ALIGN_Q))
        _record("T2 move wrong-object (distractor on pad) <-KEY", TASK.check_success(),
                False, note=f"distractor={TASK.distractor_info[0]}")
    except Exception as e:
        print(f"[SKIP] T2: could not set distractor pose ({e}); "
              f"try making distractors dynamic for this test")
else:
    print("[SKIP] T2: this episode spawned no distractor")

# T3 not-placed: default post-setup state (stapler is >0.1 from pad by construction).
_setup(1)
_record("T3 move not-placed (default state)", TASK.check_success(), False)

# ============================ PRESS mode (even seed) =========================
_setup(0)
assert TASK.mode == "press", f"expected press, got {TASK.mode}"

# T5 no-contact: default post-setup state has no gripper<->stapler contact.
_record("T5 press no-contact (default state)", TASK.check_success(), False)

# T6 positive control: run the scripted expert so a real cp2 contact is produced
# (contact-based check cannot be faked with set_pose).
_setup(0)
TASK.play_once()
_record("T6 press positive (ran expert)", TASK.check_success(), True,
        note=f"plan_success={getattr(TASK, 'plan_success', '?')}")

# ================================ summary ====================================
print("\n==== summary ====")
print(f"{sum(_results)}/{len(_results)} passed")
sys.exit(0 if _results and all(_results) else 1)
