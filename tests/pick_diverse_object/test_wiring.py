#!/usr/bin/env python3
"""Real-SAPIEN production wiring checks for Pick-Diverse-Object.

This deliberately does not retry failed setup with a different seed: changing the raw
seed would hide parity, scheduling, placement, or determinism regressions.
"""
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RT = os.path.join(REPO, "third_party", "robotwin")
os.chdir(RT)
sys.path[:0] = [os.path.join(RT, "script"), RT]

import collect_data as cd  # noqa: E402
from envs._pick_diverse_object_pool import (  # noqa: E402
    APPLE_STABILITY_FAMILY_ORDER,
    APPLE_RADIUS_FIRST_RESCUE_SET,
    EXPERIMENTAL_PROBE_CANDIDATE_SETS,
    EXPERIMENTAL_PROBE_PLACEMENT_POLICIES,
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
RESULTS = []
OVERRIDES = (
    "FAMILIARITY_OVERRIDE",
    "TARGET_NOUN_OVERRIDE",
    "TARGET_MODEL_ID_OVERRIDE",
    "TARGET_SIDE_OVERRIDE",
    "POOL_OVERRIDE",
    "DISTRACTOR_NOUNS_OVERRIDE",
    "PLACEMENT_ORDER_OVERRIDE",
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

experiment_name = "speaker-098-base3"
experiment_pool = EXPERIMENTAL_PROBE_CANDIDATE_SETS[experiment_name]
experiment_configs = []
for side, seed in (("left", 9820), ("right", 9821)):
    clear_overrides()
    TASK.FAMILIARITY_OVERRIDE = "unseen"
    TASK.POOL_OVERRIDE = experiment_pool
    TASK.TARGET_NOUN_OVERRIDE = "speaker"
    TASK.TARGET_MODEL_ID_OVERRIDE = 3
    TASK.TARGET_SIDE_OVERRIDE = side
    TASK.DISTRACTOR_NOUNS_OVERRIDE = (
        "dumbbell", "wooden mallet", "paintbrush",
    )
    try:
        TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
    except Exception as exc:
        check(f"098 speaker {side}: setup succeeds", False,
              note=f"{type(exc).__name__}: {exc}")
        continue

    actual_side = "right" if TASK.target.get_pose().p[0] > 0 else "left"
    nouns = {item["noun"] for item in TASK.scene_objects}
    experiment_configs.append(TASK.target.config)
    check(f"098 speaker {side}: exact target is loaded",
          TASK.target_modelname == "098_speaker" and int(TASK.target_id) == 3)
    check(f"098 speaker {side}: requested side is honored", actual_side == side,
          note=f"actual={actual_side}")
    check(f"098 speaker {side}: replacement scene has production nouns",
          nouns == set(experiment_pool), note=f"nouns={sorted(nouns)}")
    check(f"098 speaker {side}: actor config is injected",
          TASK.target.config is not None
          and tuple(TASK.target.config["scale"]) == (0.05, 0.05, 0.05)
          and len(TASK.target.config["contact_points_pose"]) == 8)

check("098 repeated setups receive independent actor configs",
      len(experiment_configs) == 2
      and experiment_configs[0] is not experiment_configs[1])

expected_apple_nouns = {"apple", "speaker", "wooden mallet", "paintbrush"}
for index, family_name in enumerate(APPLE_STABILITY_FAMILY_ORDER):
    set_name = f"apple-035-base1-{family_name}"
    experiment_pool = EXPERIMENTAL_PROBE_CANDIDATE_SETS[set_name]
    side = ("left", "right")[index % 2]
    clear_overrides()
    TASK.FAMILIARITY_OVERRIDE = "unseen"
    TASK.POOL_OVERRIDE = experiment_pool
    TASK.TARGET_NOUN_OVERRIDE = "apple"
    TASK.TARGET_MODEL_ID_OVERRIDE = 1
    TASK.TARGET_SIDE_OVERRIDE = side
    TASK.DISTRACTOR_NOUNS_OVERRIDE = (
        "speaker", "wooden mallet", "paintbrush",
    )
    try:
        TASK.setup_demo(now_ep_num=0, seed=10600 + index, **ARGS)
    except Exception as exc:
        check(f"Apple {family_name}: setup succeeds", False,
              note=f"{type(exc).__name__}: {exc}")
        continue

    target_record = next(
        item for item in TASK.scene_objects if item["role"] == "target"
    )
    actual_side = "right" if TASK.target.get_pose().p[0] > 0 else "left"
    nouns = {item["noun"] for item in TASK.scene_objects}
    check(f"Apple {family_name}: exact source actor is loaded",
          TASK.target_modelname == "035_apple" and int(TASK.target_id) == 1)
    check(f"Apple {family_name}: requested side is honored", actual_side == side,
          note=f"actual={actual_side}")
    check(f"Apple {family_name}: isolated scene has four expected nouns",
          nouns == expected_apple_nouns, note=f"nouns={sorted(nouns)}")
    check(f"Apple {family_name}: historical forced probe stays target-first",
          TASK.placement_policy == "target-first"
          and TASK.scene_objects[0]["role"] == "target",
          note=f"policy={TASK.placement_policy}")
    check(f"Apple {family_name}: spawn pose is recorded",
          len(target_record.get("spawn_position", ())) == 3
          and len(target_record.get("spawn_quaternion", ())) == 4)
    check(f"Apple {family_name}: source metadata remains authoritative",
          TASK.target.config is not None
          and tuple(TASK.target.config["scale"]) == (0.7, 0.7, 0.7)
          and len(TASK.target.config["contact_points_pose"]) == 4
          and TASK.target.config["stable"] is False)

rescue_pool = EXPERIMENTAL_PROBE_CANDIDATE_SETS[APPLE_RADIUS_FIRST_RESCUE_SET]
rescue_signatures = {}
for side, seed in (("left", 10700), ("right", 10701)):
    def setup_rescue():
        clear_overrides()
        TASK.FAMILIARITY_OVERRIDE = "unseen"
        TASK.POOL_OVERRIDE = rescue_pool
        TASK.TARGET_NOUN_OVERRIDE = "apple"
        TASK.TARGET_MODEL_ID_OVERRIDE = 1
        TASK.TARGET_SIDE_OVERRIDE = side
        TASK.DISTRACTOR_NOUNS_OVERRIDE = (
            "speaker", "wooden mallet", "paintbrush",
        )
        TASK.PLACEMENT_ORDER_OVERRIDE = (
            EXPERIMENTAL_PROBE_PLACEMENT_POLICIES[APPLE_RADIUS_FIRST_RESCUE_SET]
        )
        TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)

    try:
        setup_rescue()
        first = current_signature()
        actual_side = "right" if TASK.target.get_pose().p[0] > 0 else "left"
        placement_sequence = [item["noun"] for item in TASK.scene_objects]
        placement_indices = [item["placement_index"] for item in TASK.scene_objects]
        source_config = TASK.target.config
        setup_rescue()
        second = current_signature()
    except Exception as exc:
        check(f"Apple rescue {side}: setup succeeds", False,
              note=f"{type(exc).__name__}: {exc}")
        continue

    rescue_signatures[side] = first
    check(f"Apple rescue {side}: exact target and side are honored",
          TASK.target_modelname == "035_apple"
          and int(TASK.target_id) == 1
          and actual_side == side,
          note=f"actual_side={actual_side}")
    check(f"Apple rescue {side}: radius-first creation order is exact",
          TASK.placement_policy == "radius-first"
          and placement_sequence
          == ["wooden mallet", "paintbrush", "speaker", "apple"]
          and placement_indices == [0, 1, 2, 3],
          note=f"sequence={placement_sequence}")
    check(f"Apple rescue {side}: source metadata remains authoritative",
          source_config is not None
          and tuple(source_config["scale"]) == (0.7, 0.7, 0.7)
          and len(source_config["contact_points_pose"]) == 4
          and source_config["stable"] is False)
    check(f"Apple rescue {side}: repeated setup is deterministic", first == second)

clear_overrides()
TASK.FAMILIARITY_OVERRIDE = "unseen"
TASK.POOL_OVERRIDE = rescue_pool
TASK.TARGET_NOUN_OVERRIDE = "apple"
TASK.TARGET_MODEL_ID_OVERRIDE = 1
TASK.TARGET_SIDE_OVERRIDE = "left"
TASK.DISTRACTOR_NOUNS_OVERRIDE = ("speaker", "wooden mallet", "paintbrush")
TASK.PLACEMENT_ORDER_OVERRIDE = "unknown-policy"
try:
    TASK.setup_demo(now_ep_num=0, seed=10702, **ARGS)
except ValueError as exc:
    invalid_policy_rejected = "unknown placement order policy" in str(exc)
except Exception:
    invalid_policy_rejected = False
else:
    invalid_policy_rejected = False
check("unknown placement policy fails closed", invalid_policy_rejected)

clear_overrides()
print(f"\n==== {sum(RESULTS)}/{len(RESULTS)} passed ====")
sys.exit(0 if RESULTS and all(RESULTS) else 1)
