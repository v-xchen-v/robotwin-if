#!/usr/bin/env python3
"""Layer-A noun-only instruction-template invariants for pick_diverse_object."""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
while not os.path.isdir(os.path.join(REPO, "third_party", "robotwin")):
    parent = os.path.dirname(REPO)
    if parent == REPO:
        raise RuntimeError("could not locate repo root")
    REPO = parent

JSON_PATH = os.path.join(REPO, "tasks", "task_instruction", "pick_diverse_object.json")
sys.path.insert(0, os.path.join(REPO, "third_party", "robotwin", "description", "utils"))
from generate_episode_instructions import filter_instructions, replace_placeholders  # noqa: E402

EXPECTED_TEMPLATE_COUNTS = {"seen": 12, "unseen": 4}
PARAMS = {"{A}": "the wooden mallet", "{a}": "left"}

with open(JSON_PATH) as handle:
    data = json.load(handle)
TEMPLATE_SEEN = data["seen"]
TEMPLATE_UNSEEN = data["unseen"]
RESULTS = []


def check(name, condition, note=""):
    ok = bool(condition)
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


for split_name, templates in (("seen", TEMPLATE_SEEN), ("unseen", TEMPLATE_UNSEEN)):
    no_target = [template for template in templates if "{A}" not in template]
    stray = [template for template in templates if "{B}" in template or "{C}" in template]
    check(f"template-{split_name}: every template has {{A}}", not no_target,
          f"offenders={no_target[:3]}")
    check(f"template-{split_name}: no stray {{B}}/{{C}}", not stray,
          f"offenders={stray[:3]}")

seen_set = set(TEMPLATE_SEEN)
unseen_set = set(TEMPLATE_UNSEEN)
check("template seen/unseen split is disjoint", seen_set.isdisjoint(unseen_set),
      f"overlap={len(seen_set & unseen_set)}")

for split_name, templates in (("seen", TEMPLATE_SEEN), ("unseen", TEMPLATE_UNSEEN)):
    filtered = filter_instructions(list(templates), PARAMS)
    check(
        f"template-{split_name}: real filter preserves expected count",
        len(filtered) == EXPECTED_TEMPLATE_COUNTS[split_name],
        f"got={len(filtered)}",
    )

for split_name, templates in (("seen", TEMPLATE_SEEN), ("unseen", TEMPLATE_UNSEEN)):
    bad = []
    for template in templates:
        output = replace_placeholders(template, dict(PARAMS))
        if "wooden mallet" not in output or "{" in output or "the the" in output:
            bad.append(output)
    check(f"template-{split_name}: literal noun phrase renders cleanly", not bad,
          f"offenders={bad[:2]}")

schema = data.get("schema", "")
check("schema distinguishes template split from object familiarity",
      "instruction-template split" in schema and "object-familiarity split" in schema)
check("schema documents noun-only literal", "the {noun}" in schema)

print(f"\n==== {sum(RESULTS)}/{len(RESULTS)} passed ====")
sys.exit(0 if RESULTS and all(RESULTS) else 1)
