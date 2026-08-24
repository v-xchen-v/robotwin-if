#!/usr/bin/env python3
"""Layer-B check_success discrimination tests for pick_diverse_object.

Positive collection runs only prove "correct action -> True". They do NOT prove
"wrong action -> False" — a check_success that always returned True would pass them
all yet make the grounding benchmark meaningless. This drives specific end-states
and asserts check_success returns the expected boolean.

The KEY cases are D3/D4: the instruction names one object by color+noun, a DIFFERENT
distractor is lifted instead, and check_success must stay False:
  - D3 lifts the SAME-COLOR different-noun distractor (color alone would mislead),
  - D4 lifts the SAME-NOUN different-color distractor (noun alone would mislead).
D5 lifts the target itself WITHOUT a grasp -> False (the "held" half of the check).

Run from anywhere, inside the RoboTwin conda env:
    conda activate RoboTwin
    python tests/pick_diverse_object/test_check_success.py
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
import sapien  # noqa: E402
import collect_data as cd  # noqa: E402  (RoboTwin's collector; reused for arg construction)

_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run
cd.main(task_name="pick_diverse_object", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0

ALIGN_Q = [0.5, 0.5, 0.5, 0.5]
_results = []


def _setup(seed):
    """setup_demo with retry on UnStableError (advance seed by +1; single mode)."""
    s = seed
    last = None
    for _ in range(40):
        try:
            TASK.setup_demo(now_ep_num=0, seed=s, **ARGS)
            return s
        except Exception as e:  # UnStableError etc.
            last = e
        s += 1
    raise RuntimeError(f"no suitable scene near seed {seed}: {last}")


def _distractor(role):
    for d in TASK.distractors:
        if d["role"] == role:
            return d
    return None


def _record(name, got, expect, note=""):
    got = bool(got)
    ok = got == expect
    _results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: got={got} expect={expect}  {note}")


def _lift(actor):
    tp = TASK.target.get_pose().p
    actor.actor.set_pose(sapien.Pose([float(tp[0]), float(tp[1]), float(tp[2]) + 0.2], ALIGN_Q))


# D1 default: nothing picked, target at rest -> False.
_setup(0)
_record("D1 default (nothing picked)", TASK.check_success(), False,
        note=f"target={TASK.target_noun}/{TASK.target_color}")

# D2 positives: the scripted expert must be able to grasp+lift EACH of the 12 target
# categories (grasp params are object-specific). A single grasp from a random pose isn't
# 100% reliable (normal for RoboTwin — collect_data retries), so give each noun several
# chances and pass if ANY succeeds with check_success True; the real per-object oracle
# rate is what the collection reporter measures. seed % 12 -> each noun recurs every 12.
ALL_NOUNS = ["bottle", "cup", "shoe", "mug", "can", "toycar", "phone",
             "soap", "hamburg", "bread", "coffee-box", "mouse"]
passed, attempts = {}, {}
seed = 0
while len(passed) < len(ALL_NOUNS) and seed < 240:
    s = _setup(seed)
    noun = TASK.target_noun
    if noun not in passed:
        attempts[noun] = attempts.get(noun, 0) + 1
        try:
            TASK.play_once()
            if TASK.check_success():
                passed[noun] = (s, TASK.target_color)
        except Exception:
            pass
    seed = s + 1
for noun in ALL_NOUNS:
    if noun in passed:
        _record(f"D2 positive ({noun} target graspable)", True, True,
                note=f"{passed[noun][1]} {noun} seed={passed[noun][0]} (in {attempts[noun]} tries)")
    else:
        _record(f"D2 positive ({noun} target graspable)", False, True,
                note=f"no success in {attempts.get(noun, 0)} tries")

# D3 (KEY) lift the SAME-COLOR different-noun distractor -> False (color alone misleads).
# Under option B such a distractor isn't in every scene, so scan seeds to find one.
def _find_role(role, start):
    s = start
    for _ in range(80):
        s = _setup(s)
        d = _distractor(role)
        if d is not None:
            return s, d
        s += 1
    raise RuntimeError(f"no episode with a {role} distractor near seed {start}")


s, d = _find_role("same_color", 1)
_lift(d["actor"])
_record("D3 same-COLOR distractor lifted <-KEY", TASK.check_success(), False,
        note=f"seed={s} target={TASK.target_noun}/{TASK.target_color} wrong={d['noun']}/{d['color']}")

# D4 (KEY) lift the SAME-NOUN different-color distractor -> False (noun alone misleads).
s, d = _find_role("same_noun", 1)
_lift(d["actor"])
_record("D4 same-NOUN distractor lifted <-KEY", TASK.check_success(), False,
        note=f"seed={s} target={TASK.target_noun}/{TASK.target_color} wrong={d['noun']}/{d['color']}")

# D5 target moved up but NOT held (no grasp) -> False (the "held" half of the check).
_setup(3)
_lift(TASK.target)
_record("D5 target lifted but not held", TASK.check_success(), False)

print("\n==== summary ====")
print(f"{sum(_results)}/{len(_results)} passed")
sys.exit(0 if _results and all(_results) else 1)
