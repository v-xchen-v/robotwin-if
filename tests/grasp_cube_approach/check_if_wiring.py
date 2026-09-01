#!/usr/bin/env python3
"""IF-wiring check for grasp_cube_approach (step 3): seed -> mode -> instruction -> check.

With APPROACH left at its default None (production), the mode must be derived
purely from the seed: even seed -> top, odd seed -> side, and consecutive pairs
(2k, 2k+1) share one scene. Confirms the instruction {D} phrase matches the mode
and check_success passes in BOTH directions (oracle follows the seed-picked mode).

    conda activate RoboTwin
    python tests/grasp_cube_approach/check_if_wiring.py [N_pairs]
"""
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _parent = os.path.dirname(_REPO)
    if _parent == _REPO:
        raise RuntimeError("repo root not found")
    _REPO = _parent
_RT = os.path.join(_REPO, "third_party", "robotwin")
os.chdir(_RT)
sys.path.insert(0, os.path.join(_RT, "script"))
sys.path.insert(0, _RT)

import collect_data as cd  # noqa: E402

_cap = {}
cd.run = lambda task, args: _cap.update(task=task, args=args)
cd.main(task_name="grasp_cube_approach", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0

# Production path: no override, mode must come from the seed.
TASK.APPROACH = None

N_PAIRS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
ok = True
print("seed  mode  expect  {D}                success  match")
for seed in range(N_PAIRS * 2):
    TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
    expect = ["top", "side"][seed % 2]
    TASK.play_once()
    phrase = TASK.info["info"]["{D}"]
    succ = bool(TASK.check_success())
    mode_ok = (TASK.mode == expect)
    phrase_ok = (phrase in (TASK.TOP_PHRASES if expect == "top" else TASK.SIDE_PHRASES))
    row_ok = mode_ok and phrase_ok and succ
    ok = ok and row_ok
    print(f"{seed:4d}  {TASK.mode:4}  {expect:4}    {phrase:18}  {str(succ):5}    {'OK' if row_ok else 'BAD'}")

print("\nseed->mode wiring:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
