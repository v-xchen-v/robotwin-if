#!/usr/bin/env python3
import os, sys
import numpy as np
_RT = "/home/xichen6/Documents/repos/robotwin-if/third_party/robotwin"
os.chdir(_RT); sys.path.insert(0, os.path.join(_RT, "script")); sys.path.insert(0, _RT)
import collect_data as cd
_cap = {}
cd.run = lambda t, a: _cap.update(task=t, args=a)
cd.main(task_name="operate_mic_drawer", task_config="demo_clean")
TASK = _cap["task"]; ARGS = dict(_cap["args"]); ARGS["render_freq"] = 0

for seed in [int(x) for x in (sys.argv[1:] or ["1", "2", "3"])]:
    try:
        TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
        TASK.play_once()
    except Exception as e:
        print(f"[seed {seed}] EXC {type(e).__name__}: {e}", flush=True); continue
    q = np.atleast_1d(TASK.cabinet.get_qpos())
    mic = TASK.microphone.get_pose().p
    fp = TASK.cabinet.get_functional_point(0)
    xy = np.abs(mic[:2] - fp[:2])
    rise = float(mic[2] - TASK.origin_z)
    po = (TASK.robot.is_left_gripper_open() if TASK.place_arm == "left" else TASK.robot.is_right_gripper_open())
    print(f"[seed {seed}] plan_success={TASK.plan_success} drawer_q={round(float(q[0]),4)} "
          f"mic={[round(float(v),3) for v in mic[:3]]} fp={[round(float(v),3) for v in fp[:3]]} "
          f"xy=({round(float(xy[0]),3)},{round(float(xy[1]),3)}) rise={round(rise,4)} place_open={po}", flush=True)
