"""Shared object-familiarity pools for :mod:`pick_diverse_object`.

This module is intentionally simulator-free so the environment, probes, tests, and
reporter use one source of truth.  ``UNSEEN_CANDIDATES`` is only a metadata
shortlist; entries graduate to ``UNSEEN_POOL`` after real settle/grasp probing.
"""

from copy import deepcopy
from math import isfinite, pi


# Category-level familiarity is defined only by the 50 native/raw task files that
# existed at first-commit 8187d5b. IF-added tasks do not make an object Seen because
# IF-Ext produces no finetuning data.
RAW_TASK_SEEN_ASSETS = frozenset({
    "001_bottle", "002_bowl", "003_plate", "005_french-fries", "006_hamburg",
    "007_shoe-box", "008_tray", "011_dustbin", "015_laptop", "018_microphone",
    "019_coaster", "020_hammer", "021_cup", "024_scanner", "036_cabinet",
    "039_mug", "040_rack", "041_shoe", "044_microwave", "046_alarm-clock",
    "047_mouse", "048_stapler", "050_bell", "056_switch", "057_toycar",
    "060_kitchenpot", "062_plasticbox", "063_tabletrashbin", "070_paymentsign",
    "071_can", "072_electronicscale", "073_rubikscube", "074_displaystand",
    "075_bread", "076_breadbasket", "077_phone", "078_phonestand",
    "079_remotecontrol", "080_pillbottle", "081_playingcards", "086_woodenblock",
    "099_fan", "100_seal", "102_roller", "105_sauce-can", "106_skillet",
    "107_soap", "110_basket", "112_tea-box", "113_coffee-box", "114_bottle",
})

FAMILIARITIES = ("seen", "unseen")
_DEFAULT_REST_QPOS = (0.707, 0.707, 0.0, 0.0)
_DEFAULT_ROTATE_LIM = (0.0, pi / 3, 0.0)

# Proven top-down rotations from grasp_cube_approach. Translation is filled from
# the Apple metadata center so the gripper closes around the body, not the crown.
APPLE_TOP_DOWN_CONTACT_ROTATIONS = (
    ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
    ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    ((0.0, 0.0, -1.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
)



def _contact_pose_at_center(rotation, center):
    return tuple(
        tuple(float(value) for value in rotation[row]) + (float(center[row]),)
        for row in range(3)
    ) + ((0.0, 0.0, 0.0, 1.0),)


def _apple_top_down_actor_config(native_config):
    """Return an isolated Apple config with body-centered top-down contacts."""
    if not isinstance(native_config, dict):
        raise ValueError("Apple top-down grasp requires native actor metadata")

    vectors = {}
    for key in ("center", "extents", "scale"):
        try:
            values = tuple(float(value) for value in native_config[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid Apple {key} metadata") from exc
        if len(values) != 3 or not all(isfinite(value) for value in values):
            raise ValueError(f"invalid Apple {key} metadata")
        vectors[key] = values

    if not all(value > 0 for value in vectors["extents"]):
        raise ValueError("Apple extents must be positive")
    if not all(value > 0 for value in vectors["scale"]):
        raise ValueError("Apple scale must be positive")

    result = deepcopy(native_config)
    result["contact_points_pose"] = [
        [list(row) for row in _contact_pose_at_center(rotation, vectors["center"])]
        for rotation in APPLE_TOP_DOWN_CONTACT_ROTATIONS
    ]
    result["contact_points_group"] = [[0, 1, 2, 3]]
    result["contact_points_mask"] = [True]
    return result


def _entry(asset, model_ids, *, rest_qpos=_DEFAULT_REST_QPOS,
           rotate_rand=True, rotate_lim=_DEFAULT_ROTATE_LIM,
           grasp_strategy="default", pre_grasp_dis=0.1,
           contact_point_id=None, placement_radius=0.07):
    """Build an immutable-by-convention pool entry with centralized task config."""
    grasp_kwargs = {"pre_grasp_dis": float(pre_grasp_dis)}
    if contact_point_id is not None:
        grasp_kwargs["contact_point_id"] = int(contact_point_id)
    return {
        "asset": asset,
        "model_ids": tuple(model_ids),
        "rest_qpos": tuple(rest_qpos),
        "rotate_rand": bool(rotate_rand),
        "rotate_lim": tuple(rotate_lim),
        "grasp_strategy": grasp_strategy,
        "grasp_kwargs": grasp_kwargs,
        "placement_radius": float(placement_radius),
    }


# Production Seen pool: 12 categories / 12 exact variants, one per noun. Every exact
# ID is reachable from native/raw task Python at commit 8187d5b. The IDs were selected
# by visual review in the object atlas; model-specific native pose adjustments are kept.
SEEN_POOL = {
    "bottle": _entry(
        "001_bottle", (13,), rest_qpos=(0.707, 0.0, 0.0, 0.707),
        rotate_rand=False, rotate_lim=(0.0, 0.0, 0.0),
        grasp_strategy="bottle", placement_radius=0.065,
    ),
    "cup": _entry(
        "021_cup", (0,), rest_qpos=(0.5, 0.5, 0.5, 0.5),
        rotate_rand=False, rotate_lim=(0.0, 0.0, 0.0),
        grasp_strategy="cup", placement_radius=0.06,
    ),
    "shoe": _entry(
        "041_shoe", (8,), grasp_strategy="shoe", placement_radius=0.09,
    ),
    "mug": _entry(
        "039_mug", (0,), grasp_strategy="mug", pre_grasp_dis=0.05,
        placement_radius=0.07,
    ),
    "can": _entry(
        "071_can", (2,), rest_qpos=(0.5, 0.5, 0.5, 0.5),
        rotate_rand=False, rotate_lim=(0.0, 0.0, 0.0), placement_radius=0.045,
    ),
    "toy car": _entry("057_toycar", (5,), placement_radius=0.07),
    "phone": _entry(
        # Native place_phone_stand uses this model-specific resting orientation
        # for base1; the previous quaternion was the native base4 orientation.
        "077_phone", (1,), rest_qpos=(0.5, 0.5, 0.5, 0.5),
        rotate_lim=(0.0, 0.7, 0.0), pre_grasp_dis=0.08,
        placement_radius=0.06,
    ),
    "soap": _entry("107_soap", (0,), placement_radius=0.055),
    "hamburger": _entry("006_hamburg", (0,), placement_radius=0.06),
    "bread": _entry("075_bread", (5,), placement_radius=0.07),
    "coffee box": _entry("113_coffee-box", (1,), placement_radius=0.065),
    "mouse": _entry("047_mouse", (2,), placement_radius=0.055),
}


# Exhaustive metadata shortlist among all 69 raw-task-Unseen numbered categories.
# Inclusion requires a rigid visual/collision asset, stable=True, and nonempty valid
# contact_points_group/contact_points_mask. This is NOT evidence that a variant settles,
# can coexist in a four-object scene, or can be grasped by both arms.
UNSEEN_CANDIDATES = {
    "drill": _entry("030_drill", (6,), placement_radius=0.085),
    "shampoo bottle": _entry("049_shampoo", (1, 2, 3, 4, 5, 7), placement_radius=0.07),
    "candlestick": _entry("051_candlestick", (0, 1, 2, 3), placement_radius=0.12),
    "dumbbell": _entry("052_dumbbell", (0, 2, 4, 6), placement_radius=0.105),
    "speaker": _entry("055_small-speaker", (1, 2), placement_radius=0.075),
    "pencil cup": _entry("059_pencup", (0, 1, 2, 3, 4, 5, 6), placement_radius=0.07),
    "drink bottle": _entry("068_boxdrink", (2, 3), placement_radius=0.08),
    "wooden mallet": _entry("084_woodenmallet", (3,), placement_radius=0.10),
    "globe": _entry("089_globe", (2, 3), placement_radius=0.13),
    "trophy": _entry("090_trophy", (0, 1, 2, 3, 4), placement_radius=0.10),
    "glue bottle": _entry("095_glue", (0, 1, 2, 4, 5, 6), placement_radius=0.065),
    "milk tea": _entry("101_milk-tea", (0, 1, 2, 4, 6), placement_radius=0.09),
    "hydrating oil": _entry("109_hydrating-oil", (0, 1, 2, 5), placement_radius=0.06),
    "hand bell": _entry("111_callbell", (1, 2, 3, 4, 5), placement_radius=0.085),
}


# Manual follow-up after the 14-category metadata shortlist produced only three passing
# nouns. These assets are raw-task Unseen and stable, and they contain contact poses,
# but their empty contact groups/masks disable RoboTwin's automatic contact selection.
# Explicit contact IDs make them probeable without editing third-party asset metadata.
# They remain candidates, not production objects, until they pass the same real-SAPIEN
# confirmation and coexistence gates as the original shortlist.
MANUAL_UNSEEN_CANDIDATES = {
    "notebook": _entry(
        "092_notebook", (0, 1, 2), contact_point_id=0, placement_radius=0.10,
    ),
    "paintbrush": _entry(
        "093_brush-pen", (0, 1, 2, 4, 5), contact_point_id=0,
        placement_radius=0.08,
    ),
}

PROBE_UNSEEN_CANDIDATES = {
    **UNSEEN_CANDIDATES,
    **MANUAL_UNSEEN_CANDIDATES,
}


def _production_apple_entry():
    """Canonical upright Apple with task-local, arm-symmetric top contacts."""
    return _entry(
        "035_apple",
        (1,),
        rest_qpos=(1.0, 0.0, 0.0, 0.0),
        rotate_rand=True,
        rotate_lim=(0.0, 0.0, pi),
        grasp_strategy="apple_top_down",
        pre_grasp_dis=0.08,
        placement_radius=0.055,
    )


# Production Unseen pool: four exact variants that passed real settle/grasp gates.
# Insertion order defines the target cycle for odd raw seeds.
UNSEEN_POOL = {
    "dumbbell": _entry("052_dumbbell", (0,), placement_radius=0.105),
    "apple": _production_apple_entry(),
    "wooden mallet": _entry("084_woodenmallet", (3,), placement_radius=0.10),
    "paintbrush": _entry(
        "093_brush-pen", (1,), contact_point_id=0, placement_radius=0.08,
    ),
}


def familiarity_for_seed(seed):
    """Alternate object familiarity on raw seed parity for exact 50/50 tried counts."""
    return FAMILIARITIES[int(seed) % len(FAMILIARITIES)]


def target_for_seed(seed, pool):
    """Return ``(noun, asset, model_id)`` using the per-group production schedule.

    ``seed // 2`` advances the schedule because adjacent raw seeds belong to different
    familiarity groups. Nouns cycle first; variants cycle only after a full noun cycle.
    """
    if not pool:
        raise ValueError("target pool is empty")
    nouns = tuple(pool)
    group_index = int(seed) // len(FAMILIARITIES)
    noun = nouns[group_index % len(nouns)]
    entry = pool[noun]
    model_ids = entry["model_ids"]
    if not model_ids:
        raise ValueError(f"{noun!r} has no locked model_ids")
    model_id = model_ids[(group_index // len(nouns)) % len(model_ids)]
    return noun, entry["asset"], model_id


def iter_variants(pool):
    """Yield ``(noun, asset, model_id, entry)`` for every exact pool variant."""
    for noun, entry in pool.items():
        for model_id in entry["model_ids"]:
            yield noun, entry["asset"], model_id, entry
