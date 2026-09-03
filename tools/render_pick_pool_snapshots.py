#!/usr/bin/env python3
"""Render real-texture SAPIEN snapshots for Pick-Diverse-Object pools.

Run inside the RoboTwin conda environment:

    conda run -n RoboTwin python tools/render_pick_pool_snapshots.py --group unseen-candidates

The candidate sheet is visual evidence only. A metadata-qualified or visually plausible
variant is not added to the production Unseen pool until the settle/grasp probe passes.
"""
import argparse
import json
import os
import re
import sys
from textwrap import fill

import matplotlib
import numpy as np
import trimesh
from PIL import Image

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import sapien  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from tasks.envs._pick_diverse_object_pool import (  # noqa: E402
    MANUAL_UNSEEN_CANDIDATES,
    SEEN_POOL,
    UNSEEN_CANDIDATES,
    iter_variants,
)

ASSETS = os.path.join(REPO, "third_party", "robotwin", "assets", "objects")
OUT = os.path.join(REPO, "notes", "2026-08-21-pick-diverse-object", "evidence", "pool")
GROUPS = {
    "seen": SEEN_POOL,
    "unseen-candidates": UNSEEN_CANDIDATES,
    "manual-candidates": MANUAL_UNSEEN_CANDIDATES,
}

# Exact-ID reachability in the native/raw task Python at RoboTwin commit 8187d5b.
# A task is listed only if its explicit ID set or model_data scan can select this
# exact variant; category-only references with an incompatible ID set are excluded.
SEEN_RAW_TASKS_BY_VARIANT = {
    ("001_bottle", 13): (
        "pick_diverse_bottles", "shake_bottle", "shake_bottle_horizontally",
        "adjust_bottle", "pick_dual_bottles",
    ),
    ("021_cup", 0): ("place_empty_cup",),
    ("041_shoe", 8): ("place_dual_shoes", "place_shoe"),
    ("039_mug", 0): ("hanging_mug",),
    ("071_can", 2): ("place_can_basket", "place_cans_plasticbox"),
    ("057_toycar", 5): (
        "place_a2b_left", "place_a2b_right", "place_object_basket",
        "place_object_stand", "put_object_cabinet",
    ),
    ("077_phone", 1): (
        "place_a2b_left", "place_a2b_right", "place_phone_stand",
        "put_object_cabinet",
    ),
    ("107_soap", 0): (
        "place_a2b_left", "place_a2b_right", "put_object_cabinet",
    ),
    ("006_hamburg", 0): ("place_burger_fries",),
    ("075_bread", 5): (
        "place_a2b_left", "place_a2b_right", "place_bread_basket",
        "place_bread_skillet", "put_object_cabinet",
    ),
    ("113_coffee-box", 1): (
        "place_a2b_left", "place_a2b_right", "put_object_cabinet",
    ),
    ("047_mouse", 2): (
        "place_a2b_left", "place_a2b_right", "place_mouse_pad",
        "place_object_scale", "place_object_stand", "put_object_cabinet",
    ),
}

# Exact IDs reachable from at least one native/raw task loader at commit 8187d5b.
# Some loaders enumerate explicit IDs; the generic A-to-B/cabinet tasks scan every
# model_data<ID>.json available for their supported categories.
SEEN_RAW_REACHABLE_IDS = {
    "001_bottle": frozenset(range(20)),
    "021_cup": frozenset(range(8)),
    "041_shoe": frozenset(range(10)),
    "039_mug": frozenset(range(10)),
    "071_can": frozenset((0, 1, 2, 3, 5, 6)),
    "057_toycar": frozenset(range(6)),
    "077_phone": frozenset(range(5)),
    "107_soap": frozenset(range(4)),
    "006_hamburg": frozenset(range(6)),
    "075_bread": frozenset(range(7)),
    "113_coffee-box": frozenset(range(7)),
    "047_mouse": frozenset(range(3)),
}


def raw_tasks_for_seen_variant(obj, base_id):
    tasks = []

    def add(*names):
        for name in names:
            if name not in tasks:
                tasks.append(name)

    if obj == "001_bottle" and base_id in range(20):
        add("pick_diverse_bottles", "shake_bottle", "shake_bottle_horizontally")
        if base_id in (13, 16):
            add("adjust_bottle", "pick_dual_bottles")
    elif obj == "021_cup":
        if base_id == 0:
            add("place_empty_cup")
        elif base_id in range(1, 8):
            add("place_container_plate")
    elif obj == "041_shoe" and base_id in range(10):
        add("place_dual_shoes", "place_shoe")
    elif obj == "039_mug" and base_id in range(10):
        add("hanging_mug")
    elif obj == "071_can" and base_id in (0, 1, 2, 3, 5, 6):
        add("place_can_basket", "place_cans_plasticbox")
    elif obj == "057_toycar" and base_id in range(6):
        add(
            "place_a2b_left", "place_a2b_right", "place_object_basket",
            "place_object_stand", "put_object_cabinet",
        )
    elif obj == "077_phone" and base_id in range(5):
        add("place_a2b_left", "place_a2b_right")
        if base_id in (0, 1, 2, 4):
            add("place_phone_stand")
        add("put_object_cabinet")
    elif obj == "107_soap" and base_id in range(4):
        add("place_a2b_left", "place_a2b_right", "put_object_cabinet")
    elif obj == "006_hamburg" and base_id in range(6):
        add("place_burger_fries")
    elif obj == "075_bread" and base_id in range(7):
        add("place_a2b_left", "place_a2b_right")
        if base_id in (0, 1, 3, 5, 6):
            add("place_bread_basket", "place_bread_skillet")
        add("put_object_cabinet")
    elif obj == "113_coffee-box" and base_id in range(7):
        add("place_a2b_left", "place_a2b_right", "put_object_cabinet")
    elif obj == "047_mouse" and base_id in range(3):
        add(
            "place_a2b_left", "place_a2b_right", "place_mouse_pad",
            "place_object_scale", "place_object_stand", "put_object_cabinet",
        )
    return tuple(tasks)


def frame_mat44(center, radius, fovy, azim_deg=40, elev_deg=22, margin=1.5):
    d = margin * radius / np.tan(fovy / 2)
    a, e = np.deg2rad(azim_deg), np.deg2rad(elev_deg)
    view = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    cam_pos = center + d * view
    fwd = center - cam_pos
    fwd /= np.linalg.norm(fwd)
    left = np.cross([0, 0, 1.0], fwd)
    left /= np.linalg.norm(left)
    up = np.cross(fwd, left)
    mat = np.eye(4)
    mat[:3, :3] = np.stack([fwd, left, up], axis=1)
    mat[:3, 3] = cam_pos
    return mat


def render_variant(scene_ctx, obj, base_id, size=340):
    engine, _renderer = scene_ctx
    glb = os.path.join(ASSETS, obj, "visual", f"base{base_id}.glb")
    tm = trimesh.load(glb, force="scene")
    center = tm.bounds.mean(0)
    radius = float(np.linalg.norm(tm.bounds[1] - tm.bounds[0]) / 2)

    scene = engine.create_scene(sapien.SceneConfig())
    scene.set_ambient_light([0.6, 0.6, 0.6])
    scene.add_directional_light([0.3, 0.4, -1], [1.3, 1.3, 1.3], shadow=False)
    scene.add_directional_light([-0.6, -0.3, -0.6], [0.5, 0.5, 0.5], shadow=False)
    scene.add_point_light([center[0] + radius, center[1], center[2] + radius], [3, 3, 3])
    builder = scene.create_actor_builder()
    builder.add_visual_from_file(filename=glb)
    builder.build_kinematic().set_pose(sapien.Pose())
    fovy = np.deg2rad(30)
    cam = scene.add_camera(name="snap", width=size, height=size, fovy=fovy, near=0.01, far=100)
    cam.entity.set_pose(sapien.Pose(frame_mat44(center, radius, fovy)))
    scene.update_render()
    cam.take_picture()
    rgba = np.clip(cam.get_picture("Color"), 0, 1)
    comp = (rgba[..., :3] * rgba[..., 3:4] + (1 - rgba[..., 3:4])) * 255
    return Image.fromarray(comp.astype(np.uint8))


def selected_variants(group):
    if group == "all":
        for name, pool in GROUPS.items():
            for row in iter_variants(pool):
                yield (name, *row)
        return
    for row in iter_variants(GROUPS[group]):
        yield (group, *row)


def available_variant_ids(obj):
    object_dir = os.path.join(ASSETS, obj)
    ids = []
    for filename in os.listdir(object_dir):
        match = re.fullmatch(r"model_data(\d+)\.json", filename)
        if match is None:
            continue
        base_id = int(match.group(1))
        visual = os.path.join(object_dir, "visual", f"base{base_id}.glb")
        if os.path.isfile(visual):
            ids.append(base_id)
    return sorted(ids)


OBJECT_ATLAS_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>RoboTwin Object Atlas</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Archivo+Narrow:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet" media="print" onload="this.media='all'" />
<style>
:root {
  --ground: #e9eff3;
  --grid-line: rgba(39, 70, 92, 0.07);
  --surface: #f8fbfc;
  --surface-raised: #ffffff;
  --surface-muted: #dfe7ec;
  --ink: #172631;
  --ink-soft: #5b6f7d;
  --line: #c4d1d9;
  --line-strong: #91a5b2;
  --accent: #2457c5;
  --accent-soft: #dce6ff;
  --selected: #08766d;
  --selected-soft: #d6efeb;
  --warning: #9d402d;
  --warning-soft: #f4ddd7;
  --shadow: rgba(19, 41, 55, 0.14);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground: #10181e;
    --grid-line: rgba(172, 199, 215, 0.055);
    --surface: #162129;
    --surface-raised: #1b2831;
    --surface-muted: #22323c;
    --ink: #edf4f7;
    --ink-soft: #a5b7c2;
    --line: #344750;
    --line-strong: #58707d;
    --accent: #7da2ff;
    --accent-soft: #24375f;
    --selected: #61cbbd;
    --selected-soft: #173f3b;
    --warning: #ef917b;
    --warning-soft: #4b2b28;
    --shadow: rgba(0, 0, 0, 0.35);
  }
}
:root[data-theme="dark"] {
  --ground: #10181e;
  --grid-line: rgba(172, 199, 215, 0.055);
  --surface: #162129;
  --surface-raised: #1b2831;
  --surface-muted: #22323c;
  --ink: #edf4f7;
  --ink-soft: #a5b7c2;
  --line: #344750;
  --line-strong: #58707d;
  --accent: #7da2ff;
  --accent-soft: #24375f;
  --selected: #61cbbd;
  --selected-soft: #173f3b;
  --warning: #ef917b;
  --warning-soft: #4b2b28;
  --shadow: rgba(0, 0, 0, 0.35);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  min-width: 0;
  overflow-x: hidden;
  color: var(--ink);
  background-color: var(--ground);
  background-image:
    linear-gradient(var(--grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
  background-size: 24px 24px;
  font-family: "IBM Plex Sans", "Noto Sans", Arial, sans-serif;
  line-height: 1.45;
}
button, input { font: inherit; }
button { color: inherit; }
.skip-link {
  position: fixed;
  left: 1rem;
  top: -5rem;
  z-index: 100;
  padding: .65rem .9rem;
  color: var(--surface-raised);
  background: var(--ink);
}
.skip-link:focus { top: 1rem; }
.masthead {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 2.5rem;
  align-items: end;
  max-width: 1800px;
  margin: 0 auto;
  padding: 2.8rem clamp(1rem, 3vw, 3.5rem) 2.2rem;
}
.eyebrow,
.metric-label,
.section-code,
.control-label,
.card-tasks,
.selection-key {
  font-family: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
}
.eyebrow {
  margin: 0 0 .55rem;
  color: var(--accent);
  font-size: .72rem;
  font-weight: 500;
  letter-spacing: .12em;
  text-transform: uppercase;
}
h1, h2, p { margin: 0; }
h1 {
  max-width: 12ch;
  font-family: "Archivo Narrow", "Arial Narrow", sans-serif;
  font-size: clamp(2.6rem, 5vw, 5.3rem);
  font-weight: 700;
  letter-spacing: -.025em;
  line-height: .88;
  text-wrap: balance;
}
.dek {
  max-width: 66ch;
  margin-top: 1.1rem;
  color: var(--ink-soft);
  font-size: .98rem;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(8rem, 1fr));
  border-top: 1px solid var(--line-strong);
  border-left: 1px solid var(--line-strong);
}
.metric {
  min-width: 8.5rem;
  padding: .8rem 1rem .95rem;
  border-right: 1px solid var(--line-strong);
  border-bottom: 1px solid var(--line-strong);
  background: var(--surface);
}
.metric-value {
  display: block;
  font-family: "Archivo Narrow", "Arial Narrow", sans-serif;
  font-size: 2rem;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.metric-label {
  display: block;
  margin-top: .35rem;
  color: var(--ink-soft);
  font-size: .62rem;
  letter-spacing: .06em;
  text-transform: uppercase;
}
.toolbar {
  position: sticky;
  top: 0;
  z-index: 30;
  display: grid;
  grid-template-columns: minmax(15rem, 1fr) auto auto;
  gap: 1rem;
  align-items: end;
  padding: .8rem clamp(1rem, 3vw, 3.5rem);
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line-strong);
  background: color-mix(in srgb, var(--surface) 93%, transparent);
  box-shadow: 0 5px 22px var(--shadow);
  backdrop-filter: blur(14px);
}
.search-wrap,
.filter-wrap { display: grid; gap: .35rem; }
.control-label {
  color: var(--ink-soft);
  font-size: .62rem;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.search {
  width: 100%;
  min-height: 2.45rem;
  padding: .55rem .75rem;
  color: var(--ink);
  border: 1px solid var(--line-strong);
  border-radius: 2px;
  outline: none;
  background: var(--surface-raised);
}
.search:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.filter-row { display: flex; flex-wrap: wrap; gap: .35rem; }
.filter,
.theme-button,
.action-button {
  min-height: 2.45rem;
  padding: .5rem .75rem;
  border: 1px solid var(--line-strong);
  border-radius: 2px;
  background: var(--surface-raised);
  cursor: pointer;
}
.filter:hover,
.theme-button:hover,
.action-button:hover { border-color: var(--accent); }
.filter[aria-pressed="true"] {
  color: var(--surface-raised);
  border-color: var(--ink);
  background: var(--ink);
}
.theme-button:focus-visible,
.filter:focus-visible,
.action-button:focus-visible,
.category-link:focus-visible,
.variant-card:focus-within {
  outline: 3px solid var(--accent-soft);
  outline-offset: 2px;
}
.toolbar-tail { display: flex; align-items: center; gap: .75rem; }
.visible-count {
  min-width: 7.2rem;
  color: var(--ink-soft);
  font-family: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
  font-size: .74rem;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.workspace {
  display: grid;
  grid-template-columns: 10.5rem minmax(0, 1fr) 18rem;
  gap: clamp(1rem, 2vw, 2rem);
  align-items: start;
  max-width: 1800px;
  margin: 0 auto;
  padding: 2rem clamp(1rem, 3vw, 3.5rem) 5rem;
}
.category-index,
.selection-panel {
  position: sticky;
  top: 5.9rem;
  max-height: calc(100vh - 7rem);
  overflow-y: auto;
}
.index-title,
.selection-title {
  margin: 0 0 .75rem;
  font-family: "Archivo Narrow", "Arial Narrow", sans-serif;
  font-size: 1.25rem;
  font-weight: 600;
}
.category-links { display: grid; border-top: 1px solid var(--line); }
.category-link {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: .5rem;
  padding: .55rem .15rem;
  color: var(--ink-soft);
  border-bottom: 1px solid var(--line);
  text-decoration: none;
}
.category-link:hover { color: var(--accent); }
.category-link span:last-child {
  font-family: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
  font-size: .68rem;
}
.atlas { display: grid; gap: 2.5rem; min-width: 0; }
.shelf {
  min-width: 0;
  scroll-margin-top: 6.7rem;
  border-top: 2px solid var(--ink);
}
.shelf[hidden], .variant-card[hidden] { display: none; }
.shelf-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: baseline;
  padding: .65rem 0 .8rem;
}
.shelf-title {
  font-family: "Archivo Narrow", "Arial Narrow", sans-serif;
  font-size: 1.8rem;
  font-weight: 700;
  line-height: 1;
  text-transform: uppercase;
}
.section-code { color: var(--ink-soft); font-size: .72rem; }
.shelf-count {
  color: var(--ink-soft);
  font-family: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
  font-size: .72rem;
  font-variant-numeric: tabular-nums;
}
.variant-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(11.8rem, 1fr));
  gap: .8rem;
}
.variant-card {
  position: relative;
  display: grid;
  min-width: 0;
  overflow: hidden;
  color: var(--ink);
  border: 1px solid var(--line-strong);
  border-radius: 2px;
  background: var(--surface-raised);
  cursor: pointer;
  transition: transform 140ms ease, border-color 140ms ease, box-shadow 140ms ease;
}
.variant-card:hover {
  transform: translateY(-2px);
  border-color: var(--ink);
  box-shadow: 0 8px 20px var(--shadow);
}
.variant-card.is-current { border-top: 4px solid var(--accent); }
.variant-card.is-selected {
  border-color: var(--selected);
  box-shadow: 0 0 0 3px var(--selected-soft);
}
.variant-card.is-unreachable {
  cursor: not-allowed;
  background:
    repeating-linear-gradient(-45deg, transparent 0 8px, var(--warning-soft) 8px 10px),
    var(--surface-raised);
}
.variant-card.is-unreachable:hover { transform: none; border-color: var(--warning); box-shadow: none; }
.variant-check {
  position: absolute;
  top: .55rem;
  right: .55rem;
  z-index: 2;
  width: 1.25rem;
  height: 1.25rem;
  margin: 0;
  appearance: none;
  border: 1px solid var(--line-strong);
  border-radius: 1px;
  background: var(--surface-raised);
  cursor: pointer;
}
.variant-check:checked { border-color: var(--selected); background: var(--selected); }
.variant-check:checked::after {
  content: "";
  position: absolute;
  left: .34rem;
  top: .12rem;
  width: .32rem;
  height: .62rem;
  border: solid var(--surface-raised);
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}
.variant-check:disabled { opacity: .42; cursor: not-allowed; }
.variant-stage {
  position: relative;
  aspect-ratio: 1;
  overflow: hidden;
  border-bottom: 1px solid var(--line);
  background-color: #ffffff;
  background-image:
    linear-gradient(rgba(32, 61, 79, .045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(32, 61, 79, .045) 1px, transparent 1px);
  background-size: 20px 20px;
}
.variant-stage::after {
  content: "";
  position: absolute;
  inset: 50% auto auto 50%;
  width: 24px;
  height: 24px;
  border-top: 1px solid rgba(32, 61, 79, .15);
  border-left: 1px solid rgba(32, 61, 79, .15);
  transform: translate(-12px, -12px);
  pointer-events: none;
}
.variant-image { display: block; width: 100%; height: 100%; object-fit: cover; }
.card-body { display: grid; gap: .5rem; padding: .7rem .75rem .78rem; }
.card-head { display: flex; gap: .5rem; align-items: center; min-width: 0; }
.base-id {
  font-family: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
  font-size: .86rem;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.badge {
  padding: .12rem .38rem;
  border: 1px solid currentColor;
  border-radius: 1px;
  font-family: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
  font-size: .56rem;
  font-weight: 500;
  letter-spacing: .05em;
  line-height: 1.35;
  text-transform: uppercase;
}
.badge-current { margin-left: auto; color: var(--accent); background: var(--accent-soft); }
.reachability {
  display: flex;
  gap: .4rem;
  align-items: center;
  color: var(--ink-soft);
  font-size: .72rem;
}
.reachability::before {
  content: "";
  width: .48rem;
  height: .48rem;
  border: 1px solid var(--ink-soft);
  border-radius: 50%;
  background: transparent;
}
.is-unreachable .reachability { color: var(--warning); font-weight: 600; }
.is-unreachable .reachability::before { border-color: var(--warning); background: var(--warning); }
.card-tasks {
  min-height: 2.35rem;
  overflow: hidden;
  color: var(--ink-soft);
  font-size: .61rem;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}
.selection-panel {
  border-top: 4px solid var(--selected);
  background: var(--surface);
  box-shadow: 0 8px 24px var(--shadow);
}
.selection-head { padding: 1rem 1rem .8rem; border-bottom: 1px solid var(--line); }
.selection-title { margin: 0; }
.selection-note { margin-top: .35rem; color: var(--ink-soft); font-size: .75rem; }
.selection-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: .45rem;
  padding: .8rem 1rem;
  border-bottom: 1px solid var(--line);
}
.action-button { min-height: 2.15rem; padding: .4rem .55rem; font-size: .74rem; }
.action-button.primary {
  grid-column: 1 / -1;
  color: var(--surface-raised);
  border-color: var(--selected);
  background: var(--selected);
}
.action-button:disabled { opacity: .42; cursor: not-allowed; }
.selection-list { display: grid; max-height: 48vh; overflow-y: auto; }
.selection-empty { padding: 1.2rem 1rem; color: var(--ink-soft); font-size: .78rem; }
.selection-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: .45rem;
  align-items: center;
  padding: .52rem 1rem;
  border-bottom: 1px solid var(--line);
  font-size: .75rem;
}
.selection-key { overflow: hidden; color: var(--ink-soft); font-size: .64rem; text-overflow: ellipsis; white-space: nowrap; }
.remove-button {
  width: 1.5rem;
  height: 1.5rem;
  padding: 0;
  color: var(--ink-soft);
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
}
.remove-button:hover { color: var(--warning); border-color: var(--warning); }
.legend { display: grid; gap: .45rem; padding: 1rem; border-top: 1px solid var(--line); }
.legend-row { display: flex; gap: .5rem; align-items: center; color: var(--ink-soft); font-size: .7rem; }
.legend-mark { width: 1.2rem; height: .55rem; border: 1px solid var(--line-strong); background: var(--surface-raised); }
.legend-mark.current { border-top: 4px solid var(--accent); }
.legend-mark.selected { border-color: var(--selected); box-shadow: 0 0 0 2px var(--selected-soft); }
.legend-mark.unreachable { border-color: var(--warning); background: var(--warning-soft); }
.toast {
  position: fixed;
  right: 1.25rem;
  bottom: 1.25rem;
  z-index: 80;
  max-width: min(24rem, calc(100vw - 2.5rem));
  padding: .7rem .9rem;
  color: var(--surface-raised);
  border: 1px solid var(--ink);
  background: var(--ink);
  box-shadow: 0 8px 24px var(--shadow);
  opacity: 0;
  transform: translateY(.5rem);
  pointer-events: none;
  transition: opacity 140ms ease, transform 140ms ease;
}
.toast.show { opacity: 1; transform: translateY(0); }
@media (max-width: 1240px) {
  .workspace { grid-template-columns: 8.5rem minmax(0, 1fr) 16rem; }
  .variant-grid { grid-template-columns: repeat(auto-fill, minmax(10.8rem, 1fr)); }
}
@media (max-width: 980px) {
  .masthead { grid-template-columns: 1fr; }
  .metrics { max-width: 36rem; }
  .toolbar { grid-template-columns: 1fr; align-items: stretch; }
  .toolbar-tail { justify-content: space-between; }
  .workspace { grid-template-columns: minmax(0, 1fr); }
  .category-index, .selection-panel { position: static; max-height: none; }
  .category-links { grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr)); }
  .selection-list { max-height: 18rem; }
}
@media (max-width: 560px) {
  .masthead { padding-top: 1.8rem; }
  .metrics { grid-template-columns: 1fr 1fr; }
  .metric { min-width: 0; }
  .filter-row { display: grid; grid-template-columns: 1fr 1fr; }
  .filter { width: 100%; }
  .variant-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .55rem; }
  .card-tasks { min-height: 3.2rem; }
  .badge-current { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after { transition-duration: .001ms !important; }
}
</style>
</head>
<body>
<a class="skip-link" href="#atlas">Skip to object variants</a>
<header class="masthead">
  <div>
    <p class="eyebrow">RoboTwin-IF / Seen exact-ID review</p>
    <h1>RoboTwin Object Atlas</h1>
    <p class="dek">Compare every renderable model instance in the 12 current Seen categories. Select only exact IDs you want to retain; IDs outside native raw-task sampling remain visible for audit but cannot be selected.</p>
  </div>
  <div class="metrics" aria-label="Atlas summary">
    <div class="metric"><strong class="metric-value" id="metric-categories">—</strong><span class="metric-label">categories</span></div>
    <div class="metric"><strong class="metric-value" id="metric-variants">—</strong><span class="metric-label">renderable IDs</span></div>
    <div class="metric"><strong class="metric-value" id="metric-reachable">—</strong><span class="metric-label">raw reachable</span></div>
    <div class="metric"><strong class="metric-value" id="metric-current">—</strong><span class="metric-label">current production</span></div>
  </div>
</header>
<nav class="toolbar" aria-label="Atlas controls">
  <label class="search-wrap">
    <span class="control-label">Search noun, asset, baseID, or raw task</span>
    <input class="search" id="search" type="search" placeholder="Try: bottle, base13, place_object_stand" autocomplete="off" />
  </label>
  <div class="filter-wrap">
    <span class="control-label">Show</span>
    <div class="filter-row" id="filters">
      <button class="filter" type="button" data-filter="all" aria-pressed="true">All</button>
      <button class="filter" type="button" data-filter="reachable" aria-pressed="false">Raw reachable</button>
      <button class="filter" type="button" data-filter="unreachable" aria-pressed="false">Not reachable</button>
      <button class="filter" type="button" data-filter="current" aria-pressed="false">Current</button>
      <button class="filter" type="button" data-filter="selected" aria-pressed="false">Selected</button>
    </div>
  </div>
  <div class="toolbar-tail">
    <span class="visible-count" id="visible-count">—</span>
    <button class="theme-button" id="theme-button" type="button">Theme: system</button>
  </div>
</nav>
<div class="workspace">
  <aside class="category-index" aria-label="Category index">
    <h2 class="index-title">Category shelves</h2>
    <nav class="category-links" id="category-links"></nav>
  </aside>
  <main class="atlas" id="atlas"></main>
  <aside class="selection-panel" aria-label="Selected variants">
    <div class="selection-head">
      <h2 class="selection-title">Selection <span id="selection-count">0</span></h2>
      <p class="selection-note">Choose one or more exact IDs per noun, then copy the compact list back to Claude.</p>
    </div>
    <div class="selection-actions">
      <button class="action-button" id="load-current" type="button">Load current set</button>
      <button class="action-button" id="clear-selection" type="button">Clear</button>
      <button class="action-button primary" id="copy-selection" type="button" disabled>Copy selected IDs</button>
    </div>
    <div class="selection-list" id="selection-list"><p class="selection-empty">No variants selected.</p></div>
    <div class="legend" aria-label="Visual key">
      <div class="legend-row"><span class="legend-mark current"></span><span>Current production ID</span></div>
      <div class="legend-row"><span class="legend-mark selected"></span><span>Your selection</span></div>
      <div class="legend-row"><span class="legend-mark unreachable"></span><span>Not exact-ID reachable</span></div>
    </div>
  </aside>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script>
const catalog = __CATALOG_JSON__;
const atlas = document.querySelector("#atlas");
const categoryLinks = document.querySelector("#category-links");
const search = document.querySelector("#search");
const cards = [];
let activeFilter = "all";

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function buildAtlas() {
  for (const category of catalog.categories) {
    const link = makeElement("a", "category-link");
    link.href = `#category-${category.slug}`;
    link.append(makeElement("span", "", category.noun), makeElement("span", "", String(category.variants.length).padStart(2, "0")));
    categoryLinks.append(link);

    const section = makeElement("section", "shelf");
    section.id = `category-${category.slug}`;
    section.dataset.category = category.slug;
    const header = makeElement("header", "shelf-header");
    const titleGroup = makeElement("div");
    titleGroup.append(makeElement("h2", "shelf-title", category.noun), makeElement("p", "section-code", category.asset));
    const reachable = category.variants.filter((variant) => variant.reachable).length;
    header.append(titleGroup, makeElement("p", "shelf-count", `${reachable}/${category.variants.length} raw reachable`));
    section.append(header);

    const grid = makeElement("div", "variant-grid");
    for (const variant of category.variants) {
      const card = makeElement("label", "variant-card");
      const key = `${category.asset}/base${variant.base_id}`;
      card.dataset.key = key;
      card.dataset.noun = category.noun;
      card.dataset.asset = category.asset;
      card.dataset.baseId = String(variant.base_id);
      card.dataset.reachable = String(variant.reachable);
      card.dataset.current = String(variant.current);
      card.dataset.search = [category.noun, category.asset, `base${variant.base_id}`, ...variant.raw_tasks].join(" ").toLowerCase();
      if (variant.current) card.classList.add("is-current");
      if (!variant.reachable) {
        card.classList.add("is-unreachable");
        card.title = "This exact ID is not selectable by native/raw task Python at commit 8187d5b.";
      }

      const checkbox = makeElement("input", "variant-check");
      checkbox.type = "checkbox";
      checkbox.value = key;
      checkbox.disabled = !variant.reachable;
      checkbox.setAttribute("aria-label", `Select ${category.noun} ${key}`);
      checkbox.addEventListener("change", () => {
        card.classList.toggle("is-selected", checkbox.checked);
        persistSelection();
        renderSelection();
        if (activeFilter === "selected") applyFilters();
      });

      const stage = makeElement("span", "variant-stage");
      const image = makeElement("img", "variant-image");
      image.src = variant.image;
      image.alt = `${category.noun}, ${category.asset} base${variant.base_id}`;
      image.loading = "lazy";
      image.decoding = "async";
      stage.append(image);

      const body = makeElement("span", "card-body");
      const head = makeElement("span", "card-head");
      head.append(makeElement("strong", "base-id", `base${variant.base_id}`));
      if (variant.current) head.append(makeElement("span", "badge badge-current", "current"));
      const reach = makeElement("span", "reachability", variant.reachable ? "Raw-task reachable" : "Not exact-ID reachable");
      const tasks = makeElement("span", "card-tasks", variant.raw_tasks.length ? variant.raw_tasks.join(" · ") : "No native/raw task can select this exact ID");
      tasks.title = variant.raw_tasks.join(", ");
      body.append(head, reach, tasks);
      card.append(checkbox, stage, body);
      grid.append(card);
      cards.push({ card, checkbox, category, variant, key });
    }
    section.append(grid);
    atlas.append(section);
  }
}

function applyFilters() {
  const query = search.value.trim().toLowerCase();
  let visible = 0;
  for (const item of cards) {
    const statusMatch = activeFilter === "all"
      || (activeFilter === "reachable" && item.variant.reachable)
      || (activeFilter === "unreachable" && !item.variant.reachable)
      || (activeFilter === "current" && item.variant.current)
      || (activeFilter === "selected" && item.checkbox.checked);
    const queryMatch = !query || item.card.dataset.search.includes(query);
    item.card.hidden = !(statusMatch && queryMatch);
    if (!item.card.hidden) visible += 1;
  }
  for (const section of atlas.querySelectorAll(".shelf")) {
    section.hidden = !Array.from(section.querySelectorAll(".variant-card")).some((card) => !card.hidden);
  }
  document.querySelector("#visible-count").textContent = `${visible} / ${cards.length} visible`;
}

function selectedItems() {
  return cards.filter((item) => item.checkbox.checked);
}

function persistSelection() {
  try {
    localStorage.setItem("robotwin-object-atlas-selection", JSON.stringify(selectedItems().map((item) => item.key)));
  } catch (_) {}
}

function restoreSelection() {
  let stored = [];
  try { stored = JSON.parse(localStorage.getItem("robotwin-object-atlas-selection") || "[]"); } catch (_) {}
  const keys = new Set(Array.isArray(stored) ? stored : []);
  for (const item of cards) {
    item.checkbox.checked = item.variant.reachable && keys.has(item.key);
    item.card.classList.toggle("is-selected", item.checkbox.checked);
  }
}

function renderSelection() {
  const selected = selectedItems();
  const list = document.querySelector("#selection-list");
  const count = document.querySelector("#selection-count");
  const copy = document.querySelector("#copy-selection");
  count.textContent = String(selected.length);
  copy.disabled = selected.length === 0;
  list.replaceChildren();
  if (!selected.length) {
    list.append(makeElement("p", "selection-empty", "No variants selected."));
    return;
  }
  for (const item of selected) {
    const row = makeElement("div", "selection-row");
    row.append(makeElement("strong", "", item.category.noun), makeElement("span", "selection-key", `base${item.variant.base_id}`));
    const remove = makeElement("button", "remove-button", "×");
    remove.type = "button";
    remove.title = `Remove ${item.category.noun} base${item.variant.base_id}`;
    remove.setAttribute("aria-label", remove.title);
    remove.addEventListener("click", () => {
      item.checkbox.checked = false;
      item.card.classList.remove("is-selected");
      persistSelection();
      renderSelection();
      if (activeFilter === "selected") applyFilters();
    });
    row.append(remove);
    list.append(row);
  }
}

function selectionText() {
  const grouped = new Map();
  for (const category of catalog.categories) grouped.set(category.asset, []);
  for (const item of selectedItems()) grouped.get(item.category.asset).push(item.variant.base_id);
  return catalog.categories
    .filter((category) => grouped.get(category.asset).length)
    .map((category) => `${category.noun} (${category.asset}): ${grouped.get(category.asset).sort((a, b) => a - b).join(", ")}`)
    .join("\n");
}

let toastTimer = 0;
function showToast(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2200);
}

async function copySelection() {
  const text = selectionText();
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    const textarea = makeElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  showToast("Selected exact IDs copied.");
}

function loadCurrent() {
  for (const item of cards) {
    item.checkbox.checked = item.variant.current;
    item.card.classList.toggle("is-selected", item.checkbox.checked);
  }
  persistSelection();
  renderSelection();
  if (activeFilter === "selected") applyFilters();
  showToast(`Loaded ${cards.filter((item) => item.variant.current).length} current production variants.`);
}

function clearSelection() {
  for (const item of cards) {
    item.checkbox.checked = false;
    item.card.classList.remove("is-selected");
  }
  persistSelection();
  renderSelection();
  if (activeFilter === "selected") applyFilters();
}

function setTheme(theme) {
  if (theme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.dataset.theme = theme;
  document.querySelector("#theme-button").textContent = `Theme: ${theme}`;
  try { localStorage.setItem("robotwin-object-atlas-theme", theme); } catch (_) {}
}

function initTheme() {
  let theme = "system";
  try { theme = localStorage.getItem("robotwin-object-atlas-theme") || "system"; } catch (_) {}
  if (!["system", "light", "dark"].includes(theme)) theme = "system";
  setTheme(theme);
}

buildAtlas();
document.querySelector("#metric-categories").textContent = String(catalog.categories.length);
document.querySelector("#metric-variants").textContent = String(cards.length);
document.querySelector("#metric-reachable").textContent = String(cards.filter((item) => item.variant.reachable).length);
document.querySelector("#metric-current").textContent = String(cards.filter((item) => item.variant.current).length);
restoreSelection();
renderSelection();
applyFilters();
initTheme();

search.addEventListener("input", applyFilters);
document.querySelector("#filters").addEventListener("click", (event) => {
  const button = event.target.closest("[data-filter]");
  if (!button) return;
  activeFilter = button.dataset.filter;
  for (const filter of document.querySelectorAll(".filter")) filter.setAttribute("aria-pressed", String(filter === button));
  applyFilters();
});
document.querySelector("#load-current").addEventListener("click", loadCurrent);
document.querySelector("#clear-selection").addEventListener("click", clearSelection);
document.querySelector("#copy-selection").addEventListener("click", copySelection);
document.querySelector("#theme-button").addEventListener("click", () => {
  const current = document.documentElement.dataset.theme || "system";
  setTheme(current === "system" ? "light" : current === "light" ? "dark" : "system");
});
</script>
</body>
</html>
'''


def render_seen_object_atlas(ctx):
    pool_assets = {entry["asset"] for entry in SEEN_POOL.values()}
    if pool_assets != set(SEEN_RAW_REACHABLE_IDS):
        missing = sorted(pool_assets - set(SEEN_RAW_REACHABLE_IDS))
        stale = sorted(set(SEEN_RAW_REACHABLE_IDS) - pool_assets)
        raise RuntimeError(
            "Seen raw-ID reachability is out of sync with SEEN_POOL: "
            f"missing={missing}, stale={stale}"
        )

    derived_selected_tasks = {}
    for entry in SEEN_POOL.values():
        obj = entry["asset"]
        for base_id in entry["model_ids"]:
            derived_selected_tasks[(obj, int(base_id))] = raw_tasks_for_seen_variant(
                obj, int(base_id)
            )
    if derived_selected_tasks != SEEN_RAW_TASKS_BY_VARIANT:
        raise RuntimeError(
            "Selected-variant raw-task provenance disagrees with the atlas rules"
        )

    review_out = os.path.join(REPO, "notes", "object-review")
    assets_out = os.path.join(review_out, "robotwin-object-atlas-assets")
    os.makedirs(assets_out, exist_ok=True)
    catalog = {
        "source_commit": "8187d5b",
        "categories": [],
    }
    index_rows = []
    total = 0
    for noun, entry in SEEN_POOL.items():
        obj = entry["asset"]
        slug = noun.replace(" ", "-")
        current_ids = {int(base_id) for base_id in entry["model_ids"]}
        ids = available_variant_ids(obj)
        if not ids:
            raise RuntimeError(f"no renderable variants found for {obj}")
        if not current_ids.issubset(ids):
            raise RuntimeError(
                f"current SEEN_POOL IDs lack renderable assets for {obj}: "
                f"{sorted(current_ids - set(ids))}"
            )

        category_out = os.path.join(assets_out, slug)
        os.makedirs(category_out, exist_ok=True)
        variants = []
        for base_id in ids:
            tasks = raw_tasks_for_seen_variant(obj, base_id)
            reachable = base_id in SEEN_RAW_REACHABLE_IDS[obj]
            if reachable != bool(tasks):
                raise RuntimeError(
                    f"raw-task names disagree with reachability for {obj}/base{base_id}"
                )
            current = base_id in current_ids
            filename = f"snap_{obj}_b{base_id}.png"
            image = render_variant(ctx, obj, base_id)
            image.save(os.path.join(category_out, filename), optimize=True)
            variants.append({
                "base_id": base_id,
                "reachable": reachable,
                "current": current,
                "raw_tasks": tasks,
                "image": f"robotwin-object-atlas-assets/{slug}/{filename}",
            })
            index_rows.append((noun, obj, base_id, reachable, current, tasks))
            total += 1
            print(
                f"  {noun:16s} {obj}/base{base_id:<2d} "
                f"raw={'yes' if reachable else 'no ':3s} "
                f"current={'yes' if current else 'no'}",
                flush=True,
            )
        catalog["categories"].append({
            "noun": noun,
            "asset": obj,
            "slug": slug,
            "variants": variants,
        })

    os.makedirs(review_out, exist_ok=True)
    atlas_path = os.path.join(review_out, "robotwin-object-atlas.html")
    catalog_json = json.dumps(catalog, ensure_ascii=False, indent=2)
    with open(atlas_path, "w", encoding="utf-8") as handle:
        handle.write(OBJECT_ATLAS_HTML.replace("__CATALOG_JSON__", catalog_json))

    index_path = os.path.join(assets_out, "selection_index.tsv")
    with open(index_path, "w", encoding="utf-8") as handle:
        handle.write(
            "noun\tasset\tbase_id\traw_task_reachable\t"
            "current_production\traw_tasks\n"
        )
        for noun, obj, base_id, reachable, current, tasks in index_rows:
            handle.write(
                f"{noun}\t{obj}\t{base_id}\t"
                f"{'yes' if reachable else 'no'}\t{'yes' if current else 'no'}\t"
                f"{','.join(tasks)}\n"
            )
    print(f"rendered {total} variants across {len(SEEN_POOL)} categories")
    print(f"object atlas -> {atlas_path}")
    print(f"selection index -> {index_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--group",
        choices=(*GROUPS, "all", "seen-object-atlas"),
        default="unseen-candidates",
    )
    ap.add_argument("--columns", type=int, default=6)
    ap.add_argument(
        "--annotate-raw-tasks",
        action="store_true",
        help="label Seen variants with exact-ID-reachable raw task names",
    )
    args = ap.parse_args()

    if args.group == "seen-object-atlas":
        if args.annotate_raw_tasks:
            ap.error(
                "--annotate-raw-tasks is unnecessary for "
                "--group seen-object-atlas"
            )
        engine = sapien.Engine()
        renderer = sapien.SapienRenderer()
        engine.set_renderer(renderer)
        render_seen_object_atlas((engine, renderer))
        return

    rows = list(selected_variants(args.group))
    if args.annotate_raw_tasks:
        if args.group != "seen":
            ap.error("--annotate-raw-tasks requires --group seen")
        rendered_keys = {(obj, int(base_id)) for _, _, obj, base_id, _ in rows}
        provenance_keys = set(SEEN_RAW_TASKS_BY_VARIANT)
        if rendered_keys != provenance_keys:
            missing = sorted(rendered_keys - provenance_keys)
            stale = sorted(provenance_keys - rendered_keys)
            raise RuntimeError(
                "Seen raw-task provenance is out of sync with SEEN_POOL: "
                f"missing={missing}, stale={stale}"
            )

    group_out = os.path.join(OUT, args.group)
    os.makedirs(group_out, exist_ok=True)
    engine = sapien.Engine()
    renderer = sapien.SapienRenderer()
    engine.set_renderer(renderer)
    ctx = (engine, renderer)

    imgs = []
    for familiarity, noun, obj, base_id, _entry in rows:
        image = render_variant(ctx, obj, base_id)
        filename = f"snap_{obj}_b{base_id}.png"
        image.save(os.path.join(group_out, filename))
        imgs.append((familiarity, noun, obj, base_id, image))
        print(f"  {familiarity:17s} {noun:16s} {obj}/base{base_id}", flush=True)

    ncol = args.columns
    nrow = (len(imgs) + ncol - 1) // ncol
    cell_height = 3.7 if args.annotate_raw_tasks else 2.75
    fig = plt.figure(figsize=(ncol * 2.75, nrow * cell_height), dpi=130)
    for i, (familiarity, noun, obj, base_id, image) in enumerate(imgs):
        ax = fig.add_subplot(nrow, ncol, i + 1)
        ax.imshow(np.asarray(image))
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f"{noun}\n{obj} b{base_id}", fontsize=8.5,
                     color=("#165D9C" if familiarity == "seen" else "#7C3A8C"))
        if args.annotate_raw_tasks:
            tasks = SEEN_RAW_TASKS_BY_VARIANT[(obj, int(base_id))]
            task_label = fill(
                ", ".join(tasks),
                width=38,
                break_long_words=False,
                break_on_hyphens=False,
            )
            ax.set_xlabel(
                f"raw tasks @ 8187d5b:\n{task_label}",
                fontsize=6.2,
                color="#333333",
                labelpad=6,
                linespacing=1.2,
            )
    nouns = len({(familiarity, noun) for familiarity, noun, *_rest in imgs})
    title = (
        f"Pick-Diverse-Object {args.group} — {nouns} nouns / "
        f"{len(imgs)} exact variants"
    )
    if args.annotate_raw_tasks:
        title += "\nExact-ID-reachable native/raw task Python"
    fig.suptitle(title, fontsize=12, y=0.99)
    fig.subplots_adjust(
        left=0.01,
        right=0.99,
        top=0.90 if not args.annotate_raw_tasks else 0.91,
        bottom=0.01 if not args.annotate_raw_tasks else 0.075,
        hspace=0.34 if not args.annotate_raw_tasks else 0.95,
        wspace=0.03,
    )
    suffix = f"{args.group}_raw_tasks" if args.annotate_raw_tasks else args.group
    sheet = os.path.join(OUT, f"snapshots_{suffix}.png")
    fig.savefig(sheet, facecolor="white")
    plt.close(fig)
    print(f"\ncontact sheet -> {sheet}")


if __name__ == "__main__":
    main()
