#!/usr/bin/env python3
"""Render simple software (no-GL) thumbnails of the operate_stapler distractor pool.

Headless-friendly: uses trimesh + matplotlib (no OpenGL / no display), so it runs on a
box without a GPU display. Output is a shaded shape thumbnail per object (materials are
approximated by a single tint sampled from the glb, so treat these as shape references,
not photoreal renders).

    python tools/render_distractor_thumbs.py           # -> notes/.../evidence/distractors/*.png

Regenerate after changing the pool. Same list as operate_stapler.DISTRACTOR_NAMES.
"""
import json
import os
import re
import sys

import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ASSETS = os.path.join(_REPO, "third_party", "robotwin", "assets", "objects")
_OUT = os.path.join(_REPO, "notes", "2026-08-20-operate-stapler", "evidence", "distractors")

POOL = [
    "077_phone", "078_phonestand", "079_remotecontrol", "059_pencup",
    "093_brush-pen", "092_notebook", "095_glue", "081_playingcards",
    "100_seal", "024_scanner", "047_mouse", "021_cup",
]


def first_stable_id(name):
    d = os.path.join(_ASSETS, name)
    ids = []
    for f in os.listdir(d):
        m = re.match(r"model_data(\d+)\.json$", f)
        if not m:
            continue
        n = int(m.group(1))
        try:
            cfg = json.load(open(os.path.join(d, f)))
        except Exception:
            continue
        if cfg.get("stable", False) and os.path.exists(os.path.join(d, "visual", f"base{n}.glb")):
            ids.append(n)
    return min(ids) if ids else None


def tint_from(mesh):
    # Approximate a single color: PBR baseColorFactor, else average of baseColorTexture.
    try:
        mat = mesh.visual.material
        bcf = getattr(mat, "baseColorFactor", None)
        if bcf is not None:
            return np.array(bcf[:3], dtype=float)
        img = getattr(mat, "baseColorTexture", None) or getattr(mat, "image", None)
        if img is not None:
            arr = np.asarray(img.convert("RGB")).reshape(-1, 3) / 255.0
            return arr.mean(0)
    except Exception:
        pass
    return np.array([0.62, 0.62, 0.64])


def render(name, out):
    nid = first_stable_id(name)
    if nid is None:
        print(f"  skip {name}: no stable id")
        return False
    scene = trimesh.load(os.path.join(_ASSETS, name, "visual", f"base{nid}.glb"), force="scene")
    tints, geoms = [], []
    for g in scene.geometry.values():
        tints.append(tint_from(g))
        geoms.append(g)
    mesh = trimesh.util.concatenate(geoms)
    base = np.average(tints, axis=0) if tints else np.array([0.62, 0.62, 0.64])

    v = mesh.vertices - mesh.vertices.mean(0)
    v = v / np.abs(v).max()
    tris = v[mesh.faces]
    light = np.array([0.4, 0.5, 0.85]); light /= np.linalg.norm(light)
    sh = np.clip(mesh.face_normals @ light, 0.28, 1.0)[:, None]
    col = np.clip(base * 0.9 * sh + 0.10, 0, 1)

    fig = plt.figure(figsize=(2.2, 2.2), dpi=120)
    ax = fig.add_subplot(111, projection="3d")
    ax.add_collection3d(Poly3DCollection(tris, facecolors=col, edgecolors="none"))
    ax.set_xlim(-1, 1); ax.set_ylim(-1, 1); ax.set_zlim(-1, 1)
    ax.set_box_aspect((1, 1, 1)); ax.view_init(elev=22, azim=35); ax.set_axis_off()
    fig.subplots_adjust(0, 0, 1, 1)
    fig.savefig(out, transparent=True); plt.close(fig)
    print(f"  {name}: base{nid} -> {os.path.basename(out)}")
    return True


def main():
    os.makedirs(_OUT, exist_ok=True)
    for name in POOL:
        render(name, os.path.join(_OUT, f"{name}.png"))
    print(f"done -> {_OUT}")


if __name__ == "__main__":
    main()
