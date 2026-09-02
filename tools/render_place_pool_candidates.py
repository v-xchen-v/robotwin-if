"""Render real-texture SAPIEN snapshots of the Place-Relative on-top candidates.

Offscreen Vulkan render (run inside the RoboTwin conda env):

    conda run -n RoboTwin python tools/render_place_pool_candidates.py

For each candidate object it renders EVERY base{K}.glb variant (so we can pick the
cleanest single-color one by eye, per the "verify colors by texture" rule — native
objects_description color words are noisy). Movers and bases that were already
eyeball-verified in the Pick-Diverse pool (mouse/toycar/can/soap/coffee-box) are
skipped. Reuses the framing/lighting from tools/render_pick_pool_snapshots.py.
"""
import glob
import os
import numpy as np
import trimesh
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import sapien  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(REPO, "third_party", "robotwin", "assets", "objects")
OUT = os.path.join(REPO, "notes", "2026-08-24-place-relative", "evidence", "pool")

# Candidates whose colors are NOT yet verified. role: mover (placed) / base (received on).
# All base variants of each are rendered so we can lock the cleanest color per object.
CANDIDATES = [
    ("stapler", "048_stapler", "mover"),
    ("bell", "050_bell", "mover"),
    ("rubikscube", "073_rubikscube", "mover"),
    ("remotecontrol", "079_remotecontrol", "mover"),
    ("plate", "003_plate", "base"),
    ("tea-box", "112_tea-box", "base"),
    ("displaystand", "074_displaystand", "base"),
]


def base_ids(obj):
    ids = []
    for f in glob.glob(os.path.join(ASSETS, obj, "model_data*.json")):
        b = os.path.basename(f).replace("model_data", "").replace(".json", "")
        try:
            ids.append(int(b))
        except ValueError:
            pass
    return sorted(i for i in ids if os.path.exists(os.path.join(ASSETS, obj, "visual", f"base{i}.glb")))


def frame_mat44(center, radius, fovy, azim_deg=40, elev_deg=22, margin=1.5):
    d = margin * radius / np.tan(fovy / 2)
    a, e = np.deg2rad(azim_deg), np.deg2rad(elev_deg)
    view = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    cam_pos = center + d * view
    fwd = center - cam_pos; fwd /= np.linalg.norm(fwd)
    left = np.cross([0, 0, 1.0], fwd); left /= np.linalg.norm(left)
    up = np.cross(fwd, left)
    m = np.eye(4); m[:3, :3] = np.stack([fwd, left, up], axis=1); m[:3, 3] = cam_pos
    return m


def render_variant(engine, obj, base_id, size=340):
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


def main():
    os.makedirs(OUT, exist_ok=True)
    engine = sapien.Engine()
    renderer = sapien.SapienRenderer()
    engine.set_renderer(renderer)

    tiles = []
    for noun, obj, role in CANDIDATES:
        for bid in base_ids(obj):
            im = render_variant(engine, obj, bid)
            im.save(os.path.join(OUT, f"cand_{noun}_{obj}_b{bid}.png"))
            tiles.append((noun, role, obj, bid, im))
            print(f"  {noun:14s} {obj}/base{bid}  ({role})")

    ncol = 6
    nrow = (len(tiles) + ncol - 1) // ncol
    fig = plt.figure(figsize=(ncol * 2.6, nrow * 2.8), dpi=130)
    for i, (noun, role, obj, bid, im) in enumerate(tiles):
        ax = fig.add_subplot(nrow, ncol, i + 1)
        ax.imshow(np.asarray(im)); ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"{noun} b{bid}\n({role})", fontsize=8,
                     color=("#06c" if role == "base" else "#333"))
    fig.suptitle("Place-Relative on-top candidates — every base variant (blue=base/receiver)", fontsize=11)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.95, bottom=0.01, hspace=0.34, wspace=0.03)
    sheet = os.path.join(OUT, "candidates.png")
    fig.savefig(sheet, facecolor="white"); plt.close(fig)
    print(f"\ncontact sheet -> {sheet}")


if __name__ == "__main__":
    main()
