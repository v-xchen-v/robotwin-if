#!/usr/bin/env python3
"""Layer-A instruction-pool invariants for operate_tabletop.json.

Guards the three-way {A}/{B}/{C} placeholder routing (click/press/pick) that makes
shared-scene verb-and-target discrimination work, plus seen/unseen disjointness.
Uses RoboTwin's REAL filter_instructions so the test tracks upstream routing
semantics (no simulator needed, but run in the RoboTwin env for the yaml import
inside that module).

    python tests/operate_tabletop/test_instructions.py

Boundary: this checks STRUCTURAL routing (a template routes to a mode iff it holds
exactly that mode's placeholder). It cannot detect a semantically-pick sentence that
was mis-tagged with {B}; the count baselines below are the regression tripwire.
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

_JSON = os.path.join(_REPO, "tasks", "task_instruction", "operate_tabletop.json")
sys.path.insert(0, os.path.join(_REPO, "third_party", "robotwin", "description", "utils"))
from generate_episode_instructions import filter_instructions  # noqa: E402

# Expected filtered counts (regression tripwire). Update deliberately if you change
# the pool; a change here forces a conscious review that routing stayed clean.
# Templates are borrowed from native pools (see gen: click_bell / press_stapler /
# adjust_bottle), so these track those upstream pools after remap+filter.
EXPECT = {
    ("click", "seen"): 28, ("click", "unseen"): 5,
    ("press", "seen"): 48, ("press", "unseen"): 10,
    ("pick", "seen"): 12, ("pick", "unseen"): 4,
}

# Each mode fills exactly its own non-arm placeholder (arm {a} optional).
PARAMS = {
    "click": {"{A}": "050_bell/base0", "{a}": "left"},
    "press": {"{B}": "048_stapler/base0", "{a}": "left"},
    "pick": {"{C}": "077_phone/base0", "{a}": "left"},
}
PLACEHOLDER = {"click": "{A}", "press": "{B}", "pick": "{C}"}
MODES = ["click", "press", "pick"]

data = json.load(open(_JSON))
SEEN, UNSEEN = data["seen"], data["unseen"]

_results = []


def _check(name, ok, note=""):
    _results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


def _mode_of(t):
    present = [m for m in MODES if PLACEHOLDER[m] in t]
    return present[0] if len(present) == 1 else None


# 1. Every template carries exactly one mode placeholder (no {A}+{B} cross-tag).
for pool_name, pool in [("seen", SEEN), ("unseen", UNSEEN)]:
    bad = [t for t in pool if _mode_of(t) is None]
    _check(f"{pool_name}: every template has exactly one of A/B/C", not bad,
           note=f"offenders={bad[:3]}")

# 2. All three verbs present in both pools (else a mode has no instructions).
for m in MODES:
    _check(f"{m} templates in seen", any(_mode_of(t) == m for t in SEEN))
    _check(f"{m} templates in unseen", any(_mode_of(t) == m for t in UNSEEN))

# 3. Per-mode seen ∩ unseen = ∅ (IF requires zero train/eval template overlap).
for m in MODES:
    s = {t for t in SEEN if _mode_of(t) == m}
    u = {t for t in UNSEEN if _mode_of(t) == m}
    _check(f"{m} seen∩unseen = empty", s.isdisjoint(u), note=f"overlap={len(s & u)}")

# 4. Routing via RoboTwin's real filter: each mode's params select ONLY its own
#    templates, both pools non-empty, and counts match the baseline.
for m in MODES:
    for pool_name, pool in [("seen", SEEN), ("unseen", UNSEEN)]:
        f = filter_instructions(list(pool), PARAMS[m])
        only_mine = f and all(_mode_of(t) == m for t in f)
        leak = sum(1 for t in f if _mode_of(t) != m)
        _check(f"{m} mode / {pool_name}: only {m} templates, non-empty",
               only_mine, note=f"n={len(f)} leak={leak}")
        _check(f"{m} mode / {pool_name}: count == {EXPECT[(m, pool_name)]}",
               len(f) == EXPECT[(m, pool_name)], note=f"got {len(f)}")

print(f"\n==== {sum(_results)}/{len(_results)} passed ====")
sys.exit(0 if _results and all(_results) else 1)
