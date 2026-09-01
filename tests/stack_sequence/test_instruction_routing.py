#!/usr/bin/env python3
"""Layer-A instruction-routing test for stack_sequence (no sim needed).

The positional-slot invariant this task rests on:
  - {A}/{B}/{C} are ORDER slots (bottom/mid/top); the env fills them with the
    commanded colors per episode, so the SAME template pool must route under all
    6 permutations and render the order the env commanded.
  - Every template must fully name the order (contain {A}, {B}, {C}); a template
    that omits a slot would under-specify the sequence.

Checks, using RoboTwin's own filter/replace so this matches the real pipeline:
  1. every seen+unseen template contains all of {A},{B},{C} (full order named);
  2. no template contains an arm placeholder (order-only, keeps routing uniform);
  3. filter_instructions accepts ALL templates for the env's param set
     {A,B,C,a,b,c} (arm-free templates route via the omit-all-arms branch);
  4. the color->slot substitution renders the COMMANDED order: the canonical
     "Stack {C} on {B}, and {B} on {A}." reads red-bottom for perm0 and
     blue-bottom (reversed) for perm5.

Run inside the RoboTwin conda env, after ./bridge_tasks.sh:
    conda activate RoboTwin
    python tests/stack_sequence/test_instruction_routing.py
"""
import os
import sys
import json
import re

_REPO = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _parent = os.path.dirname(_REPO)
    if _parent == _REPO:
        raise RuntimeError("could not locate repo root")
    _REPO = _parent
_RT = os.path.join(_REPO, "third_party", "robotwin")
sys.path.insert(0, os.path.join(_RT, "description", "utils"))

from generate_episode_instructions import filter_instructions, replace_placeholders  # noqa: E402

JSON_PATH = os.path.join(_REPO, "tasks", "task_instruction", "stack_sequence.json")
with open(JSON_PATH) as f:
    POOL = json.load(f)
SEEN, UNSEEN = POOL["seen"], POOL["unseen"]
ALL = SEEN + UNSEEN

_results = []


def _record(name, ok, note=""):
    _results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


def placeholders(t):
    return set(re.findall(r"{([^}]+)}", t))


# (1) every template names the full order.
missing = [t for t in ALL if not {"A", "B", "C"}.issubset(placeholders(t))]
_record("all templates contain {A},{B},{C}", not missing,
        note=f"{len(missing)} missing" + (f": {missing[:2]}" if missing else ""))

# (2) no arm placeholders (order-only pool).
with_arm = [t for t in ALL if placeholders(t) & set("abcdefghijklmnopqrstuvwxyz")]
_record("no template uses an arm slot", not with_arm,
        note=f"{len(with_arm)} with arms" + (f": {with_arm[:2]}" if with_arm else ""))

# (3) routing: env emits {A,B,C,a,b,c}; every arm-free template must be accepted.
episode = {"{A}": "red block", "{B}": "green block", "{C}": "blue block",
           "{a}": "left", "{b}": "right", "{c}": "left"}
fs = filter_instructions(SEEN, episode)
fu = filter_instructions(UNSEEN, episode)
_record("all seen templates route", len(fs) == len(SEEN), note=f"{len(fs)}/{len(SEEN)}")
_record("all unseen templates route", len(fu) == len(UNSEEN), note=f"{len(fu)}/{len(UNSEEN)}")

# (4) color->slot substitution renders the commanded order.
canonical = "Stack {C} on {B}, and {B} on {A}."
perm0 = {"{A}": "red block", "{B}": "green block", "{C}": "blue block"}
perm5 = {"{A}": "blue block", "{B}": "green block", "{C}": "red block"}
r0 = replace_placeholders(canonical, perm0)
r5 = replace_placeholders(canonical, perm5)
_record("perm0 renders red-bottom",
        r0 == "Stack blue block on green block, and green block on red block.", note=r0)
_record("perm5 renders blue-bottom (reversed)",
        r5 == "Stack red block on green block, and green block on blue block.", note=r5)

print("\n==== summary ====")
print(f"{sum(_results)}/{len(_results)} passed")
sys.exit(0 if _results and all(_results) else 1)
