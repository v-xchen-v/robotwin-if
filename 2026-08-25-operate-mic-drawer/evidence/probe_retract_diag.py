#!/usr/bin/env python3
"""Attribute the drawer slide-back to a phase: release / lift / settle / move-to-origin."""
import os, sys
_RT = "/home/xichen6/Documents/repos/robotwin-if/third_party/robotwin"
os.chdir(_RT); sys.path.insert(0, os.path.join(_RT, "script")); sys.path.insert(0, _RT)
import collect_data as cd
_cap = {}
cd.run = lambda t, a: _cap.update(task=t, args=a)
cd.main(task_name="operate_mic_drawer", task_config="demo_clean")
TASK = _cap["task"]; ARGS = dict(_cap["args"]); ARGS["render_freq"] = 0

for seed in [int(x) for x in (sys.argv[1:] or ["0", "1"])]:
    for open_arm in ("left", "right"):
        TASK.probe_open_arm = open_arm
        TASK.probe_skip_mic = False
        TASK.probe_order = "retract_diag"
        try:
            TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
            TASK.play_once()
            r = TASK.probe_rec
            print(f"[seed {seed}] open={open_arm:5s} pull={r.get('q_pull')} release={r.get('q_release')} "
                  f"lift={r.get('q_lift')} settle={r.get('q_settle')} origin={r.get('q_origin')} "
                  f"fail={r.get('fail_stage')}", flush=True)
        except Exception as e:
            print(f"[seed {seed}] open={open_arm} EXC {type(e).__name__}: {e}", flush=True)
