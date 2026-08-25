#!/usr/bin/env python3
"""Layer-A instruction-pool invariants for place_relative.json.

Two relation families share ONE pool, routed by placeholder signature through
RoboTwin's real filter_instructions:
  - beside : {A}=mover, {B}=reference
  - on-top : {A}=mover, {C}=reference
The reference key ({B} vs {C}) is what keeps the families un-mixable, so the
central check here is ROUTING: a beside episode (info has {A},{B},{a}) must select
ONLY beside frames and ZERO on-top frames, and vice-versa. Also checks seen/unseen
disjointness and the controlled literal "the {color} {noun}" injection for both
object slots.

    python tests/place_relative/test_instructions.py

(no simulator needed, but run in the RoboTwin env for the yaml import inside the
generate_episode_instructions module).
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

# beside episode names the reference as {B}, on-top names it as {C}; mover always {A}.
BESIDE = {"{A}": "the red mouse", "{B}": "the green plate", "{a}": "left"}
ONTOP = {"{A}": "the red mouse", "{C}": "the green plate", "{a}": "left"}

data = json.load(open(_JSON))
SEEN, UNSEEN = data["seen"], data["unseen"]


def _sig(t):
    ph = set(re.findall(r"{([^}]+)}", t))
    ph.discard("a")
    return frozenset(ph)


def is_beside(t):
    return _sig(t) == frozenset({"A", "B"})


def is_ontop(t):
    return _sig(t) == frozenset({"A", "C"})


_results = []


def _check(name, ok, note=""):
    _results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


# 1. Every template is exactly one of the two allowed signatures (mover {A} + one ref).
for pool_name, pool in [("seen", SEEN), ("unseen", UNSEEN)]:
    bad = [t for t in pool if not (is_beside(t) or is_ontop(t))]
    _check(f"{pool_name}: every template is {{A,B}} or {{A,C}}", not bad, note=f"offenders={bad[:3]}")

# 2. seen ∩ unseen = ∅ (IF requires zero train/eval template overlap).
s, u = set(SEEN), set(UNSEEN)
_check("seen∩unseen = empty", s.isdisjoint(u), note=f"overlap={len(s & u)}")

# 3. Both families present in BOTH seen and unseen (else one relation has no held-out set).
for pool_name, pool in [("seen", SEEN), ("unseen", UNSEEN)]:
    nb, no = sum(map(is_beside, pool)), sum(map(is_ontop, pool))
    _check(f"{pool_name}: has beside AND on-top frames", nb > 0 and no > 0, note=f"beside={nb} ontop={no}")

# 4. ROUTING (the core mechanism): beside params select exactly the beside frames and
#    NONE of the on-top frames; on-top params do the mirror. Cross-leak == broken task.
for pool_name, pool in [("seen", SEEN), ("unseen", UNSEEN)]:
    nb, no = sum(map(is_beside, pool)), sum(map(is_ontop, pool))
    fb = filter_instructions(list(pool), BESIDE)
    fo = filter_instructions(list(pool), ONTOP)
    _check(f"{pool_name}: beside params -> only beside frames",
           len(fb) == nb and all(is_beside(t) for t in fb), note=f"got {len(fb)}/{nb}")
    _check(f"{pool_name}: on-top params -> only on-top frames",
           len(fo) == no and all(is_ontop(t) for t in fo), note=f"got {len(fo)}/{no}")

# 5. Literal injection: the correct object phrases render verbatim for each relation,
#    with no leftover braces and no "the the".
for pool_name, pool in [("seen", SEEN), ("unseen", UNSEEN)]:
    bad = []
    for t in pool:
        params = BESIDE if is_beside(t) else ONTOP
        out = replace_placeholders(t, dict(params))
        if ("red mouse" not in out) or ("green plate" not in out) or ("{" in out) or ("the the" in out):
            bad.append(out)
    _check(f"{pool_name}: literal object phrases render cleanly", not bad, note=f"offenders={bad[:2]}")

print(f"\n==== {sum(_results)}/{len(_results)} passed ====")
sys.exit(0 if _results and all(_results) else 1)
