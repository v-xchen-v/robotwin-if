#!/usr/bin/env python3
"""Layer-B + scene-pairing tests for the merged IF-Sequence env stack_sequence.

Two guarantees this env must hold:
  (1) Scene/order decoupling: seeds (6k .. 6k+5) produce the IDENTICAL scene
      (same 3 block positions) under the 6 DIFFERENT commanded orders — the
      "same frame, only the instructed order differs" property that isolates the
      sequence axis.
  (2) check_success grades the stack in the COMMANDED bottom->top order, and the
      REVERSAL (a valid stack built in the wrong order) MUST fail — the
      order-blind false-positive this task exists to catch.

Predicates are tested directly (`_l2_ordered` = following, `_l1_any_stack` =
execution) by set_pose-ing the blocks, so no full sim / gripper state is needed
(mirrors laptop_verb's use of `_raw_success`).

Run inside the RoboTwin conda env, after ./bridge_tasks.sh:
    conda activate RoboTwin
    python tests/stack_sequence/test_check_success.py
Exit code is non-zero if any case fails.
"""
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _parent = os.path.dirname(_REPO)
    if _parent == _REPO:
        raise RuntimeError("could not locate repo root")
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
cd.main(task_name="stack_sequence", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0
# Production pairing (scene=seed//6, order=seed%6), not the spike override.
TASK.MODE = None
TASK.ORACLE_MODE = None

_results = []


def _record(name, ok, note=""):
    _results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


def setup(seed):
    last = None
    s = seed
    for _ in range(20):
        try:
            TASK.setup_demo(now_ep_num=0, seed=s, **ARGS)
            return
        except Exception as e:
            last = e
            s += 6  # keep seed%6 so the commanded order is preserved
    raise RuntimeError(f"no stable scene near {seed}: {last}")


def block_xy(ci):
    return np.round(TASK.blocks[ci].get_pose().p[:2], 5).tolist()


def scene_sig():
    # scene = the 3 fixed-color block positions (color index -> xy).
    return [block_xy(ci) for ci in range(3)]


def put(ci, x, y, z):
    # Actor wraps the sapien entity as .actor (get_pose proxies to it); set the
    # underlying entity's pose directly.
    TASK.blocks[ci].actor.set_pose(sapien.Pose([x, y, z], [1, 0, 0, 0]))


def stack_in(order, base=(0.0, -0.13), z0=0.80, dz=0.05, xy_jit=None):
    """Place blocks[order[0]] at the bottom, order[1] middle, order[2] top."""
    x, y = base
    for lvl, ci in enumerate(order):
        ox, oy = (xy_jit[lvl] if xy_jit else (0.0, 0.0))
        put(ci, x + ox, y + oy, z0 + dz * lvl)


def scatter():
    # Three blocks flat on the table, far apart -> no stack at all.
    put(0, -0.20, -0.10, 0.80)
    put(1, 0.00, -0.10, 0.80)
    put(2, 0.20, -0.10, 0.80)


def l2():
    return bool(TASK._l2_ordered())


def l1():
    return bool(TASK._l1_any_stack())


# ===================== (1) scene/order decoupling ==========================
# Seeds 0..5 -> scene_seed 0 -> identical 3-block scene; modes 0..5 (all perms).
sigs, modes = [], []
for s in range(6):
    setup(s)
    sigs.append(scene_sig())
    modes.append(TASK.mode)
_record("seeds 0..5 share one scene", all(sig == sigs[0] for sig in sigs),
        note=f"{sigs[0]}")
_record("seeds 0..5 cover all 6 orders", sorted(modes) == [0, 1, 2, 3, 4, 5],
        note=f"modes={modes}")

# ===================== (2) order-graded success + reversal =================
# seed 0 -> mode 0 -> perm (red, green, blue) bottom->top.
setup(0)
assert TASK.perm == (0, 1, 2), TASK.perm
stack_in((0, 1, 2))
_record("perm0 positive (red<green<blue)", l2() and l1())
stack_in((2, 1, 0))
_record("perm0 reversal (blue<green<red) <-KEY", (not l2()) and l1(),
        note="valid stack, wrong order -> L2 must fail, L1 still true")
stack_in((0, 2, 1))
_record("perm0 mid/top swapped", (not l2()) and l1())
scatter()
_record("perm0 not stacked (flat)", (not l2()) and (not l1()))
# Only two stacked (bottom+mid aligned), top block off on its own.
put(0, 0.0, -0.13, 0.80)
put(1, 0.0, -0.13, 0.85)
put(2, 0.25, -0.10, 0.80)
_record("perm0 only two stacked", (not l2()) and (not l1()))
# xy misalignment beyond eps (0.025) breaks the stack even with right z.
stack_in((0, 1, 2), xy_jit=[(0, 0), (0.03, 0), (0.03, 0)])
_record("perm0 xy off > eps -> not stacked", (not l2()) and (not l1()))

# seed 5 -> mode 5 -> perm (blue, green, red) bottom->top. Confirms the check is
# parametrized by the commanded order, not hardcoded to red-bottom.
setup(5)
assert TASK.perm == (2, 1, 0), TASK.perm
stack_in((2, 1, 0))
_record("perm5 positive (blue<green<red)", l2() and l1())
stack_in((0, 1, 2))
_record("perm5 reversal (red<green<blue) <-KEY", (not l2()) and l1(),
        note="native default order is WRONG here -> must fail")

# Sanity: full check_success (adds grippers-open) agrees on a positive case at
# rest (grippers open after setup).
setup(0)
stack_in((0, 1, 2))
_record("check_success positive incl. grippers", bool(TASK.check_success()))

print("\n==== summary ====")
print(f"{sum(_results)}/{len(_results)} passed")
sys.exit(0 if _results and all(_results) else 1)
