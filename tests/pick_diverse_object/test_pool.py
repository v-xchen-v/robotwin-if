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
    APPLE_TOP_DOWN_CONTACT_ROTATIONS,
    MANUAL_UNSEEN_CANDIDATES,
    PROBE_UNSEEN_CANDIDATES,
    RAW_TASK_SEEN_ASSETS,
    SEEN_POOL,
    UNSEEN_CANDIDATES,
    UNSEEN_POOL,
    _apple_top_down_actor_config,
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
    return (
        (1 - 2 * (y * y + z * z)) * vx + 2 * (x * y - z * w) * vy
        + 2 * (x * z + y * w) * vz,
        2 * (x * y + z * w) * vx + (1 - 2 * (x * x + z * z)) * vy
        + 2 * (y * z - x * w) * vz,
        2 * (x * z - y * w) * vx + 2 * (y * z + x * w) * vy
        + (1 - 2 * (x * x + y * y)) * vz,
    )


def valid_rotation(rotation):
    rows = tuple(tuple(float(value) for value in row) for row in rotation)
    if len(rows) != 3 or any(len(row) != 3 for row in rows):
        return False
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    orthonormal = all(
        math.isclose(dot(rows[i], rows[j]), float(i == j), abs_tol=1e-9)
        for i in range(3)
        for j in range(3)
    )
    determinant = (
        rows[0][0] * (rows[1][1] * rows[2][2] - rows[1][2] * rows[2][1])
        - rows[0][1] * (rows[1][0] * rows[2][2] - rows[1][2] * rows[2][0])
        + rows[0][2] * (rows[1][0] * rows[2][1] - rows[1][1] * rows[2][0])
    )
    return orthonormal and math.isclose(determinant, 1.0, abs_tol=1e-9)


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
    valid_groups = bool(groups) and (not masks or any(bool(value) for value in masks))
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


numbered_assets = {
    name for name in os.listdir(ASSETS)
    if len(name) >= 4 and name[:3].isdigit() and name[3] == "_"
}
check("asset taxonomy has 120 numbered categories", len(numbered_assets) == 120,
      f"got={len(numbered_assets)}")
check("raw-task taxonomy splits into 51 Seen / 69 Unseen",
      len(RAW_TASK_SEEN_ASSETS) == 51
      and len(numbered_assets - RAW_TASK_SEEN_ASSETS) == 69)

EXPECTED_SEEN_EXACT = {
    "bottle": ("001_bottle", (13,)),
    "cup": ("021_cup", (0,)),
    "shoe": ("041_shoe", (8,)),
    "mug": ("039_mug", (0,)),
    "can": ("071_can", (2,)),
    "toy car": ("057_toycar", (5,)),
    "phone": ("077_phone", (1,)),
    "soap": ("107_soap", (0,)),
    "hamburger": ("006_hamburg", (0,)),
    "bread": ("075_bread", (5,)),
    "coffee box": ("113_coffee-box", (1,)),
    "mouse": ("047_mouse", (2,)),
}
actual_seen_exact = {
    noun: (entry["asset"], entry["model_ids"])
    for noun, entry in SEEN_POOL.items()
}
check("Seen pool has 12 nouns / 12 exact variants",
      len(SEEN_POOL) == 12 and sum(1 for _ in iter_variants(SEEN_POOL)) == 12)
check("Seen pool matches the reviewed exact-ID selection",
      actual_seen_exact == EXPECTED_SEEN_EXACT,
      note=f"actual={actual_seen_exact}")
check("phone/base1 uses its native resting orientation",
      SEEN_POOL["phone"]["rest_qpos"] == (0.5, 0.5, 0.5, 0.5))

check("Unseen metadata shortlist has 14 nouns / 54 variants",
      len(UNSEEN_CANDIDATES) == 14
      and sum(1 for _ in iter_variants(UNSEEN_CANDIDATES)) == 54)
check("human-facing shortlist nouns match reviewed geometry",
      "drink bottle" in UNSEEN_CANDIDATES
      and "hand bell" in UNSEEN_CANDIDATES
      and "drink carton" not in UNSEEN_CANDIDATES
      and "call bell" not in UNSEEN_CANDIDATES)
check("manual follow-up stays separate from the 14/54 shortlist",
      set(MANUAL_UNSEEN_CANDIDATES) == {"notebook", "paintbrush"}
      and len(PROBE_UNSEEN_CANDIDATES) == 16
      and not (set(MANUAL_UNSEEN_CANDIDATES) & set(UNSEEN_CANDIDATES)))
check("manual candidates select an existing contact pose explicitly",
      all(entry["grasp_kwargs"].get("contact_point_id") == 0
          for entry in MANUAL_UNSEEN_CANDIDATES.values()))

ENTRY_KEYS = {
    "asset", "model_ids", "rest_qpos", "rotate_rand", "rotate_lim",
    "grasp_strategy", "grasp_kwargs", "placement_radius",
}
all_entries = {
    **SEEN_POOL,
    **PROBE_UNSEEN_CANDIDATES,
    **{f"production:{noun}": entry for noun, entry in UNSEEN_POOL.items()},
}
bad_schema = {
    noun: sorted(set(entry) ^ ENTRY_KEYS)
    for noun, entry in all_entries.items()
    if set(entry) != ENTRY_KEYS
}
check("retained pool entries use only the production schema",
      not bad_schema, f"bad={bad_schema}")

EXPECTED_UNSEEN_EXACT = {
    "dumbbell": ("052_dumbbell", (0,)),
    "apple": ("035_apple", (1,)),
    "wooden mallet": ("084_woodenmallet", (3,)),
    "paintbrush": ("093_brush-pen", (1,)),
}
actual_unseen_exact = {
    noun: (entry["asset"], entry["model_ids"])
    for noun, entry in UNSEEN_POOL.items()
}
check("production Unseen pool has the final four exact variants in order",
      actual_unseen_exact == EXPECTED_UNSEEN_EXACT,
      note=f"actual={actual_unseen_exact}")
check("production Unseen pool stays raw-task Unseen",
      {entry["asset"] for entry in UNSEEN_POOL.values()}.isdisjoint(
          RAW_TASK_SEEN_ASSETS
      ))
check("Apple is absent from Seen and reusable candidate inventories",
      all(entry["asset"] != "035_apple"
          for entry in {**SEEN_POOL, **PROBE_UNSEEN_CANDIDATES}.values()))

apple_entry = UNSEEN_POOL["apple"]
check("production Apple locks canonical z-up top-grasp physics",
      apple_entry["rest_qpos"] == (1.0, 0.0, 0.0, 0.0)
      and apple_entry["rotate_rand"] is True
      and apple_entry["rotate_lim"] == (0.0, 0.0, math.pi)
      and apple_entry["grasp_strategy"] == "apple_top_down"
      and apple_entry["grasp_kwargs"] == {"pre_grasp_dis": 0.08}
      and math.isclose(apple_entry["placement_radius"], 0.055))
for noun, entry in UNSEEN_POOL.items():
    if noun == "apple":
        continue
    candidate = PROBE_UNSEEN_CANDIDATES.get(noun)
    check(f"locked {noun}: exact ID came from the retained candidate inventory",
          candidate is not None
          and entry["asset"] == candidate["asset"]
          and set(entry["model_ids"]) <= set(candidate["model_ids"]))

with open(os.path.join(ASSETS, "035_apple", "model_data1.json")) as handle:
    native_apple_config = json.load(handle)
native_apple_snapshot = json.loads(json.dumps(native_apple_config))
top_apple_config = _apple_top_down_actor_config(native_apple_config)
top_contacts = top_apple_config["contact_points_pose"]
check("Apple source retains native stable=false metadata",
      native_apple_config.get("stable") is False
      and tuple(native_apple_config.get("scale", ())) == (0.7, 0.7, 0.7))
check("Apple top-contact builder deep-copies native metadata",
      native_apple_config == native_apple_snapshot
      and top_apple_config is not native_apple_config)
check("Apple top-contact config exposes one four-pose group",
      len(top_contacts) == 4
      and top_apple_config["contact_points_group"] == [[0, 1, 2, 3]]
      and top_apple_config["contact_points_mask"] == [True])
check("Apple top-contact rotations are proper and body-centered",
      all(valid_rotation([row[:3] for row in matrix[:3]])
          and tuple(row[3] for row in matrix[:3])
              == tuple(native_apple_config["center"])
          and tuple(tuple(row[:3]) for row in matrix[:3])
              == APPLE_TOP_DOWN_CONTACT_ROTATIONS[index]
          and tuple(matrix[3]) == (0.0, 0.0, 0.0, 1.0)
          for index, matrix in enumerate(top_contacts)))
approach_axes = [
    tuple(-matrix[row][1] for row in range(3))
    for matrix in top_contacts
]
yaw_quaternions = [
    (math.cos(angle / 2), 0.0, 0.0, math.sin(angle / 2))
    for angle in (-math.pi, -math.pi / 2, 0.0, math.pi / 2, math.pi)
]
check("Apple top contacts stay vertical under every z-yaw",
      all(all(math.isclose(value, expected, abs_tol=1e-9)
              for value, expected in zip(
                  rotate_vector(quaternion, axis), (0.0, 0.0, -1.0)))
          for axis in approach_axes for quaternion in yaw_quaternions))

invalid_apple_configs = (
    None,
    {"center": [0, 0, 0], "extents": [1, 1, 1]},
    {"center": [0, 0, 0], "extents": [1, 1, 0], "scale": [1, 1, 1]},
)
rejected = 0
for config in invalid_apple_configs:
    try:
        _apple_top_down_actor_config(config)
    except ValueError:
        rejected += 1
check("Apple top-contact builder rejects incomplete or degenerate metadata",
      rejected == len(invalid_apple_configs))

seen_assets = {entry["asset"] for entry in SEEN_POOL.values()}
candidate_assets = {entry["asset"] for entry in PROBE_UNSEEN_CANDIDATES.values()}
check("all selected Seen assets occur in raw tasks",
      seen_assets <= RAW_TASK_SEEN_ASSETS,
      f"bad={sorted(seen_assets - RAW_TASK_SEEN_ASSETS)}")
check("all reusable probe candidates are raw-task Unseen",
      candidate_assets.isdisjoint(RAW_TASK_SEEN_ASSETS),
      f"overlap={sorted(candidate_assets & RAW_TASK_SEEN_ASSETS)}")

bad_metadata = []
for noun, asset, model_id, _entry in iter_variants(UNSEEN_CANDIDATES):
    ok, note = valid_grasp_metadata(asset, model_id)
    if not ok:
        bad_metadata.append(f"{noun}/{asset}base{model_id}: {note}")
check("all 54 shortlist variants retain stable+grasp metadata",
      not bad_metadata, f"bad={bad_metadata[:3]}")

check("seed parity alternates Seen/Unseen",
      [familiarity_for_seed(seed) for seed in range(8)]
      == ["seen", "unseen"] * 4)
seen_cycle = [
    target_for_seed(seed, SEEN_POOL)[0]
    for seed in range(0, 2 * len(SEEN_POOL), 2)
]
unseen_cycle = [
    target_for_seed(seed, UNSEEN_POOL)[0]
    for seed in range(1, 2 * len(UNSEEN_POOL), 2)
]
check("Seen target nouns cycle in manifest order", seen_cycle == list(SEEN_POOL))
check("final Unseen target nouns cycle in manifest order",
      unseen_cycle == list(UNSEEN_POOL))
speaker_index = list(UNSEEN_CANDIDATES).index("speaker")
first_speaker_seed = 1 + 2 * speaker_index
second_speaker_seed = first_speaker_seed + 2 * len(UNSEEN_CANDIDATES)
check("shortlist exact IDs advance only after one complete noun cycle",
      target_for_seed(first_speaker_seed, UNSEEN_CANDIDATES)[2] == 1
      and target_for_seed(second_speaker_seed, UNSEEN_CANDIDATES)[2] == 2)

try:
    target_for_seed(0, {})
except ValueError:
    empty_pool_rejected = True
else:
    empty_pool_rejected = False
check("empty target pool fails closed", empty_pool_rejected)

# Probe hooks must stay disabled in the production class definition. Parse the source so
# this test remains simulator-free.
tree = ast.parse(open(ENV_PATH).read(), ENV_PATH)
class_node = next(
    node for node in tree.body
    if isinstance(node, ast.ClassDef) and node.name == "pick_diverse_object"
)
override_names = {
    "FAMILIARITY_OVERRIDE", "TARGET_NOUN_OVERRIDE", "TARGET_MODEL_ID_OVERRIDE",
    "TARGET_SIDE_OVERRIDE", "POOL_OVERRIDE", "DISTRACTOR_NOUNS_OVERRIDE",
}
override_values = {}
for node in class_node.body:
    if (isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)):
        name = node.targets[0].id
        if name in override_names:
            override_values[name] = ast.literal_eval(node.value)
check("all retained probe overrides default to None",
      override_values == {name: None for name in override_names},
      f"got={override_values}")
check("removed placement-policy override is absent",
      all(not (isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name)
                       and target.id == "PLACEMENT_ORDER_OVERRIDE"
                       for target in node.targets))
          for node in class_node.body))

print(f"\n==== {sum(RESULTS)}/{len(RESULTS)} passed ====")
sys.exit(0 if RESULTS and all(RESULTS) else 1)
