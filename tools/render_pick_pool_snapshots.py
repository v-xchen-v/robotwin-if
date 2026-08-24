"""Render real-texture SAPIEN snapshots of the Pick-Diverse-Object 12-item pool.

Offscreen Vulkan render (run inside the RoboTwin conda env — it has sapien):

    conda run -n RoboTwin python tools/render_pick_pool_snapshots.py

For each locked (noun, obj, base_id, color) variant it builds a kinematic actor
from assets/objects/{obj}/visual/base{K}.glb, frames it with an auto-fit camera,
renders RGB, composites on white, and tiles all variants (grouped by object) into
one contact sheet + saves per-variant PNGs. Objects keep their as-authored glb
orientation. Pool mirrors tools/render_pick_pool_thumbs.py / docs/features/04.
"""
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
OUT = os.path.join(REPO, "notes", "2026-08-21-pick-diverse-object", "evidence", "pool")

# (noun, obj, base_id, color) — grouped by object; targets first then fillers.
POOL = [
    ("bottle", "001_bottle", 0, "red"), ("bottle", "001_bottle", 22, "green"),
    ("bottle", "001_bottle", 5, "orange"),
    ("cup", "021_cup", 0, "blue"), ("cup", "021_cup", 3, "green"),
    ("shoe", "041_shoe", 8, "red"), ("shoe", "041_shoe", 4, "green"),
    ("mug", "039_mug", 0, "black"), ("can", "071_can", 3, "red"),
    ("toycar", "057_toycar", 3, "green"), ("phone", "077_phone", 4, "black"),
    ("soap", "107_soap", 2, "blue"), ("hamburg", "006_hamburg", 4, "yellow"),
    ("bread", "075_bread", 4, "golden"), ("coffee-box", "113_coffee-box", 0, "brown"),
    ("mouse", "047_mouse", 0, "gray"),
]


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


def render_variant(scene_ctx, obj, base_id, size=340):
    engine, renderer = scene_ctx
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
    ctx = (engine, renderer)

    imgs = []
    for noun, obj, base_id, color in POOL:
        im = render_variant(ctx, obj, base_id)
        im.save(os.path.join(OUT, f"snap_{noun}_{color}_{obj}_b{base_id}.png"))
        imgs.append((noun, color, obj, base_id, im))
        print(f"  {noun}/{color}  {obj}/base{base_id}")

    ncol = 5
    nrow = (len(imgs) + ncol - 1) // ncol
    fig = plt.figure(figsize=(ncol * 2.6, nrow * 2.8), dpi=130)
    for i, (noun, color, obj, base_id, im) in enumerate(imgs):
        ax = fig.add_subplot(nrow, ncol, i + 1)
        ax.imshow(np.asarray(im)); ax.set_xticks([]); ax.set_yticks([])
        tgt = noun in ("bottle", "cup", "shoe")
        ax.set_title(f"{'[T] ' if tgt else ''}{noun} / {color}\n{obj} b{base_id}",
                     fontsize=9, color=("#0a5" if tgt else "#333"))
    n_nouns = len({p[0] for p in POOL})
    fig.suptitle(f"Pick-Diverse-Object pool — {n_nouns} objects / {len(POOL)} variants  ([T]=target noun)", fontsize=11)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.94, bottom=0.01, hspace=0.32, wspace=0.03)
    sheet = os.path.join(OUT, "snapshots.png")
    fig.savefig(sheet, facecolor="white"); plt.close(fig)
    print(f"\ncontact sheet -> {sheet}")


if __name__ == "__main__":
    main()
