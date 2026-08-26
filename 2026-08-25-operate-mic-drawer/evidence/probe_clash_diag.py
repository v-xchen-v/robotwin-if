#!/usr/bin/env python3
"""Isolation diagnostic for the grasp_drawer failure.

Per open-arm, three conditions on the SAME seed:
  A) drawer-only (skip mic)          -> is the drawer graspable by this arm alone?
  B) mic-first  (native-like order)  -> baseline (what probe_oracle ran)
  C) drawer-first                    -> does grabbing the drawer before the central
                                        mic avoid the two-arms-converge-on-center clash?
"""
import os, sys
# This script lives in /tmp, so don't walk up for the repo — hardcode it.
_RT = "/home/xichen6/Documents/repos/robotwin-if/third_party/robotwin"
os.chdir(_RT)
sys.path.insert(0, os.path.join(_RT, "script"))
sys.path.insert(0, _RT)
import collect_data as cd
_cap = {}
cd.run = lambda t, a: _cap.update(task=t, args=a)
cd.main(task_name="operate_mic_drawer", task_config="demo_clean")
TASK = _cap["task"]; ARGS = dict(_cap["args"]); ARGS["render_freq"] = 0

SEEDS = [int(x) for x in (sys.argv[1:] or ["0", "1", "2"])]

def run(seed, open_arm, skip_mic=False, order="mic_first"):
    TASK.probe_open_arm = open_arm
    TASK.probe_skip_mic = skip_mic
    TASK.probe_order = order
    try:
        TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
    except Exception as e:
        return f"setup_err:{type(e).__name__}"
    try:
        TASK.play_once()
        r = TASK.probe_rec
        return f"fail={r.get('fail_stage')} qpos={r.get('cabinet_qpos')} succ={r.get('success')}"
    except Exception as e:
        return f"exc:{type(e).__name__}:{e}"

for seed in SEEDS:
    for open_arm in ("left", "right"):
        print(f">>> seed {seed} open={open_arm} A drawer-only ...", flush=True)
        a = run(seed, open_arm, skip_mic=True)
        print(f">>> seed {seed} open={open_arm} B mic-first ...", flush=True)
        b = run(seed, open_arm, skip_mic=False, order="mic_first")
        print(f">>> seed {seed} open={open_arm} C drawer-first ...", flush=True)
        c = run(seed, open_arm, skip_mic=False, order="drawer_first")
        print(f"[seed {seed}] open={open_arm:5s} | A drawer-only: {a}", flush=True)
        print(f"                        | B mic-first : {b}", flush=True)
        print(f"                        | C drawer-1st: {c}", flush=True)
