#!/usr/bin/env python3
"""Layer-B check_success discrimination tests for place_relative (IF-Spatial-Direction).

Positive rollouts only prove "correct action -> True"; they do NOT prove "wrong action
-> False". A check that ignored the direction word, or ignored WHICH object is the
reference, would still pass positives yet make the spatial benchmark meaningless. So we
drive specific end-states by teleporting the mover and assert the expected boolean.

KEY cases:
  R4 wrong-DIRECTION: left asked but mover placed to the RIGHT of B -> False; front asked
     but placed BEHIND B -> False; a lateral direction asked but mover STACKED on B ->
     False; on-top asked but mover placed BESIDE B -> False. Proves the direction phrase
     decides success.
  R5 wrong-REFERENCE: mover placed correctly relative to the DISTRACTOR, not B -> False.
     Proves the check is anchored to the NAMED reference, not just "some object".
  R7 scene-pairing: consecutive seeds 5k..5k+4 share ONE scene (same A/B/distractor
     poses) and cycle through all five directions -- the structural guarantee that the
     policy sees pixel-identical frames and only the instruction changes.

Run inside the RoboTwin conda env:
    conda activate RoboTwin
    python tests/place_relative/test_check_success.py
"""
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _parent = os.path.dirname(_REPO)
    if _parent == _REPO:
        raise RuntimeError("could not locate repo root (no third_party/robotwin above this file)")
    _REPO = _parent
_RT = os.path.join(_REPO, "third_party", "robotwin")
os.chdir(_RT)
sys.path.insert(0, os.path.join(_RT, "script"))
sys.path.insert(0, _RT)

import numpy as np  # noqa: E402
import sapien  # noqa: E402
import collect_data as cd  # noqa: E402
from envs._if_relative import DIRECTIONS  # noqa: E402

_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run
cd.main(task_name="place_relative", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0
ORDER = list(TASK.ORDER)

IDENT = [1.0, 0.0, 0.0, 0.0]
_results = []


def _setup_direction(direction, start=0):
    """setup_demo for a seed whose direction == `direction` (seed % 5 == index),
    retrying by +5 so the parity is preserved across UnStableError retries."""
    idx = ORDER.index(direction)
    s = start + ((idx - start) % 5)
    last = None
    for _ in range(80):
        try:
            TASK.setup_demo(now_ep_num=0, seed=s, **ARGS)
            assert TASK.direction == direction, (s, TASK.direction)
            return s
        except Exception as e:  # UnStableError etc.
            last = e
            s += 5
    raise RuntimeError(f"no stable {direction} scene near {start}: {last}")


def _teleport(actor, xyz):
    actor.actor.set_pose(sapien.Pose([float(xyz[0]), float(xyz[1]), float(xyz[2])], IDENT))


def _dir_xyz(ref, direction, offset=None):
    """xyz for the mover placed in `direction` relative to `ref`, on the table."""
    off = TASK.OFFSET if offset is None else offset
    axis, sign = DIRECTIONS[direction]
    b = ref.get_pose().p
    xyz = [float(b[0]), float(b[1]), float(b[2])]
    xyz[0 if axis == "x" else 1] += sign * off
    return xyz


def _ontop_xyz(ref, half_z):
    b = ref.get_pose().p
    return [b[0], b[1], b[2] + half_z + 0.03]  # aligned over B, elevated onto its top


def _record(name, got, expect, note=""):
    got = bool(got)
    ok = got == expect
    _results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: got={got} expect={expect}  {note}")


# ---- R1 default: nothing moved -> False (every direction) --------------------------
for d in ORDER:
    s = _setup_direction(d)
    _record(f"R1 default {d} (nothing moved)", TASK.check_success(), False,
            note=f"seed={s} mover={TASK.mover_noun} ref={TASK.reference_noun}")

# ---- R2 lateral positives: teleport mover to the commanded cell -> True ------------
for d in ("left", "right", "front", "back"):
    s = _setup_direction(d)
    _teleport(TASK.mover, _dir_xyz(TASK.reference, d))
    _record(f"R2 {d} positive (mover {d} of B)", TASK.check_success(), True, note=f"seed={s}")

# ---- R3 on-top positive: teleport mover onto B -> True -----------------------------
s = _setup_direction("on_top")
_teleport(TASK.mover, _ontop_xyz(TASK.reference, TASK.base_half_z))
_record("R3 on-top positive (mover on B)", TASK.check_success(), True,
        note=f"seed={s} half_z={TASK.base_half_z:.3f}")

# ---- R4 wrong-DIRECTION reversals -> False (all KEY) -------------------------------
s = _setup_direction("left")
_teleport(TASK.mover, _dir_xyz(TASK.reference, "right"))
_record("R4a left asked, placed RIGHT <-KEY", TASK.check_success(), False, note=f"seed={s}")

s = _setup_direction("front")
_teleport(TASK.mover, _dir_xyz(TASK.reference, "back"))
_record("R4b front asked, placed BACK <-KEY", TASK.check_success(), False, note=f"seed={s}")

s = _setup_direction("left")
_teleport(TASK.mover, _ontop_xyz(TASK.reference, TASK.base_half_z))
_record("R4c lateral asked, mover STACKED <-KEY", TASK.check_success(), False, note=f"seed={s}")

s = _setup_direction("on_top")
_teleport(TASK.mover, _dir_xyz(TASK.reference, "right"))
_record("R4d on-top asked, mover BESIDE <-KEY", TASK.check_success(), False, note=f"seed={s}")

# ---- R5 wrong-REFERENCE: correct direction, but relative to the DISTRACTOR -> False -
s = _setup_direction("left")
if TASK.distractors:
    d = TASK.distractors[0]["actor"]
    _teleport(TASK.mover, _dir_xyz(d, "left"))
    far = np.hypot(*(TASK.mover.get_pose().p[:2] - TASK.reference.get_pose().p[:2]))
    _record("R5a left of DISTRACTOR (not B) <-KEY", TASK.check_success(), False,
            note=f"seed={s} dist_to_ref={far:.2f}")

s = _setup_direction("on_top")
if TASK.distractors:
    d = TASK.distractors[0]["actor"]
    dp = d.get_pose().p
    _teleport(TASK.mover, [dp[0], dp[1], dp[2] + 0.10])
    _record("R5b on-top of DISTRACTOR (not B) <-KEY", TASK.check_success(), False, note=f"seed={s}")

# ---- R6 oracle positives: the scripted expert should satisfy the check -------------
for d in ORDER:
    ok = False
    seed = ORDER.index(d)
    for _ in range(8):
        sd = _setup_direction(d, seed)
        try:
            TASK.play_once()
            if TASK.check_success():
                ok = True
                break
        except Exception:
            pass
        seed = sd + 5
    _record(f"R6 oracle positive ({d})", ok, True, note=f"direction {d}")

# ---- R7 scene-pairing: seeds 5k..5k+4 share one scene, directions cycle ------------
def _scene_key():
    """Initial-pose fingerprint (mover/ref/distractor noun + xy), rounded."""
    def xy(a):
        p = a.get_pose().p
        return (round(float(p[0]), 3), round(float(p[1]), 3))
    return (TASK.mover_noun, xy(TASK.mover), TASK.reference_noun, xy(TASK.reference),
            TASK.distractors[0]["noun"], xy(TASK.distractors[0]["actor"]))


base = 0
for _try in range(6):
    keys, dirs, ok_tuple = [], [], True
    for k in range(5):
        try:
            TASK.setup_demo(now_ep_num=0, seed=base + k, **ARGS)
            keys.append(_scene_key())
            dirs.append(TASK.direction)
        except Exception:
            ok_tuple = False
            break
    if ok_tuple:
        break
    base += 5
_record("R7a 5-tuple shares one scene", ok_tuple and all(k == keys[0] for k in keys), True,
        note=f"base_seed={base} keys={len(set(keys))} unique")
_record("R7b 5-tuple cycles all directions", dirs == ORDER, True, note=f"dirs={dirs}")

print("\n==== summary ====")
print(f"{sum(_results)}/{len(_results)} passed")
sys.exit(0 if _results and all(_results) else 1)
