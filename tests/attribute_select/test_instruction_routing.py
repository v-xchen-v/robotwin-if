#!/usr/bin/env python3
"""Layer-A instruction-routing test for attribute_select (no sim needed).

The invariant: one {ADJ} slot carries the full referring phrase for the single
target object; the SAME template pool must route for every axis/value, and
render the phrase the env commanded. Templates must name exactly that one object
(contain {ADJ}) and carry no arm slot.

Checks, using RoboTwin's own filter/replace so this matches the real pipeline:
  1. every seen+unseen template contains {ADJ};
  2. no template contains an arm placeholder (single {ADJ} pool);
  3. filter_instructions accepts ALL templates for the env param set {ADJ};
  4. {ADJ} substitution renders the commanded phrase for each axis.

Run after ./bridge_tasks.sh, inside the RoboTwin conda env:
    python tests/attribute_select/test_instruction_routing.py
"""
import os
import sys
import json
import re

_REPO = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _p = os.path.dirname(_REPO)
    if _p == _REPO:
        raise RuntimeError("repo root not found")
    _REPO = _p
_RT = os.path.join(_REPO, "third_party", "robotwin")
sys.path.insert(0, os.path.join(_RT, "description", "utils"))

from generate_episode_instructions import filter_instructions, replace_placeholders  # noqa: E402

with open(os.path.join(_REPO, "tasks", "task_instruction", "attribute_select.json")) as f:
    POOL = json.load(f)
SEEN, UNSEEN = POOL["seen"], POOL["unseen"]
ALL = SEEN + UNSEEN

_res = []


def rec(name, ok, note=""):
    _res.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


def ph(t):
    return set(re.findall(r"{([^}]+)}", t))


# (1) every template names the target via {ADJ}.
missing = [t for t in ALL if "ADJ" not in ph(t)]
rec("all templates contain {ADJ}", not missing, note=f"{missing[:2]}" if missing else "")

# (2) no arm placeholders (single-{ADJ} pool, no arm axis).
with_arm = [t for t in ALL if ph(t) & set("abcdefghijklmnopqrstuvwxyz")]
rec("no template uses an arm slot", not with_arm, note=f"{with_arm[:2]}" if with_arm else "")

# (3) routing: env emits only {ADJ}; every template must be accepted.
episode = {"{ADJ}": "red block"}
fs = filter_instructions(SEEN, episode)
fu = filter_instructions(UNSEEN, episode)
rec("all seen templates route", len(fs) == len(SEEN), note=f"{len(fs)}/{len(SEEN)}")
rec("all unseen templates route", len(fu) == len(UNSEEN), note=f"{len(fu)}/{len(UNSEEN)}")

# (4) {ADJ} renders the commanded phrase per axis (one canonical template).
canon = "Pick up the {ADJ}."
cases = {
    "color(red)": ("red block", "Pick up the red block."),
    "decal(cat)": ("block with a cat on it", "Pick up the block with a cat on it."),
    "shape(bar)": ("long bar", "Pick up the long bar."),
    "size(big)": ("big block", "Pick up the big block."),
}
for label, (adj, expect) in cases.items():
    out = replace_placeholders(canon, {"{ADJ}": adj})
    rec(f"renders {label}", out == expect, note=out)

print(f"\n==== {sum(_res)}/{len(_res)} passed ====")
sys.exit(0 if _res and all(_res) else 1)
