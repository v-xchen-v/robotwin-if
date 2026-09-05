#!/usr/bin/env python3
"""Layer-B + same-scene structural test for attribute_select.

Two things, using the real env (setup_demo builds the scene):

  A. SAME-SCENE structural invariant (guards the bug the user caught): the pair
     (2k, 2k+1) must be the SAME physical scene -- both objects at the SAME two
     positions -- with only the *named* target flipping. If the target's position
     tracked the instruction, a policy could win by position alone.

  B. check_success predicate (Layer-B counter-example): lifting the TARGET passes,
     lifting the DISTRACTOR fails, lifting neither fails -- proving success is
     "the lifted object is the commanded target", not "something moved".

Run after ./bridge_tasks.sh, inside the RoboTwin conda env:
    python tests/attribute_select/test_check_success.py
"""
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _p = os.path.dirname(_REPO)
    if _p == _REPO:
        raise RuntimeError("repo root not found")
    _REPO = _p
_RT = os.path.join(_REPO, "third_party", "robotwin")
os.chdir(_RT)
sys.path.insert(0, os.path.join(_RT, "script"))
sys.path.insert(0, _RT)

import sapien  # noqa: E402
import collect_data as cd  # noqa: E402

_cap = {}
cd.run = lambda task, args: _cap.update(task=task, args=args)
cd.main(task_name="attribute_select", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"]); ARGS["render_freq"] = 0

_res = []


def rec(name, ok, note=""):
    _res.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


def setup(seed):
    TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)


def xy(actor):
    p = actor.get_pose().p
    return (round(float(p[0]), 3), round(float(p[1]), 3))


def lift(actor, dz):
    p = actor.get_pose().p
    actor.actor.set_pose(sapien.Pose([float(p[0]), float(p[1]), float(p[2]) + dz]))


# ---- A. same-scene structural invariant (color pair seed 0 / 1) ----
setup(0)
scene0 = {xy(TASK.target), xy(TASK.distractor)}
t0 = xy(TASK.target)
setup(1)
scene1 = {xy(TASK.target), xy(TASK.distractor)}
t1 = xy(TASK.target)
rec("pair (0,1) is the SAME scene (identical object positions)", scene0 == scene1,
    note=f"{sorted(scene0)} vs {sorted(scene1)}")
rec("named target flips to the OTHER position (no position shortcut)", t0 != t1,
    note=f"seed0 target@{t0}  seed1 target@{t1}")

# ---- B. check_success predicate (color seed 0) ----
setup(0)
tz = float(TASK.target.get_pose().p[2])
dz = float(TASK.distractor.get_pose().p[2])
TASK._init_z = {"target": tz, "distractor": dz}

lift(TASK.target, 0.10)
rec("lift TARGET -> raw True", TASK._raw_success() is True)

lift(TASK.target, -0.10)          # put target back
lift(TASK.distractor, 0.10)
rec("lift DISTRACTOR -> raw False (Layer-B)", TASK._raw_success() is False)

lift(TASK.distractor, -0.10)      # nothing lifted
rec("lift NEITHER -> raw False", TASK._raw_success() is False)

# ---- C. pair-gate logic (inject _pair_ok cache -> no expensive partner rollout) ----
lift(TASK.target, 0.10)                       # raw success again
sk = TASK._seed // 2
type(TASK)._pair_ok[sk] = False
rec("pair-gate: partner infeasible -> check_success False (drop pair)",
    TASK.check_success() is False)
type(TASK)._pair_ok[sk] = True
rec("pair-gate: partner feasible -> check_success True", TASK.check_success() is True)
type(TASK)._pair_ok.pop(sk, None)

print(f"\n==== {sum(_res)}/{len(_res)} passed ====")
sys.exit(0 if _res and all(_res) else 1)
