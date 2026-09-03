#!/usr/bin/env python3
"""Static object-familiarity pool, metadata, and seed-schedule invariants."""
import ast
import json
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from tasks.envs._pick_diverse_object_pool import (  # noqa: E402
    APPLE_STABILITY_FAMILY_ORDER,
    APPLE_STABILITY_POSE_FAMILIES,
    APPLE_STABILITY_THRESHOLDS,
    APPLE_RADIUS_FIRST_RESCUE_SET,
    EXPERIMENTAL_PROBE_CANDIDATE_SETS,
    EXPERIMENTAL_PROBE_PLACEMENT_POLICIES,
    MANUAL_UNSEEN_CANDIDATES,
    PROBE_UNSEEN_CANDIDATES,
    RAW_TASK_SEEN_ASSETS,
    SEEN_POOL,
    UNSEEN_CANDIDATES,
    UNSEEN_POOL,
    _apple_stability_entry,
    _replacement_pool,
    familiarity_for_seed,
    iter_variants,
    target_for_seed,
)

ASSETS = os.path.join(REPO, "third_party", "robotwin", "assets", "objects")
ENV_PATH = os.path.join(REPO, "tasks", "envs", "pick_diverse_object.py")
RESULTS = []


def check(name, condition, note=""):
    ok = bool(condition)
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


def rotate_vector(quaternion, vector):
    w, x, y, z = quaternion
    vx, vy, vz = vector
    # Unit-quaternion rotation matrix, kept local so this static test has no
    # simulator or transforms3d dependency.
    return (
        (1 - 2 * (y * y + z * z)) * vx + 2 * (x * y - z * w) * vy
        + 2 * (x * z + y * w) * vz,
        2 * (x * y + z * w) * vx + (1 - 2 * (x * x + z * z)) * vy
        + 2 * (y * z - x * w) * vz,
        2 * (x * z - y * w) * vx + 2 * (y * z + x * w) * vy
        + (1 - 2 * (x * x + y * y)) * vz,
    )


def valid_grasp_metadata(asset, model_id):
    path = os.path.join(ASSETS, asset, f"model_data{model_id}.json")
    if not os.path.isfile(path):
        return False, "missing metadata"
    with open(path) as handle:
        data = json.load(handle)
    visual = os.path.join(ASSETS, asset, "visual", f"base{model_id}.glb")
    collision = os.path.join(ASSETS, asset, "collision", f"base{model_id}.glb")
    groups = data.get("contact_points_group") or []
    masks = data.get("contact_points_mask") or []
    valid_groups = bool(groups) and (not masks or any(bool(x) for x in masks))
    ok = (
        data.get("stable") is True
        and os.path.isfile(visual)
        and os.path.isfile(collision)
        and valid_groups
    )
    return ok, (
        f"stable={data.get('stable')} visual={os.path.isfile(visual)} "
        f"collision={os.path.isfile(collision)} groups={len(groups)} masks={masks}"
    )


check("raw-task Seen taxonomy has 51 categories", len(RAW_TASK_SEEN_ASSETS) == 51,
      f"got={len(RAW_TASK_SEEN_ASSETS)}")
check("Seen task pool has 12 nouns / 16 variants",
      len(SEEN_POOL) == 12 and sum(1 for _ in iter_variants(SEEN_POOL)) == 16)
check("Unseen shortlist has 14 nouns / 54 variants",
      len(UNSEEN_CANDIDATES) == 14
      and sum(1 for _ in iter_variants(UNSEEN_CANDIDATES)) == 54)
check("human-facing candidate nouns match reviewed geometry",
      "drink bottle" in UNSEEN_CANDIDATES
      and "hand bell" in UNSEEN_CANDIDATES
      and "drink carton" not in UNSEEN_CANDIDATES
      and "call bell" not in UNSEEN_CANDIDATES)
check("manual follow-up is separate from the 14/54 metadata shortlist",
      set(MANUAL_UNSEEN_CANDIDATES) == {"notebook", "paintbrush"}
      and len(PROBE_UNSEEN_CANDIDATES) == 16
      and not (set(MANUAL_UNSEEN_CANDIDATES) & set(UNSEEN_CANDIDATES)))
check("manual follow-up uses explicit contact poses",
      all(entry["grasp_kwargs"].get("contact_point_id") is not None
          for entry in MANUAL_UNSEEN_CANDIDATES.values()))

speaker_experiment = EXPERIMENTAL_PROBE_CANDIDATE_SETS["speaker-098-base3"]
check("production speaker remains the confirmed 055 exact variant",
      UNSEEN_POOL["speaker"]["asset"] == "055_small-speaker"
      and UNSEEN_POOL["speaker"]["model_ids"] == (1,))
check("098 experiment preserves the four production nouns",
      tuple(speaker_experiment) == tuple(UNSEEN_POOL)
      and all(speaker_experiment[noun] == UNSEEN_POOL[noun]
              for noun in UNSEEN_POOL if noun != "speaker"))
experiment_entry = speaker_experiment["speaker"]
experiment_config = experiment_entry["actor_config"]
check("098 experiment replaces only speaker/base3",
      experiment_entry["asset"] == "098_speaker"
      and experiment_entry["model_ids"] == (3,)
      and experiment_entry["asset"] not in RAW_TASK_SEEN_ASSETS)
check("098 experiment has a finite positive 0.05 scale",
      experiment_entry["scale"] == (0.05, 0.05, 0.05)
      and all(math.isfinite(value) and value > 0
              for value in experiment_entry["scale"])
      and experiment_config["scale"] == experiment_entry["scale"])
contact_poses = experiment_config["contact_points_pose"]
contact_groups = experiment_config["contact_points_group"]
valid_contact_poses = (
    len(contact_poses) == 8
    and all(
        len(matrix) == 4
        and all(len(row) == 4 and all(math.isfinite(value) for value in row)
                for row in matrix)
        and tuple(matrix[3]) == (0.0, 0.0, 0.0, 1.0)
        for matrix in contact_poses
    )
)
check("098 experiment injects eight valid homogeneous contact matrices",
      valid_contact_poses)
check("098 experiment contact groups cover all matrices",
      contact_groups == ((0, 1, 2, 3), (4, 5, 6, 7))
      and experiment_config["contact_points_mask"] == (True, True)
      and sorted(index for group in contact_groups for index in group) == list(range(8)))
with open(os.path.join(ASSETS, "098_speaker", "model_data3.json")) as handle:
    source_098_metadata = json.load(handle)
check("098 source metadata remains scale/contact-free",
      "scale" not in source_098_metadata
      and not source_098_metadata.get("contact_points_pose")
      and source_098_metadata.get("stable") is True)

expected_unseen_exact = {
    "dumbbell": ("052_dumbbell", (0,)),
    "speaker": ("055_small-speaker", (1,)),
    "wooden mallet": ("084_woodenmallet", (3,)),
    "paintbrush": ("093_brush-pen", (1,)),
}
check("Apple experiment does not change the production Unseen pool",
      {noun: (entry["asset"], entry["model_ids"])
       for noun, entry in UNSEEN_POOL.items()} == expected_unseen_exact)
check("Apple remains absent from production and maintained candidate pools",
      all(entry["asset"] != "035_apple"
          for entry in {**SEEN_POOL, **PROBE_UNSEEN_CANDIDATES,
                        **UNSEEN_POOL}.values()))
check("Apple is raw-task Unseen", "035_apple" not in RAW_TASK_SEEN_ASSETS)

bad_apple_metadata = []
for model_id in (0, 1):
    metadata_path = os.path.join(ASSETS, "035_apple", f"model_data{model_id}.json")
    with open(metadata_path) as handle:
        metadata = json.load(handle)
    matrices = metadata.get("contact_points_pose") or []
    matrix_ok = (
        len(matrices) == 4
        and all(
            len(matrix) == 4
            and all(len(row) == 4 and all(math.isfinite(value) for value in row)
                    for row in matrix)
            and tuple(matrix[3]) == (0.0, 0.0, 0.0, 1.0)
            for matrix in matrices
        )
    )
    if not (
        metadata.get("stable") is False
        and tuple(metadata.get("scale", ())) == (0.7, 0.7, 0.7)
        and matrix_ok
        and metadata.get("contact_points_group") == [[0, 1, 2, 3]]
        and metadata.get("contact_points_mask") == [True]
        and os.path.isfile(os.path.join(ASSETS, "035_apple", "visual",
                                        f"base{model_id}.glb"))
        and os.path.isfile(os.path.join(ASSETS, "035_apple", "collision",
                                        f"base{model_id}.glb"))
    ):
        bad_apple_metadata.append(model_id)
check("Apple source variants retain native stable=false grasp metadata",
      not bad_apple_metadata, f"bad={bad_apple_metadata}")

bad_apple_sets = []
expected_apple_nouns = ("apple", "speaker", "wooden mallet", "paintbrush")
for model_id in (1, 0):
    for family_name in APPLE_STABILITY_FAMILY_ORDER:
        set_name = f"apple-035-base{model_id}-{family_name}"
        pool = EXPERIMENTAL_PROBE_CANDIDATE_SETS.get(set_name)
        if pool is None or tuple(pool) != expected_apple_nouns:
            bad_apple_sets.append(f"{set_name}: nouns")
            continue
        entry = pool["apple"]
        spec = entry.get("stability_probe", {})
        family = APPLE_STABILITY_POSE_FAMILIES[family_name]
        quaternion = entry["rest_qpos"]
        norm = math.sqrt(sum(value * value for value in quaternion))
        mapped_axis = rotate_vector(quaternion, family["support_axis"])
        yaw_axes = [index for index, value in enumerate(entry["rotate_lim"])
                    if abs(value) > 1e-12]
        support_axes = [index for index, value in enumerate(family["support_axis"])
                        if abs(value) > 1e-12]
        expected_radius = 0.055 if model_id == 1 else 0.060
        if not (
            entry["asset"] == "035_apple"
            and entry["model_ids"] == (model_id,)
            and "scale" not in entry
            and "actor_config" not in entry
            and math.isclose(entry["placement_radius"], expected_radius)
            and math.isclose(norm, 1.0, abs_tol=1e-9)
            and all(math.isfinite(value) for value in quaternion)
            and all(math.isclose(value, expected, abs_tol=1e-9)
                    for value, expected in zip(mapped_axis, (0.0, 0.0, 1.0)))
            and yaw_axes == support_axes
            and spec.get("variant") == model_id
            and spec.get("pose_family") == family_name
            and tuple(spec.get("support_axis", ())) == family["support_axis"]
            and all(spec.get(key) == value
                    for key, value in APPLE_STABILITY_THRESHOLDS.items())
            and all(pool[noun] == UNSEEN_POOL[noun]
                    for noun in expected_apple_nouns if noun != "apple")
        ):
            bad_apple_sets.append(set_name)
check("Apple variants expose ten isolated natural-pose probe sets",
      not bad_apple_sets, f"bad={bad_apple_sets}")
historical_apple_sets = {
    f"apple-035-base{model_id}-{family_name}"
    for model_id in (1, 0)
    for family_name in APPLE_STABILITY_FAMILY_ORDER
}
check("old ten Apple sets remain distinct from the fresh rescue",
      len(historical_apple_sets) == 10
      and APPLE_RADIUS_FIRST_RESCUE_SET not in historical_apple_sets
      and historical_apple_sets <= set(EXPERIMENTAL_PROBE_CANDIDATE_SETS))
check("only the fresh Apple rescue is bound to radius-first placement",
      EXPERIMENTAL_PROBE_PLACEMENT_POLICIES
      == {APPLE_RADIUS_FIRST_RESCUE_SET: "radius-first"})
rescue_pool = EXPERIMENTAL_PROBE_CANDIDATE_SETS[APPLE_RADIUS_FIRST_RESCUE_SET]
old_y_pos_pool = EXPERIMENTAL_PROBE_CANDIDATE_SETS[
    "apple-035-base1-y-pos-up"
]
check("fresh rescue changes placement policy, not scene or Apple physics",
      tuple(rescue_pool) == expected_apple_nouns
      and rescue_pool == old_y_pos_pool)
rescue_targets = [
    target_for_seed(seed, rescue_pool)[0]
    for seed in range(26001, 26016, 2)
]
check("rescue coexistence seeds freeze two complete target cycles",
      rescue_targets
      == ["apple", "speaker", "wooden mallet", "paintbrush"] * 2,
      f"got={rescue_targets}")

fail_closed = []
for label, action in (
    ("unknown family", lambda: _apple_stability_entry(1, "missing")),
    ("missing replacement", lambda: _replacement_pool(
        UNSEEN_POOL, "missing", "apple", _apple_stability_entry(1, "y-pos-up")
    )),
    ("noun collision", lambda: _replacement_pool(
        UNSEEN_POOL, "dumbbell", "speaker", _apple_stability_entry(1, "y-pos-up")
    )),
):
    try:
        action()
    except ValueError:
        continue
    fail_closed.append(label)
check("experimental replacement and Apple family helpers fail closed",
      not fail_closed, f"bad={fail_closed}")

bad_arm_kwargs = []
for noun, entry in {**SEEN_POOL, **PROBE_UNSEEN_CANDIDATES}.items():
    arm_kwargs = entry.get("grasp_kwargs_by_arm", {})
    if set(arm_kwargs) - {"left", "right"}:
        bad_arm_kwargs.append(f"{noun}: invalid arms={sorted(arm_kwargs)}")
    for arm, kwargs in arm_kwargs.items():
        contact_id = kwargs.get("contact_point_id")
        if contact_id is not None and (not isinstance(contact_id, int) or contact_id < 0):
            bad_arm_kwargs.append(f"{noun}/{arm}: contact_point_id={contact_id!r}")
check("per-arm grasp overrides have valid structure", not bad_arm_kwargs,
      f"bad={bad_arm_kwargs}")

seen_assets = {entry["asset"] for entry in SEEN_POOL.values()}
candidate_assets = {entry["asset"] for entry in PROBE_UNSEEN_CANDIDATES.values()}
check("all selected Seen assets occur in raw tasks", seen_assets <= RAW_TASK_SEEN_ASSETS,
      f"bad={sorted(seen_assets - RAW_TASK_SEEN_ASSETS)}")
check("all probe candidate assets are raw-task Unseen",
      candidate_assets.isdisjoint(RAW_TASK_SEEN_ASSETS),
      f"overlap={sorted(candidate_assets & RAW_TASK_SEEN_ASSETS)}")
check("Seen and candidate nouns are each unique", len(SEEN_POOL) == len(set(SEEN_POOL))
      and len(UNSEEN_CANDIDATES) == len(set(UNSEEN_CANDIDATES)))

bad_metadata = []
for noun, asset, model_id, _entry in iter_variants(UNSEEN_CANDIDATES):
    ok, note = valid_grasp_metadata(asset, model_id)
    if not ok:
        bad_metadata.append(f"{noun}/{asset}base{model_id}: {note}")
check("all 54 candidate variants retain stable+grasp metadata", not bad_metadata,
      f"bad={bad_metadata[:3]}")

# Adjacent raw seeds strictly alternate object familiarity. Each group's own seed
# subsequence cycles nouns in manifest order before cycling exact variants.
check("seed parity alternates Seen/Unseen",
      [familiarity_for_seed(seed) for seed in range(8)]
      == ["seen", "unseen"] * 4)
seen_cycle = [target_for_seed(seed, SEEN_POOL)[0] for seed in range(0, 2 * len(SEEN_POOL), 2)]
unseen_cycle = [
    target_for_seed(seed, UNSEEN_CANDIDATES)[0]
    for seed in range(1, 2 * len(UNSEEN_CANDIDATES), 2)
]
check("Seen target nouns cycle in manifest order", seen_cycle == list(SEEN_POOL))
check("Unseen target nouns cycle in manifest order", unseen_cycle == list(UNSEEN_CANDIDATES))

# Probe hooks must stay disabled in the production class definition. Parse the source so
# this test remains simulator-free.
tree = ast.parse(open(ENV_PATH).read(), ENV_PATH)
class_node = next(node for node in tree.body
                  if isinstance(node, ast.ClassDef) and node.name == "pick_diverse_object")
override_names = {
    "FAMILIARITY_OVERRIDE", "TARGET_NOUN_OVERRIDE", "TARGET_MODEL_ID_OVERRIDE",
    "TARGET_SIDE_OVERRIDE", "POOL_OVERRIDE", "DISTRACTOR_NOUNS_OVERRIDE",
    "PLACEMENT_ORDER_OVERRIDE",
}
override_values = {}
for node in class_node.body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        name = node.targets[0].id
        if name in override_names:
            override_values[name] = ast.literal_eval(node.value)
check("all probe overrides default to None",
      override_values == {name: None for name in override_names},
      f"got={override_values}")

# This intentionally fails until real SAPIEN evidence has locked a usable pool.
check("production Unseen pool has at least four probed nouns", len(UNSEEN_POOL) >= 4,
      f"currently={len(UNSEEN_POOL)}")
locked_assets = {entry["asset"] for entry in UNSEEN_POOL.values()}
check("production Unseen pool stays raw-task Unseen",
      locked_assets.isdisjoint(RAW_TASK_SEEN_ASSETS))
for noun, entry in UNSEEN_POOL.items():
    candidate = PROBE_UNSEEN_CANDIDATES.get(noun)
    check(f"locked {noun}: exact IDs came from a documented probe candidate",
          candidate is not None
          and entry["asset"] == candidate["asset"]
          and set(entry["model_ids"]) <= set(candidate["model_ids"]))

print(f"\n==== {sum(RESULTS)}/{len(RESULTS)} passed ====")
sys.exit(0 if RESULTS and all(RESULTS) else 1)
