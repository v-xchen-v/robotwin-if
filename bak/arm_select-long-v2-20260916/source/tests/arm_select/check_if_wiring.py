#!/usr/bin/env python3
"""IF-wiring check for arm_select (step 3): seed -> mode -> instruction -> check.

With ARM_OVERRIDE left at its default None (production), the mode must be derived
purely from the seed: even seed -> left, odd seed -> right, and consecutive pairs
(2k, 2k+1) share one scene (identical box pose, since the box is fixed). Confirms
the instruction {a} word matches the mode and check_success passes in BOTH
directions (oracle follows the seed-picked arm).

    conda activate RoboTwin
    python tests/arm_select/check_if_wiring.py [N_pairs]
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

import numpy as np  # noqa: E402
import collect_data as cd  # noqa: E402

_cap = {}
cd.run = lambda task, args: _cap.update(task=task, args=args)
cd.main(task_name="arm_select", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0

# Production path: no override, mode must come from the seed.
TASK.ARM_OVERRIDE = None
TASK.ORACLE_ARM = None

N_PAIRS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
ok = True
pair_poses = {}
print("seed  mode  expect  {a}      success  match")
for seed in range(N_PAIRS * 2):
    TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
    expect = ["left", "right"][seed % 2]
    # Record the box pose BEFORE acting, to check the pair shares one scene.
    box_pose = np.array(TASK.box.get_pose().p, dtype=np.float64)
    scene_seed = seed // 2
    pair_poses.setdefault(scene_seed, []).append(box_pose)
    TASK.play_once()
    arm_word = TASK.info["info"]["{a}"]
    succ = bool(TASK.check_success())
    mode_ok = (TASK.mode == expect)
    word_ok = (arm_word == expect)
    row_ok = mode_ok and word_ok and succ
    ok = ok and row_ok
    print(f"{seed:4d}  {TASK.mode:5} {expect:5}  {arm_word:5}   {str(succ):5}    {'OK' if row_ok else 'BAD'}")

# Each pair (2k, 2k+1) must share an identical box pose (same scene).
print("\npair scene identity (box pose within pair):")
pair_ok = True
for ss, poses in sorted(pair_poses.items()):
    if len(poses) == 2:
        d = float(np.linalg.norm(poses[0] - poses[1]))
        same = d < 1e-6
        pair_ok = pair_ok and same
        print(f"  scene {ss}: |Δpose|={d:.2e}  {'SAME' if same else 'DIFFERENT'}")

ok = ok and pair_ok
print("\nseed->mode wiring:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
