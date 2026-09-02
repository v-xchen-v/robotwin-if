#!/usr/bin/env python3
"""Layer-A instruction-pool invariants for pick_diverse_object.json.

Single-mode task (only {A}=target object, {a}=arm), so routing is simpler than the
three-way operate_tabletop. What matters here is the CONTROLLED color+noun injection:
{A} is filled with a literal "the {color} {noun}" (no '/'), so RoboTwin's real
replace_placeholders must substitute it verbatim (not draw a random objects_description).
This test checks seen/unseen disjointness, {A}-only routing via the real
filter_instructions, and that literal injection yields a clean color+noun sentence.

    python tests/pick_diverse_object/test_instructions.py

(no simulator needed, but run in the RoboTwin env for the yaml import inside the
generate_episode_instructions module).
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

_JSON = os.path.join(_REPO, "tasks", "task_instruction", "pick_diverse_object.json")
sys.path.insert(0, os.path.join(_REPO, "third_party", "robotwin", "description", "utils"))
from generate_episode_instructions import filter_instructions, replace_placeholders  # noqa: E402

# Regression tripwire (borrowed from adjust_bottle's orientation-free subset, {C}->{A}).
EXPECT = {"seen": 12, "unseen": 4}
PARAMS = {"{A}": "the red cup", "{a}": "left"}  # {A} literal = "the {color} {noun}"

data = json.load(open(_JSON))
SEEN, UNSEEN = data["seen"], data["unseen"]

_results = []


def _check(name, ok, note=""):
    _results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


# 1. Every template carries {A}; no stray {B}/{C} (single-object task).
for pool_name, pool in [("seen", SEEN), ("unseen", UNSEEN)]:
    no_a = [t for t in pool if "{A}" not in t]
    stray = [t for t in pool if "{B}" in t or "{C}" in t]
    _check(f"{pool_name}: every template has {{A}}", not no_a, note=f"offenders={no_a[:3]}")
    _check(f"{pool_name}: no stray {{B}}/{{C}}", not stray, note=f"offenders={stray[:3]}")

# 2. seen ∩ unseen = ∅ (IF requires zero train/eval template overlap).
s, u = set(SEEN), set(UNSEEN)
_check("seen∩unseen = empty", s.isdisjoint(u), note=f"overlap={len(s & u)}")

# 3. Routing via RoboTwin's real filter: params select the whole pool, counts match.
for pool_name, pool in [("seen", SEEN), ("unseen", UNSEEN)]:
    f = filter_instructions(list(pool), PARAMS)
    _check(f"{pool_name}: filter non-empty & count == {EXPECT[pool_name]}",
           len(f) == EXPECT[pool_name], note=f"got {len(f)}")

# 4. Literal color+noun injection: replace_placeholders substitutes "{A}" verbatim,
#    every rendered instruction contains "red cup", no leftover braces, no "the the".
for pool_name, pool in [("seen", SEEN), ("unseen", UNSEEN)]:
    bad = []
    for t in pool:
        out = replace_placeholders(t, dict(PARAMS))
        if ("red cup" not in out) or ("{" in out) or ("the the" in out):
            bad.append(out)
    _check(f"{pool_name}: literal color+noun renders cleanly", not bad, note=f"offenders={bad[:2]}")

print(f"\n==== {sum(_results)}/{len(_results)} passed ====")
sys.exit(0 if _results and all(_results) else 1)
