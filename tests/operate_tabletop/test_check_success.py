#!/usr/bin/env python3
"""Layer-B check_success discrimination tests for the operate_tabletop task.

Positive collection runs only prove "correct action -> True". They do NOT prove
"wrong action -> False" — a check_success that always returned True would pass them
all yet make the IF benchmark meaningless. This script drives specific end-states
and asserts check_success returns the expected boolean, per mode (click/press/pick).

The KEY case is pick K3: the instruction names one object, a DIFFERENT graspable is
moved instead, and check_success must stay False (target grounding, not "something
got lifted").

Run from anywhere, inside the RoboTwin conda env:
    conda activate RoboTwin
    python tests/operate_tabletop/test_check_success.py

Exit code is non-zero if any case fails (usable as a regression gate).
"""
import os
import sys

# Locate repo root by walking up to third_party/robotwin, then run with cwd = submodule
# root so ./assets, ./task_config, ./description resolve (same as collect_data).
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

# --- Reuse collect_data.main()'s exact arg build by intercepting run() -----------
_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run
cd.main(task_name="operate_tabletop", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0

# mode = seed % 3  -> click=0, press=1, pick=2. Retries below preserve seed % 3.
ALIGN_Q = [0.5, 0.5, 0.5, 0.5]

_results = []


def _setup(seed, want_mode=None, want_graspables=0):
    """setup_demo with retry on UnStableError, preserving seed%3 (=> mode). Optionally
    keep advancing (by +3, same parity) until the scene has >= want_graspables objects."""
    s = seed
    last = None
    for _ in range(40):
        try:
            TASK.setup_demo(now_ep_num=0, seed=s, **ARGS)
            if want_mode is not None and TASK.mode != want_mode:
                raise RuntimeError(f"seed {s} gave mode {TASK.mode}, want {want_mode}")
            if len(getattr(TASK, "graspables", [])) >= want_graspables:
                return s
        except Exception as e:  # UnStableError etc. -> next same-parity seed
            last = e
        s += 3
    raise RuntimeError(f"no suitable scene near seed {seed} (want_mode={want_mode}, "
                       f"want_graspables={want_graspables}): {last}")


def _record(name, got, expect, note=""):
    got = bool(got)
    ok = got == expect
    _results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: got={got} expect={expect}  {note}")


# ============================ CLICK mode (seed % 3 == 0) =====================
_setup(0, want_mode="click")
# C1 no-contact: default post-setup has no gripper<->bell contact.
_record("C1 click no-contact (default state)", TASK.check_success(), False)

# C2 positive: run the scripted expert (contact-based check cannot be faked by set_pose).
_setup(0, want_mode="click")
TASK.play_once()
_record("C2 click positive (ran expert)", TASK.check_success(), True,
        note=f"plan_success={getattr(TASK, 'plan_success', '?')}")

# ============================ PRESS mode (seed % 3 == 1) =====================
_setup(1, want_mode="press")
# P1 no-contact: default post-setup has no gripper<->stapler contact.
_record("P1 press no-contact (default state)", TASK.check_success(), False)

# P2 positive: run the scripted expert.
_setup(1, want_mode="press")
TASK.play_once()
_record("P2 press positive (ran expert)", TASK.check_success(), True,
        note=f"plan_success={getattr(TASK, 'plan_success', '?')}")

# ============================ PICK mode (seed % 3 == 2) ======================
_setup(2, want_mode="pick")
# K1 not-picked: default post-setup, target at rest and unheld.
_record("K1 pick not-picked (default state)", TASK.check_success(), False)

# K2 positive: run the scripted expert (grasp + lift, still holding).
_setup(2, want_mode="pick")
TASK.play_once()
_record("K2 pick positive (ran expert)", TASK.check_success(), True,
        note=f"plan_success={getattr(TASK, 'plan_success', '?')}")

# K3 (KEY) wrong-object: a scene with >=2 graspables; teleport a NON-target graspable
# up (as if the policy picked the wrong object). Target stays at rest -> must be False.
_setup(2, want_mode="pick", want_graspables=2)
wrong = TASK.graspables[1]  # graspables[0] is the target
tp = TASK.target.get_pose().p
wrong.actor.set_pose(sapien.Pose([tp[0], tp[1], tp[2] + 0.2], ALIGN_Q))
_record("K3 pick wrong-object (lifted a distractor) <-KEY", TASK.check_success(), False,
        note=f"target={TASK.target_modelname} wrong={TASK.graspable_names[1]}")

# ================================ summary ====================================
print("\n==== summary ====")
print(f"{sum(_results)}/{len(_results)} passed")
sys.exit(0 if _results and all(_results) else 1)
