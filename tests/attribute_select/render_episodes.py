#!/usr/bin/env python3
"""Render a few attribute_select episodes (initial + post-grasp frames) so we
can eyeball the scenes and oracle behavior. Uses the env's own observer camera
(third-view, with arms + table). Not the heavy collect pipeline.

Run:
    conda activate RoboTwin
    python tests/attribute_select/render_episodes.py [seeds...]   # default 0 2 4 6
Output -> notes/2026-09-01-attribute-select/evidence/ep_<seed>_<axis><value>.png
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

SEEDS = [int(s) for s in sys.argv[1:]] or [0, 2, 4, 6]

_cap = {}
cd.run = lambda task, args: _cap.update(task=task, args=args)
cd.main(task_name="attribute_select", task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"]); ARGS["render_freq"] = 0


def observer(task):
    task.scene.update_render()
    return task.cameras.get_observer_rgb()


for seed in SEEDS:
    TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
    axis, value = TASK.axis, TASK.value
    before = observer(TASK)
    TASK.play_once()
    after = observer(TASK)
    ok = bool(TASK.check_success())
    pair = np.concatenate([before, after], axis=1)   # initial | post-grasp
    fn = f"ep_{seed}_{axis}{value}_{'ok' if ok else 'fail'}.png"
    Image.fromarray(pair).save(os.path.join(OUT, fn))
    print(f"seed {seed}: axis={axis} value={value} target='{TASK._adj_phrase()}' check={ok} -> {fn}")
    TASK.close_env()
