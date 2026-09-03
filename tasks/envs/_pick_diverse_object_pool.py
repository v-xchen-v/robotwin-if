"""Shared object-familiarity pools for :mod:`pick_diverse_object`.

This module is intentionally simulator-free so the environment, probes, tests, and
reporter use one source of truth.  ``UNSEEN_CANDIDATES`` is only a metadata
shortlist; entries graduate to ``UNSEEN_POOL`` after real settle/grasp probing.
"""

from math import pi


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
_SQRT_HALF = 2 ** -0.5

# Frozen before the 035_apple stability screen. Each support axis is expressed in
# the asset-local frame and maps to world +Z under the corresponding rest quaternion.
APPLE_STABILITY_FAMILY_ORDER = (
    "y-pos-up",
    "x-pos-up",
    "x-neg-up",
    "z-pos-up",
    "z-neg-up",
)
APPLE_STABILITY_POSE_FAMILIES = {
    "y-pos-up": {
        "rest_qpos": (_SQRT_HALF, _SQRT_HALF, 0.0, 0.0),
        "support_axis": (0.0, 1.0, 0.0),
        "rotate_lim": (0.0, pi, 0.0),
    },
    "x-pos-up": {
        "rest_qpos": (_SQRT_HALF, 0.0, -_SQRT_HALF, 0.0),
        "support_axis": (1.0, 0.0, 0.0),
        "rotate_lim": (pi, 0.0, 0.0),
    },
    "x-neg-up": {
        "rest_qpos": (_SQRT_HALF, 0.0, _SQRT_HALF, 0.0),
        "support_axis": (-1.0, 0.0, 0.0),
        "rotate_lim": (pi, 0.0, 0.0),
    },
    "z-pos-up": {
        "rest_qpos": (1.0, 0.0, 0.0, 0.0),
        "support_axis": (0.0, 0.0, 1.0),
        "rotate_lim": (0.0, 0.0, pi),
    },
    "z-neg-up": {
        "rest_qpos": (0.0, 1.0, 0.0, 0.0),
        "support_axis": (0.0, 0.0, -1.0),
        "rotate_lim": (0.0, 0.0, pi),
    },
}
APPLE_STABILITY_THRESHOLDS = {
    "max_target_linear_speed": 0.01,
    "max_target_angular_speed": 0.10,
    "max_xy_drift": 0.015,
    "max_support_tilt_deg": 15.0,
}

# 098_speaker/base3 has no scale or contact metadata. Its mesh uses the same y-up,
# box-like convention as the confirmed 055 speaker, so the first probe reuses 055's
# eight contact orientations at the 098 mesh center. This is an experimental grasp
# hypothesis, not production asset metadata.
_SPEAKER_098_B3_CENTER = (
    4.3250735767945425e-05,
    0.9502841313048153,
    -0.0007235937799795297,
)
_SPEAKER_098_B3_CONTACT_ROTATIONS = (
    (
        (0.01351999957114458, 0.007910000160336494, 0.9998800158500671),
        (0.9999099969863892, -0.00011000000085914508, -0.01351999957114458),
        (0.0, 0.999970018863678, -0.007910000160336494),
    ),
    (
        (0.01351999957114458, 0.9998800158500671, -0.007910000160336494),
        (0.9999099969863892, -0.01351999957114458, 0.00011000000085914508),
        (0.0, -0.007910000160336494, -0.999970018863678),
    ),
    (
        (0.01351999957114458, -0.007910000160336494, -0.9998800158500671),
        (0.9999099969863892, 0.00011000000085914508, 0.01351999957114458),
        (0.0, -0.999970018863678, 0.007910000160336494),
    ),
    (
        (0.01351999957114458, -0.9998800158500671, 0.007910000160336494),
        (0.9999099969863892, 0.01351999957114458, -0.00011000000085914508),
        (0.0, 0.007910000160336494, 0.999970018863678),
    ),
    ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)),
    ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0)),
    ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)),
)


def _contact_pose_at_center(rotation, center):
    return tuple(
        tuple(float(value) for value in rotation[row]) + (float(center[row]),)
        for row in range(3)
    ) + ((0.0, 0.0, 0.0, 1.0),)


def _entry(asset, model_ids, *, rest_qpos=_DEFAULT_REST_QPOS,
           rotate_rand=True, rotate_lim=_DEFAULT_ROTATE_LIM,
           grasp_strategy="default", pre_grasp_dis=0.1,
           contact_point_id=None, grasp_kwargs_by_arm=None,
           placement_radius=0.07, scale=None, actor_config=None):
    """Build an immutable-by-convention pool entry with centralized task config."""
    grasp_kwargs = {"pre_grasp_dis": float(pre_grasp_dis)}
    if contact_point_id is not None:
        grasp_kwargs["contact_point_id"] = int(contact_point_id)
    entry = {
        "asset": asset,
        "model_ids": tuple(model_ids),
        "rest_qpos": tuple(rest_qpos),
        "rotate_rand": bool(rotate_rand),
        "rotate_lim": tuple(rotate_lim),
        "grasp_strategy": grasp_strategy,
        "grasp_kwargs": grasp_kwargs,
        "grasp_kwargs_by_arm": {
            arm: dict(kwargs) for arm, kwargs in (grasp_kwargs_by_arm or {}).items()
        },
        "placement_radius": float(placement_radius),
    }
    if scale is not None:
        entry["scale"] = tuple(float(value) for value in scale)
    if actor_config is not None:
        entry["actor_config"] = actor_config
    return entry


# Production Seen pool: 12 categories / 16 exact variants. All are raw-task Seen and
# already have task-level oracle evidence. Colors deliberately do not appear here:
# the redesigned instruction identifies one of four distinct nouns by noun only.
SEEN_POOL = {
    "bottle": _entry(
        "001_bottle", (0, 22, 5), rest_qpos=(0.707, 0.0, 0.0, 0.707),
        rotate_rand=False, rotate_lim=(0.0, 0.0, 0.0),
        grasp_strategy="bottle", placement_radius=0.065,
    ),
    "cup": _entry(
        "021_cup", (0, 3), rest_qpos=(0.5, 0.5, 0.5, 0.5),
        rotate_rand=False, rotate_lim=(0.0, 0.0, 0.0),
        grasp_strategy="cup", placement_radius=0.06,
    ),
    "shoe": _entry(
        "041_shoe", (8, 4), grasp_strategy="shoe", placement_radius=0.09,
    ),
    "mug": _entry(
        "039_mug", (0,), grasp_strategy="mug", pre_grasp_dis=0.05,
        placement_radius=0.07,
    ),
    "can": _entry(
        "071_can", (3,), rest_qpos=(0.5, 0.5, 0.5, 0.5),
        rotate_rand=False, rotate_lim=(0.0, 0.0, 0.0), placement_radius=0.045,
    ),
    "toy car": _entry("057_toycar", (3,), placement_radius=0.07),
    "phone": _entry(
        "077_phone", (4,), rest_qpos=(0.5, -0.5, 0.5, -0.5),
        rotate_lim=(0.0, 0.7, 0.0), pre_grasp_dis=0.08,
        placement_radius=0.06,
    ),
    "soap": _entry("107_soap", (2,), placement_radius=0.055),
    "hamburger": _entry("006_hamburg", (4,), placement_radius=0.06),
    "bread": _entry("075_bread", (4,), placement_radius=0.07),
    "coffee box": _entry("113_coffee-box", (0,), placement_radius=0.065),
    "mouse": _entry("047_mouse", (0,), placement_radius=0.055),
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


# Production Unseen pool. Every exact variant passed the documented real-SAPIEN
# confirmation threshold (>=70% overall and at least one success per arm). The final
# production-seed sweep additionally verifies that these four objects can coexist.
UNSEEN_POOL = {
    "dumbbell": _entry("052_dumbbell", (0,), placement_radius=0.105),
    "speaker": _entry("055_small-speaker", (1,), placement_radius=0.075),
    "wooden mallet": _entry("084_woodenmallet", (3,), placement_radius=0.10),
    "paintbrush": _entry(
        "093_brush-pen", (1,), contact_point_id=0, placement_radius=0.08,
    ),
}


def _replacement_pool(pool, replaced_noun, candidate_noun, candidate_entry):
    """Return a four-noun probe pool with one slot replaced, failing closed."""
    if replaced_noun not in pool:
        raise ValueError(f"replacement noun {replaced_noun!r} is not in the pool")
    if candidate_noun in pool and candidate_noun != replaced_noun:
        raise ValueError(f"candidate noun {candidate_noun!r} already exists in the pool")
    result = {
        candidate_noun if noun == replaced_noun else noun:
            candidate_entry if noun == replaced_noun else entry
        for noun, entry in pool.items()
    }
    if len(result) != 4:
        raise ValueError("experimental replacement must produce four distinct nouns")
    return result


def _apple_stability_entry(model_id, pose_family):
    family = APPLE_STABILITY_POSE_FAMILIES.get(pose_family)
    if family is None:
        raise ValueError(f"unknown Apple stability pose family: {pose_family!r}")
    placement_radius = 0.055 if int(model_id) == 1 else 0.060
    entry = _entry(
        "035_apple",
        (int(model_id),),
        rest_qpos=family["rest_qpos"],
        rotate_rand=True,
        rotate_lim=family["rotate_lim"],
        placement_radius=placement_radius,
    )
    entry["stability_probe"] = {
        "variant": int(model_id),
        "pose_family": pose_family,
        "support_axis": family["support_axis"],
        **APPLE_STABILITY_THRESHOLDS,
    }
    return entry


_SPEAKER_098_B3_SCALE = (0.05, 0.05, 0.05)
_SPEAKER_098_B3_CONFIG = {
    "stable": True,
    "center": _SPEAKER_098_B3_CENTER,
    "extents": (1.124096427856812, 1.935167998826259, 1.0884406255397343),
    "scale": _SPEAKER_098_B3_SCALE,
    "contact_points_pose": tuple(
        _contact_pose_at_center(rotation, _SPEAKER_098_B3_CENTER)
        for rotation in _SPEAKER_098_B3_CONTACT_ROTATIONS
    ),
    "contact_points_group": ((0, 1, 2, 3), (4, 5, 6, 7)),
    "contact_points_mask": (True, True),
}

APPLE_RADIUS_FIRST_RESCUE_SET = (
    "apple-035-base1-y-pos-up-radius-first-rescue"
)
EXPERIMENTAL_PROBE_PLACEMENT_POLICIES = {
    APPLE_RADIUS_FIRST_RESCUE_SET: "radius-first",
}


# Post-lock replacement experiments. These pools are reachable only through explicit
# probe overrides; production and the historical 14/54 candidate inventory stay fixed.
EXPERIMENTAL_PROBE_CANDIDATE_SETS = {
    "speaker-098-base3": {
        **UNSEEN_POOL,
        "speaker": _entry(
            "098_speaker",
            (3,),
            scale=_SPEAKER_098_B3_SCALE,
            actor_config=_SPEAKER_098_B3_CONFIG,
            placement_radius=0.075,
        ),
    },
    **{
        f"apple-035-base{model_id}-{pose_family}": _replacement_pool(
            UNSEEN_POOL,
            "dumbbell",
            "apple",
            _apple_stability_entry(model_id, pose_family),
        )
        for model_id in (1, 0)
        for pose_family in APPLE_STABILITY_FAMILY_ORDER
    },
    APPLE_RADIUS_FIRST_RESCUE_SET: _replacement_pool(
        UNSEEN_POOL,
        "dumbbell",
        "apple",
        _apple_stability_entry(1, "y-pos-up"),
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
