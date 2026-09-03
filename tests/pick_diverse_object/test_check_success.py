#!/usr/bin/env python3
"""Layer-B grounding discrimination tests for Pick-Diverse-Object.

Positive oracle runs alone cannot show that the success check is target-specific. This
script drives positive and negative terminal states in both object-familiarity groups:

* every locked production noun must be graspable and produce ``True``;
* lifting an arbitrary distractor must remain ``False``;
* moving the target upward without holding it must remain ``False``;
* the untouched initial state must remain ``False``.

Run from anywhere inside the RoboTwin conda environment:

    python tests/pick_diverse_object/test_check_success.py
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
sys.path[:0] = [os.path.join(_RT, "script"), _RT]

import sapien  # noqa: E402
import collect_data as cd  # noqa: E402
from envs._pick_diverse_object_pool import SEEN_POOL, UNSEEN_POOL  # noqa: E402


_CAPTURE = {}
cd.run = lambda task, args: _CAPTURE.update(task=task, args=args)
cd.main(task_name="pick_diverse_object", task_config="demo_clean")
TASK = _CAPTURE["task"]
ARGS = dict(_CAPTURE["args"])
ARGS["render_freq"] = 0

ALIGN_Q = [0.5, 0.5, 0.5, 0.5]
RESULTS = []


def _record(name, got, expect, note=""):
    got = bool(got)
    ok = got == expect
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: got={got} expect={expect}  {note}")


def _configure(familiarity, noun=None, model_id=None, side=None):
    TASK.FAMILIARITY_OVERRIDE = familiarity
    TASK.POOL_OVERRIDE = None
    TASK.TARGET_NOUN_OVERRIDE = noun
    TASK.TARGET_MODEL_ID_OVERRIDE = model_id
    TASK.TARGET_SIDE_OVERRIDE = side
    TASK.DISTRACTOR_NOUNS_OVERRIDE = None


def _setup(seed):
    """Set up the currently forced target, retrying only physical setup failures."""
    last = None
    for candidate_seed in range(seed, seed + 40):
        try:
            TASK.setup_demo(now_ep_num=0, seed=candidate_seed, **ARGS)
            return candidate_seed
        except Exception as exc:
            last = exc
    raise RuntimeError(f"no suitable scene near seed {seed}: {last}")


def _lift_without_grasp(actor):
    pose = actor.get_pose()
    actor.actor.set_pose(sapien.Pose(
        [float(pose.p[0]), float(pose.p[1]), float(pose.p[2]) + 0.2],
        ALIGN_Q,
    ))


def _negative_cases(familiarity, pool, seed_base):
    noun = next(iter(pool))
    model_id = pool[noun]["model_ids"][0]

    _configure(familiarity, noun, model_id)
    seed = _setup(seed_base)
    _record(f"{familiarity}: untouched initial state", TASK.check_success(), False,
            note=f"target={noun} seed={seed}")

    _configure(familiarity, noun, model_id)
    seed = _setup(seed_base + 100)
    wrong = TASK.distractors[0]
    _lift_without_grasp(wrong["actor"])
    _record(f"{familiarity}: arbitrary distractor lifted", TASK.check_success(), False,
            note=f"target={noun} wrong={wrong['noun']} seed={seed}")

    _configure(familiarity, noun, model_id)
    seed = _setup(seed_base + 200)
    _lift_without_grasp(TASK.target)
    _record(f"{familiarity}: target moved but not held", TASK.check_success(), False,
            note=f"target={noun} seed={seed}")


def _positive_cases(familiarity, pool, seed_base):
    for noun_index, (noun, entry) in enumerate(pool.items()):
        model_id = entry["model_ids"][0]
        success = None
        attempts = 0
        for attempt in range(6):
            side = ("left", "right")[attempt % 2]
            _configure(familiarity, noun, model_id, side)
            seed = _setup(seed_base + noun_index * 100 + attempt * 10)
            attempts += 1
            try:
                TASK.play_once()
                if TASK.check_success():
                    success = (seed, side)
                    break
            except Exception:
                pass
        _record(
            f"{familiarity}: {noun} target graspable",
            success is not None,
            True,
            note=(
                f"model=base{model_id} seed={success[0]} arm={success[1]} "
                f"attempts={attempts}"
                if success
                else f"model=base{model_id} no success in {attempts} attempts"
            ),
        )


if len(UNSEEN_POOL) < 4:
    raise RuntimeError(
        "UNSEEN_POOL is not locked; Layer-B tests require at least four production nouns"
    )

for group_index, (familiarity, pool) in enumerate((
    ("seen", SEEN_POOL),
    ("unseen", UNSEEN_POOL),
)):
    base = 20000 + group_index * 10000
    _negative_cases(familiarity, pool, base)
    _positive_cases(familiarity, pool, base + 1000)

# Never leave probe overrides enabled for an imported/reused TASK instance.
_configure(None)

print(f"\n==== {sum(RESULTS)}/{len(RESULTS)} passed ====")
sys.exit(0 if RESULTS and all(RESULTS) else 1)
