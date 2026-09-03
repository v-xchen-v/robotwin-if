#!/usr/bin/env python3
"""Layer-A instruction-pool invariants for place_relative.json.

All five placement directions share one template family:
  - {A}: mover
  - {B}: reference
  - {D}: seed-selected direction phrase
  - {a}: optional arm

The test exercises RoboTwin's real filter_instructions and placeholder renderer for
all five directions. It does not require the simulator.

    python tests/place_relative/test_instructions.py
"""
import json
import os
import re
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _p = os.path.dirname(_REPO)
    if _p == _REPO:
        raise RuntimeError("could not locate repo root (no third_party/robotwin above)")
    _REPO = _p

_JSON = os.path.join(_REPO, "tasks", "task_instruction", "place_relative.json")
sys.path.insert(0, os.path.join(_REPO, "third_party", "robotwin", "description", "utils"))
from generate_episode_instructions import filter_instructions, replace_placeholders  # noqa: E402

DIRECTION_PHRASES = (
    "to the left of",
    "to the right of",
    "in front of",
    "behind",
    "on top of",
)
BASE_PARAMS = {
    "{A}": "the red mouse",
    "{B}": "the green plate",
    "{a}": "left",
}

data = json.load(open(_JSON))
SEEN, UNSEEN = data["seen"], data["unseen"]

_results = []


def _check(name, ok, note=""):
    _results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


def _sig(template):
    placeholders = set(re.findall(r"{([^}]+)}", template))
    placeholders.discard("a")
    return frozenset(placeholders)


# 1. Every template belongs to the one unified direction family. The optional arm
#    placeholder does not affect routing.
for pool_name, pool in [("seen", SEEN), ("unseen", UNSEEN)]:
    bad = [template for template in pool if _sig(template) != frozenset({"A", "B", "D"})]
    _check(
        f"{pool_name}: every template uses {{A,B,D}} (+ optional {{a}})",
        not bad,
        note=f"offenders={bad[:3]}",
    )

# 2. The direction phrase must directly modify the reference object. This prevents
#    templates that render ambiguously or attach the direction to the mover/action.
for pool_name, pool in [("seen", SEEN), ("unseen", UNSEEN)]:
    bad = [template for template in pool if "{D} {B}" not in template]
    _check(
        f"{pool_name}: {{D}} is immediately before {{B}}",
        not bad,
        note=f"offenders={bad[:3]}",
    )

# 3. IF held-out instruction templates must not overlap the seen pool.
s, u = set(SEEN), set(UNSEEN)
_check("seen∩unseen = empty", s.isdisjoint(u), note=f"overlap={len(s & u)}")

# 4. Exercise RoboTwin's real routing and rendering for every direction. Because all
#    directions use {D}, each parameter set must retain the entire unified pool.
for phrase in DIRECTION_PHRASES:
    params = {**BASE_PARAMS, "{D}": phrase}
    for pool_name, pool in [("seen", SEEN), ("unseen", UNSEEN)]:
        filtered = filter_instructions(list(pool), params)
        _check(
            f"{pool_name}/{phrase}: real filter retains unified family",
            len(filtered) == len(pool) and set(filtered) == set(pool),
            note=f"got={len(filtered)}/{len(pool)}",
        )

        bad = []
        for template in filtered:
            rendered = replace_placeholders(template, dict(params))
            if (
                BASE_PARAMS["{A}"] not in rendered
                or BASE_PARAMS["{B}"] not in rendered
                or phrase not in rendered
                or "{" in rendered
                or "the the" in rendered.lower()
            ):
                bad.append(rendered)
        _check(
            f"{pool_name}/{phrase}: placeholders render cleanly",
            not bad,
            note=f"offenders={bad[:2]}",
        )

print(f"\n==== {sum(_results)}/{len(_results)} passed ====")
sys.exit(0 if _results and all(_results) else 1)
