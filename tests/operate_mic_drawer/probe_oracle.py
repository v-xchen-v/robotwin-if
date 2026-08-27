#!/usr/bin/env python3
"""Oracle-feasibility probe for Operate-Microphone-Drawer.

Question: with the microphone spawned in a CENTRAL band (both arms reachable) and
the cabinet center-back, is the bimanual task oracle-feasible for BOTH role
assignments — open=LEFT/place=RIGHT and open=RIGHT/place=LEFT — or does the "far arm
places into the drawer" case fail planning (the cross-body failure that sank
Place-Relative's on-top oracle)?

For each seed we build the SAME scene twice (np.random is reseeded from the seed, so
the mic pose is identical) and run each assignment once, recording:
  - success        : mic ends in drawer functional point, lifted band (native-style)
  - fail_stage     : first step where planning went False (grasp_mic / grasp_drawer /
                     pull_drawer / lift_mic / place_mic), or "exception"
  - cabinet_qpos   : to calibrate a drawer-open threshold
  - mic_z_rise, mic_to_fp_xy : physical diagnostics

Run inside the RoboTwin conda env:
    conda activate RoboTwin
    python tests/operate_mic_drawer/probe_oracle.py [num_seeds] [base_seed]
"""
import os
import sys
from collections import Counter

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

import collect_data as cd  # noqa: E402

_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run
cd.main(task_name="operate_mic_drawer", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0

NUM = int(sys.argv[1]) if len(sys.argv) > 1 else 16
BASE = int(sys.argv[2]) if len(sys.argv) > 2 else 0


def stable_setup(seed, open_arm):
    """Setup the scene at `seed` with the given forced open-arm. Returns True on
    success; raises are surfaced by the caller advancing the seed."""
    TASK.probe_open_arm = open_arm
    TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)


def run_one(seed, open_arm):
    try:
        stable_setup(seed, open_arm)
    except Exception as e:
        return {"setup_error": type(e).__name__}
    try:
        TASK.play_once()
        return dict(TASK.probe_rec)
    except Exception as e:
        return {"open_arm": open_arm, "place_arm": ("right" if open_arm == "left" else "left"),
                "fail_stage": "exception", "exc": f"{type(e).__name__}: {e}", "success": False}


def find_seed(start):
    s = start
    for _ in range(30):
        try:
            stable_setup(s, "left")
            return s
        except Exception:
            s += 1
    return None


results = {"left": [], "right": []}  # keyed by open_arm
rows = []
seed = BASE
for i in range(NUM):
    s = find_seed(seed)
    if s is None:
        print(f"[trial {i}] no stable seed near {seed}, skipping")
        seed += 1
        continue
    seed = s + 1
    for open_arm in ("left", "right"):
        rec = run_one(s, open_arm)
        results[open_arm].append(rec)
        tag = "OK " if rec.get("success") else "XX "
        rows.append((s, open_arm, rec))
        print(f"[seed {s}] open={open_arm:5s} place={rec.get('place_arm','?'):5s} "
              f"{tag} fail={rec.get('fail_stage')} "
              f"z_rise={rec.get('mic_z_rise')} fp_xy={rec.get('mic_to_fp_xy')} "
              f"qpos={rec.get('cabinet_qpos')}")

print("\n================ SUMMARY ================")
for open_arm in ("left", "right"):
    recs = results[open_arm]
    n = len(recs)
    ok = sum(1 for r in recs if r.get("success"))
    stages = Counter(r.get("fail_stage") for r in recs if not r.get("success"))
    print(f"open={open_arm:5s} (place={'right' if open_arm=='left' else 'left'}): "
          f"{ok}/{n} oracle success")
    if stages:
        print(f"    fail stages: {dict(stages)}")
# qpos calibration: show drawer joint values from successful placements
opened = [r.get("cabinet_qpos") for arm in ("left", "right") for r in results[arm] if r.get("success")]
if opened:
    print(f"\ncabinet_qpos on success (drawer-open calibration): sample={opened[:5]}")
