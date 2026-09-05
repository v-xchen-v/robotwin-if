#!/usr/bin/env python3
"""Real-SAPIEN production wiring checks for Pick-Diverse-Object.

This deliberately does not retry failed setup with a different seed: changing the raw
seed would hide parity, scheduling, placement, or determinism regressions.
"""
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RT = os.path.join(REPO, "third_party", "robotwin")
os.chdir(RT)
sys.path[:0] = [os.path.join(RT, "script"), RT]

import collect_data as cd  # noqa: E402
from envs._pick_diverse_object_pool import (  # noqa: E402
    SEEN_POOL,
    UNSEEN_POOL,
    familiarity_for_seed,
    target_for_seed,
)


CAPTURE = {}
cd.run = lambda task, args: CAPTURE.update(task=task, args=args)
cd.main(task_name="pick_diverse_object", task_config="demo_clean")
TASK = CAPTURE["task"]
ARGS = dict(CAPTURE["args"])
ARGS["render_freq"] = 0
with open(os.path.join(RT, "assets", "objects", "035_apple", "model_data1.json")) as handle:
    NATIVE_APPLE_CONFIG = json.load(handle)
RESULTS = []
OVERRIDES = (
    "FAMILIARITY_OVERRIDE",
    "TARGET_NOUN_OVERRIDE",
    "TARGET_MODEL_ID_OVERRIDE",
    "TARGET_SIDE_OVERRIDE",
    "POOL_OVERRIDE",
    "DISTRACTOR_NOUNS_OVERRIDE",
)


def check(name, condition, note=""):
    ok = bool(condition)
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


def clear_overrides():
    for name in OVERRIDES:
        setattr(TASK, name, None)


def current_signature():
    records = []
    for item in TASK.scene_objects:
        pose = item["actor"].get_pose()
        records.append((
            item["role"],
            item["noun"],
            item["modelname"],
            int(item["model_id"]),
            int(item["placement_index"]),
            tuple(np.round(np.asarray(pose.p, dtype=float), 5)),
            tuple(np.round(np.asarray(pose.q, dtype=float), 5)),
        ))
    return tuple(sorted(records))


def setup_signature(seed):
    clear_overrides()
    TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
    return current_signature()


if len(UNSEEN_POOL) < 4:
    raise RuntimeError(
        "UNSEEN_POOL is not locked; production wiring requires four Unseen nouns"
    )

for seed in range(8):
    expected_familiarity = familiarity_for_seed(seed)
    pool = SEEN_POOL if expected_familiarity == "seen" else UNSEEN_POOL
    expected_noun, expected_asset, expected_model_id = target_for_seed(seed, pool)

    try:
        first = setup_signature(seed)
        actual_familiarity = TASK.scene_familiarity
        actual_target = (TASK.target_noun, TASK.target_modelname, int(TASK.target_id))
        nouns = [item["noun"] for item in TASK.scene_objects]
        memberships = [item["noun"] in pool for item in TASK.scene_objects]
        placement_policy = TASK.placement_policy
        placement_radii = [pool[noun]["placement_radius"] for noun in nouns]
        second = setup_signature(seed)
    except Exception as exc:
        check(f"seed {seed}: setup succeeds", False,
              note=f"{type(exc).__name__}: {exc}")
        continue

    check(f"seed {seed}: parity selects {expected_familiarity}",
          actual_familiarity == expected_familiarity,
          note=f"actual={actual_familiarity}")
    check(f"seed {seed}: scheduled target matches manifest",
          actual_target == (expected_noun, expected_asset, expected_model_id),
          note=f"actual={actual_target}")
    check(f"seed {seed}: four distinct nouns",
          len(nouns) == 4 and len(set(nouns)) == 4,
          note=f"nouns={nouns}")
    check(f"seed {seed}: scene is familiarity-homogeneous", all(memberships),
          note=f"memberships={memberships}")
    check(f"seed {seed}: production placement remains radius-first",
          placement_policy == "radius-first"
          and placement_radii == sorted(placement_radii, reverse=True),
          note=f"policy={placement_policy} radii={placement_radii}")
    check(f"seed {seed}: repeated setup is deterministic", first == second)

production_apple_configs = []
for seed, expected_role in ((1, "distractor"), (3, "target")):
    try:
        setup_signature(seed)
        apple_record = next(
            item for item in TASK.scene_objects if item["noun"] == "apple"
        )
    except Exception as exc:
        check(f"production Apple seed {seed}: setup succeeds", False,
              note=f"{type(exc).__name__}: {exc}")
        continue
    config = apple_record["actor"].config
    production_apple_configs.append(config)
    translations = [
        tuple(row[3] for row in matrix[:3])
        for matrix in config["contact_points_pose"]
    ]
    check(f"production Apple seed {seed}: expected scene role",
          apple_record["role"] == expected_role,
          note=f"actual={apple_record['role']}")
    check(f"production Apple seed {seed}: body-centered top contacts applied",
          len(config["contact_points_pose"]) == 4
          and config["contact_points_group"] == [[0, 1, 2, 3]]
          and config["contact_points_mask"] == [True]
          and all(translation == tuple(NATIVE_APPLE_CONFIG["center"])
                  for translation in translations))
check("production Apple setups receive independent actor configs",
      len(production_apple_configs) == 2
      and production_apple_configs[0] is not production_apple_configs[1])
with open(os.path.join(RT, "assets", "objects", "035_apple", "model_data1.json")) as handle:
    check("production setup leaves native Apple metadata unchanged",
          json.load(handle) == NATIVE_APPLE_CONFIG)

clear_overrides()
print(f"\n==== {sum(RESULTS)}/{len(RESULTS)} passed ====")
sys.exit(0 if RESULTS and all(RESULTS) else 1)
