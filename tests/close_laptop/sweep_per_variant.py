#!/usr/bin/env python3
"""Per-variant reliability sweep for close_laptop.

The mixed-variant spike showed close success is deterministic per model_id
(some variants always close, some always crash). This forces each of the 11
laptop variants and runs K episodes each, so we can pick a reliable subset
with confidence instead of from 1-2 incidental samples.

Run inside the RoboTwin conda env, after ./bridge_tasks.sh:
    conda activate RoboTwin
    python tests/close_laptop/sweep_per_variant.py [K]
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
import collect_data as cd  # noqa: E402

K = int(sys.argv[1]) if len(sys.argv) > 1 else 6
N_VARIANTS = 11

_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run
cd.main(task_name="close_laptop", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0


def _frac_open(qpos):
    lo, hi = TASK.laptop.get_qlimits()[0]
    return (qpos - lo) / (hi - lo)


def _setup_variant(mid, seed):
    TASK.ALLOWED_MODEL_IDS = [mid]  # force this variant in load_actors
    s = seed
    for _ in range(20):
        try:
            TASK.setup_demo(now_ep_num=0, seed=s, **ARGS)
            return True
        except Exception:
            s += 101
    return False


print(f"== close_laptop per-variant sweep: {K} eps x {N_VARIANTS} variants ==")
tally = {}
for mid in range(N_VARIANTS):
    ok = crash = stall = 0
    for k in range(K):
        if not _setup_variant(mid, seed=1000 * mid + k):
            continue
        bases = [TASK.laptop.config["contact_points"][i]["base"] for i in range(4)]
        inv = bases[0] == "link_0"
        try:
            TASK.play_once()
        except Exception:
            crash += 1
            continue
        if bool(TASK.check_success()):
            ok += 1
        else:
            stall += 1
    n = ok + crash + stall
    rate = ok / n if n else 0.0
    tally[mid] = (ok, n, rate)
    print(f"  mid={mid:2d} {'INV' if inv else '   '}  "
          f"{ok}/{n} closed ({rate:5.1%})   crash={crash} stall={stall}")

print("\n==== reliable subset (>= 90%) ====")
good = [m for m, (o, n, r) in tally.items() if n and r >= 0.90]
print(f"  {good}   ({len(good)}/{N_VARIANTS} variants)")
overall_good = sum(tally[m][0] for m in good)
overall_n = sum(tally[m][1] for m in good)
if overall_n:
    print(f"  subset pooled rate: {overall_good}/{overall_n} ({overall_good/overall_n:.1%})")
