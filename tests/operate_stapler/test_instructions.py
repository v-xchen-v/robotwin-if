#!/usr/bin/env python3
"""Layer-A instruction-pool invariants for operate_stapler.json.

Guards the {B}-placeholder routing that makes shared-scene verb discrimination work,
and seen/unseen disjointness. Uses RoboTwin's REAL filter_instructions so the test
tracks upstream routing semantics (no simulator needed, but run in the RoboTwin env
for the yaml import inside that module).

    python tests/operate_stapler/test_instructions.py

Boundary: this checks STRUCTURAL routing (a template is a "move" template iff it
contains {B}). It cannot detect a semantically-move sentence that was stripped of {B}
— such a sentence masquerades as press and would pass. The merge step is responsible
for dropping those; the count baselines below are a regression tripwire for drift.
"""
import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _p = os.path.dirname(_REPO)
    if _p == _REPO:
        raise RuntimeError("could not locate repo root (no third_party/robotwin above)")
    _REPO = _p

_JSON = os.path.join(_REPO, "tasks", "task_instruction", "operate_stapler.json")
sys.path.insert(0, os.path.join(_REPO, "third_party", "robotwin", "description", "utils"))
from generate_episode_instructions import filter_instructions  # noqa: E402

# Expected filtered counts (regression tripwire). Update deliberately if you change the
# pool; a change here forces a conscious review that routing stayed clean.
EXPECT = {
    ("press", "seen"): 48, ("press", "unseen"): 10,
    ("move", "seen"): 48, ("move", "unseen"): 8,
}

PRESS_PARAMS = {"{A}": "048_stapler/base0", "{a}": "left"}          # no {B}
MOVE_PARAMS = {"{A}": "048_stapler/base0", "{B}": "Red", "{a}": "left"}

data = json.load(open(_JSON))
SEEN, UNSEEN = data["seen"], data["unseen"]


def _has_b(t):
    return "{B}" in t


def _is_press(t):
    return not _has_b(t)


_results = []


def _check(name, ok, note=""):
    _results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


# 1. Both verbs present in both pools (else a mode has no instructions under one type).
_check("press templates in seen", any(_is_press(t) for t in SEEN))
_check("press templates in unseen", any(_is_press(t) for t in UNSEEN))
_check("move templates in seen", any(_has_b(t) for t in SEEN))
_check("move templates in unseen", any(_has_b(t) for t in UNSEEN))

# 2. Per-verb seen ∩ unseen = ∅ (IF requires zero train/eval template overlap).
for verb, pred in [("press", _is_press), ("move", _has_b)]:
    s = {t for t in SEEN if pred(t)}
    u = {t for t in UNSEEN if pred(t)}
    _check(f"{verb} seen∩unseen = empty", s.isdisjoint(u), note=f"overlap={len(s & u)}")

# 3. Routing via RoboTwin's real filter: each mode's params select only its own verb,
#    both pools non-empty, and counts match the baseline.
for pool_name, pool in [("seen", SEEN), ("unseen", UNSEEN)]:
    fp = filter_instructions(list(pool), PRESS_PARAMS)
    _check(f"press mode / {pool_name}: only press templates, non-empty",
           fp and all(_is_press(t) for t in fp),
           note=f"n={len(fp)} move_leak={sum(_has_b(t) for t in fp)}")
    _check(f"press mode / {pool_name}: count == {EXPECT[('press', pool_name)]}",
           len(fp) == EXPECT[("press", pool_name)], note=f"got {len(fp)}")

    fm = filter_instructions(list(pool), MOVE_PARAMS)
    _check(f"move mode / {pool_name}: only move templates, non-empty",
           fm and all(_has_b(t) for t in fm),
           note=f"n={len(fm)} press_leak={sum(_is_press(t) for t in fm)}")
    _check(f"move mode / {pool_name}: count == {EXPECT[('move', pool_name)]}",
           len(fm) == EXPECT[("move", pool_name)], note=f"got {len(fm)}")

print(f"\n==== {sum(_results)}/{len(_results)} passed ====")
sys.exit(0 if _results and all(_results) else 1)
