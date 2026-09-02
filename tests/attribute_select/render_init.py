#!/usr/bin/env python3
"""Render ONLY the initial scene (observer frame, no grasp) for a range of seeds,
to inspect scene variety across scene_seeds. Fast (no play_once).

Run: python tests/attribute_select/render_init.py [seeds...]   # default 8..15
Output -> notes/.../evidence/init_<seed>_<axis><value>.png
"""
import os
import sys
import numpy as np
from PIL import Image

_REPO = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _p = os.path.dirname(_REPO)
    if _p == _REPO:
        raise RuntimeError("repo root not found")
    _REPO = _p
_RT = os.path.join(_REPO, "third_party", "robotwin")
OUT = os.path.join(_REPO, "notes", "2026-09-01-attribute-select", "evidence")
os.chdir(_RT)
sys.path.insert(0, os.path.join(_RT, "script"))
sys.path.insert(0, _RT)

import collect_data as cd  # noqa: E402

SEEDS = [int(s) for s in sys.argv[1:]] or list(range(8, 16))
_cap = {}
cd.run = lambda task, args: _cap.update(task=task, args=args)
cd.main(task_name="attribute_select", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"]); ARGS["render_freq"] = 0

frames = []
for seed in SEEDS:
    TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
    TASK.scene.update_render()
    img = TASK.cameras.get_observer_rgb()
    tpos = tuple(round(float(v), 2) for v in TASK.target.get_pose().p[:2])
    print(f"seed {seed}: axis={TASK.axis} value={TASK.value} "
          f"target='{TASK._adj_phrase()}' target_xy={tpos}")
    frames.append(img)
    TASK.close_env()

# tile into a grid (2 rows) for one glance
n = len(frames); cols = (n + 1) // 2
h, w = frames[0].shape[:2]
grid = np.full((2 * h, cols * w, 3), 240, np.uint8)
for i, f in enumerate(frames):
    r, c = divmod(i, cols)
    grid[r * h:(r + 1) * h, c * w:(c + 1) * w] = f
Image.fromarray(grid).save(os.path.join(OUT, "init_scenes_grid.png"))
print("wrote init_scenes_grid.png")
