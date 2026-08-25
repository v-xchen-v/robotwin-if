#!/usr/bin/env python3
"""Layer-B check_success discrimination tests for place_relative.

Positive rollouts only prove "correct action -> True"; they do NOT prove "wrong action
-> False". A check that ignored the relation word, or ignored WHICH object is the
reference, would still pass positives yet make the spatial benchmark meaningless. So we
drive specific end-states by teleporting the mover and assert the expected boolean.

KEY cases:
  R4 wrong-RELATION: beside asked but mover stacked ON B -> False; on-top asked but mover
     placed BESIDE B -> False. Proves the relation word decides success.
  R5 wrong-REFERENCE: mover placed next to / on a DISTRACTOR, not B -> False. Proves the
     check is anchored to the NAMED reference, not just "some object".

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

_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run
cd.main(task_name="place_relative", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0

IDENT = [1.0, 0.0, 0.0, 0.0]
_results = []


def _setup_relation(relation, start):
    """setup_demo for a seed whose relation == `relation`, retrying by +2 so the
    relation parity (seed % 2) is preserved across UnStableError retries."""
    s = start if (start % 2) == (0 if relation == "beside" else 1) else start + 1
    last = None
    for _ in range(60):
        try:
            TASK.setup_demo(now_ep_num=0, seed=s, **ARGS)
            assert TASK.relation == relation, (s, TASK.relation)
            return s
        except Exception as e:  # UnStableError etc.
            last = e
            s += 2
    raise RuntimeError(f"no stable {relation} scene near {start}: {last}")


def _teleport(actor, xyz):
    actor.actor.set_pose(sapien.Pose([float(xyz[0]), float(xyz[1]), float(xyz[2])], IDENT))


def _beside_xyz(ref):
    b = ref.get_pose().p
    return [b[0] + 0.13, b[1], b[2]]           # next to B, same height


def _ontop_xyz(ref, half_z):
    b = ref.get_pose().p
    return [b[0], b[1], b[2] + half_z + 0.03]  # aligned over B, elevated onto its top


def _record(name, got, expect, note=""):
    got = bool(got)
    ok = got == expect
    _results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: got={got} expect={expect}  {note}")


# ---- R1 default: nothing moved -> False (both relations) --------------------------
s = _setup_relation("beside", 0)
_record("R1 default beside (nothing moved)", TASK.check_success(), False,
        note=f"seed={s} mover={TASK.mover_noun} ref={TASK.reference_noun}")

# ---- R2 beside positive: teleport mover next to B -> True -------------------------
_teleport(TASK.mover, _beside_xyz(TASK.reference))
_record("R2 beside positive (mover next to B)", TASK.check_success(), True, note=f"seed={s}")

# ---- R4a wrong-relation: beside asked but mover STACKED on B -> False -------------
_teleport(TASK.mover, _ontop_xyz(TASK.reference, TASK.base_half_z))
_record("R4a beside asked, mover stacked <-KEY", TASK.check_success(), False, note=f"seed={s}")

# ---- R5a wrong-reference: beside asked, mover next to a DISTRACTOR -> False -------
if TASK.distractors:
    d = TASK.distractors[0]["actor"]
    _teleport(TASK.mover, _beside_xyz(d))
    far = np.hypot(*(TASK.mover.get_pose().p[:2] - TASK.reference.get_pose().p[:2]))
    _record("R5a beside asked, next to distractor <-KEY", TASK.check_success(), False,
            note=f"seed={s} dist_to_ref={far:.2f}")

# ---- R3 on-top positive: teleport mover onto B -> True ----------------------------
s2 = _setup_relation("on_top", 1)
_teleport(TASK.mover, _ontop_xyz(TASK.reference, TASK.base_half_z))
_record("R3 on-top positive (mover on B)", TASK.check_success(), True,
        note=f"seed={s2} mover={TASK.mover_noun} ref={TASK.reference_noun} half_z={TASK.base_half_z:.3f}")

# ---- R4b wrong-relation: on-top asked but mover BESIDE B -> False -----------------
_teleport(TASK.mover, _beside_xyz(TASK.reference))
_record("R4b on-top asked, mover beside <-KEY", TASK.check_success(), False, note=f"seed={s2}")

# ---- R5b wrong-reference: on-top asked, mover on a DISTRACTOR -> False ------------
if TASK.distractors:
    d = TASK.distractors[0]["actor"]
    dp = d.get_pose().p
    _teleport(TASK.mover, [dp[0], dp[1], dp[2] + 0.10])
    _record("R5b on-top asked, on distractor <-KEY", TASK.check_success(), False, note=f"seed={s2}")

# ---- R6 oracle positives: the scripted expert should satisfy the check ------------
for rel, start in [("beside", 0), ("on_top", 1)]:
    ok = False
    seed = start
    for _ in range(8):
        sd = _setup_relation(rel, seed)
        try:
            TASK.play_once()
            if TASK.check_success():
                ok = True
                break
        except Exception:
            pass
        seed = sd + 2
    _record(f"R6 oracle positive ({rel})", ok, True, note=f"from seed {start}")

print("\n==== summary ====")
print(f"{sum(_results)}/{len(_results)} passed")
sys.exit(0 if _results and all(_results) else 1)
