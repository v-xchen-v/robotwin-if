#!/usr/bin/env python3
"""Oracle spike for the IF-Verb-Select open direction from the shared mid-state.

Confirms that, starting from the same ~50% mid-state and variant subset {1,9,10}
used by close_laptop, the native open motion (grasp screen 0 -> servo toward 1)
drives the hinge into a HIGH open band clearly above 50%. Reports the final open
fraction per episode AND the distribution of max reached, so the OPEN_TARGET
threshold can be calibrated to what the servo actually achieves.

Run inside the RoboTwin conda env, after ./bridge_tasks.sh:
    conda activate RoboTwin
    python tests/close_laptop/spike_open_success_rate.py [N]
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

TASK_NAME = "open_laptop_mid"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 30

_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run
cd.main(task_name=TASK_NAME, task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0


def _frac_open(qpos):
    lo, hi = TASK.laptop.get_qlimits()[0]
    return (qpos - lo) / (hi - lo)


n_ok = 0
n_run = 0
finals = []
print(f"== open_laptop_mid spike: {N} episodes, OPEN_TARGET={TASK.OPEN_TARGET:.0%} ==")
for ep in range(N):
    seed = ep
    last = None
    for _ in range(20):
        try:
            TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
            last = None
            break
        except Exception as e:
            last = e
            seed += N
    if last is not None:
        print(f"[ep {ep:02d}] SKIP: no stable scene ({last})")
        continue

    mid = TASK.model_id
    try:
        TASK.play_once()
    except Exception as e:
        # Sim state persists after the exception; read how far it opened before
        # crashing to tell "crashed immediately" from "opened then crashed".
        crash_frac = _frac_open(TASK.laptop.get_qpos()[0])
        print(f"[ep {ep:02d}] ERROR  mid={mid:2d} @ {crash_frac:5.1%} open  {type(e).__name__}")
        n_run += 1
        continue
    final_frac = _frac_open(TASK.laptop.get_qpos()[0])
    ok = bool(TASK.check_success())
    finals.append(final_frac)
    n_run += 1
    n_ok += int(ok)
    print(f"[ep {ep:02d}] {'OK ' if ok else 'FAIL'} mid={mid:2d} "
          f"open 50.0% -> {final_frac:5.1%}  (target >= {TASK.OPEN_TARGET:.0%})")

rate = n_ok / n_run if n_run else 0.0
print("\n==== summary ====")
print(f"{n_ok}/{n_run} opened past {TASK.OPEN_TARGET:.0%}  ({rate:.1%})")
if finals:
    fa = np.array(finals)
    print(f"final open fraction: min={fa.min():.1%} med={np.median(fa):.1%} "
          f"max={fa.max():.1%}  (calibrate OPEN_TARGET to what's reliably reached)")
