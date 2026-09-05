#!/usr/bin/env python3
"""Legacy color audit for the original 12-item Seen pool (16 variants).

The current object-familiarity extension uses noun-only instructions and reads its
production pools from ``_pick_diverse_object_pool.py``. This tool remains as
reproducible evidence for the paper-faithful color+noun baseline only.

Headless software render (trimesh + matplotlib, no GL). For each historical
(noun, obj, base_id, claimed_color) variant it: renders a shaded thumbnail,
samples the dominant baseColor from the glb texture, auto-classifies that to a
named color, and flags rows where the auto guess disagrees with the claimed
color. The thumbnail (human eye) is the arbiter; the auto guess is only a flag
to focus review. Output: one contact sheet + per-variant PNGs + a printed table.

    python tools/render_pick_pool_thumbs.py

Historical table source: docs/features/04-Pick-Diverse-Object.md. Do not use this
legacy list as the current production pool.
"""
import json
import os

import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ASSETS = os.path.join(_REPO, "third_party", "robotwin", "assets", "objects")
_OUT = os.path.join(_REPO, "notes", "2026-08-21-pick-diverse-object", "evidence", "pool")

# (noun, obj, base_id, claimed_color) — the locked 12-item / 16-variant pool.
# Targets (multi-color, must ground on color+noun): bottle, cup, shoe.
# Distractor fillers (single color): the rest.
POOL = [
    ("bottle", "001_bottle", 0, "red"),
    ("bottle", "001_bottle", 22, "green"),
    ("bottle", "001_bottle", 5, "orange"),
    ("cup", "021_cup", 0, "blue"),
    ("cup", "021_cup", 3, "green"),
    ("shoe", "041_shoe", 8, "red"),
    ("shoe", "041_shoe", 4, "green"),
    ("mug", "039_mug", 0, "black"),
    ("can", "071_can", 3, "red"),
    ("toycar", "057_toycar", 3, "green"),
    ("phone", "077_phone", 4, "black"),
    ("soap", "107_soap", 2, "blue"),
    ("hamburg", "006_hamburg", 4, "yellow"),
    ("bread", "075_bread", 4, "golden"),
    ("coffee-box", "113_coffee-box", 0, "brown"),
    ("mouse", "047_mouse", 0, "gray"),
]

# Reference sRGB anchors for the named colors used in the pool.
_NAMED = {
    "red": (0.72, 0.11, 0.11), "green": (0.20, 0.55, 0.22), "blue": (0.16, 0.32, 0.72),
    "yellow": (0.92, 0.86, 0.18), "orange": (0.90, 0.49, 0.13), "black": (0.09, 0.09, 0.10),
    "white": (0.93, 0.93, 0.92), "brown": (0.45, 0.29, 0.16), "golden": (0.83, 0.66, 0.22),
    "pink": (0.90, 0.55, 0.66), "gray": (0.55, 0.55, 0.56), "purple": (0.50, 0.28, 0.60),
    "silver": (0.75, 0.76, 0.78),
}


def _srgb_to_lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def classify(rgb):
    """Nearest named color by linear-RGB distance (perceptual-ish sanity flag)."""
    lin = _srgb_to_lin(rgb)
    best, bd = None, 1e9
    for name, ref in _NAMED.items():
        d = float(np.sum((lin - _srgb_to_lin(ref)) ** 2))
        if d < bd:
            best, bd = name, d
    return best


def dominant_color(scene):
    """Median baseColor across all geometries' textures (alpha>0.5), else factor."""
    px = []
    factors = []
    for g in scene.geometry.values():
        try:
            mat = g.visual.material
        except Exception:
            continue
        bcf = getattr(mat, "baseColorFactor", None)
        if bcf is not None:
            factors.append(np.array(bcf[:3], float) / (255.0 if max(bcf[:3]) > 1 else 1.0))
        img = getattr(mat, "baseColorTexture", None) or getattr(mat, "image", None)
        if img is not None:
            arr = np.asarray(img.convert("RGBA")).reshape(-1, 4) / 255.0
            keep = arr[arr[:, 3] > 0.5][:, :3]
            if len(keep):
                # drop the extremes (specular highlights / deep shadow) before median
                lum = keep @ np.array([0.299, 0.587, 0.114])
                m = (lum > np.percentile(lum, 5)) & (lum < np.percentile(lum, 95))
                px.append(keep[m] if m.any() else keep)
    if px:
        return np.median(np.concatenate(px, 0), axis=0)
    if factors:
        return np.mean(factors, 0)
    return np.array([0.62, 0.62, 0.64])


def texture_atlas(scene, size=220):
    """Return an RGB image tiling the actual baseColor textures of the variant.

    Shows the real texture pixels (per material) — the honest color reference,
    unlike a single median tint that washes multi-material objects out. Textures
    are ordered largest-first and tiled left-to-right; a flat factor-only material
    becomes a solid swatch tile.
    """
    from PIL import Image
    tiles = []
    for g in scene.geometry.values():
        try:
            mat = g.visual.material
        except Exception:
            continue
        img = getattr(mat, "baseColorTexture", None) or getattr(mat, "image", None)
        if img is not None:
            im = img.convert("RGB")
            tiles.append((im.size[0] * im.size[1], im))
        else:
            bcf = getattr(mat, "baseColorFactor", None)
            if bcf is not None:
                rgb = tuple(int(255 * (c / (255 if max(bcf[:3]) > 1 else 1))) for c in bcf[:3])
                tiles.append((size * size, Image.new("RGB", (size, size), rgb)))
    if not tiles:
        return Image.new("RGB", (size, size), (158, 158, 163))
    tiles.sort(key=lambda t: -t[0])
    ims = [t[1].resize((size, size)) for t in tiles[:3]]  # up to 3 materials
    W = size * len(ims)
    atlas = Image.new("RGB", (W, size), (255, 255, 255))
    for j, im in enumerate(ims):
        atlas.paste(im, (j * size, 0))
    return atlas


def render_cell(ax, obj, base_id, scene):
    ax.imshow(np.asarray(texture_atlas(scene)))
    ax.set_xticks([]); ax.set_yticks([])


def main():
    os.makedirs(_OUT, exist_ok=True)
    ncol = 3
    nrow = (len(POOL) + ncol - 1) // ncol
    fig = plt.figure(figsize=(ncol * 3.0, nrow * 3.1), dpi=130)
    rows = []
    for i, (noun, obj, base_id, claimed) in enumerate(POOL):
        scene = trimesh.load(os.path.join(_ASSETS, obj, "visual", f"base{base_id}.glb"), force="scene")
        dom = dominant_color(scene)
        auto = classify(dom)
        ok = (auto == claimed)
        rows.append((noun, obj, base_id, claimed, auto, dom, ok))

        ax = fig.add_subplot(nrow, ncol, i + 1)
        render_cell(ax, obj, base_id, scene)
        hexc = "#%02x%02x%02x" % tuple(int(255 * x) for x in np.clip(dom, 0, 1))
        flag = "" if ok else "  !"
        ax.set_title(f"{noun}/{claimed}{flag}\n{obj} b{base_id}  median:{hexc} auto:{auto}",
                     fontsize=8, color=("#111" if ok else "#c00"))

    fig.subplots_adjust(left=0.01, right=0.99, top=0.95, bottom=0.01, hspace=0.35, wspace=0.02)
    sheet = os.path.join(_OUT, "contact_sheet.png")
    fig.savefig(sheet, facecolor="white"); plt.close(fig)

    # printed table + machine-readable dump
    print(f"{'noun':13s} {'variant':22s} {'claimed':8s} {'auto':8s} {'hex':8s} flag")
    dump = []
    for noun, obj, base_id, claimed, auto, dom, ok in rows:
        hexc = "#%02x%02x%02x" % tuple(int(255 * x) for x in np.clip(dom, 0, 1))
        print(f"{noun:13s} {obj+'/base'+str(base_id):22s} {claimed:8s} {auto:8s} {hexc:8s} {'ok' if ok else 'CHECK'}")
        dump.append({"noun": noun, "obj": obj, "base_id": base_id, "claimed": claimed,
                     "auto": auto, "hex": hexc, "match": ok})
    json.dump(dump, open(os.path.join(_OUT, "color_audit.json"), "w"), indent=2)
    n_check = sum(1 for r in rows if not r[6])
    print(f"\ncontact sheet -> {sheet}")
    print(f"audit json    -> {os.path.join(_OUT, 'color_audit.json')}")
    print(f"{n_check}/{len(rows)} variants flagged for eyeball review (auto != claimed)")


if __name__ == "__main__":
    main()
