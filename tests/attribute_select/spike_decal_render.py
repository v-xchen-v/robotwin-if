"""
IF-Attribute-Select feasibility spike (stage ② oracle/render check).

Goal: verify the ONE genuinely-uncertain mechanism of the §3 design — whether
`create_box(texture_id=...)` maps a decal image as ONE clean image per cube face
(usable) vs TILED/stretched (needs UV work). color/shape/size primitives are
proven by grasp_cube_approach / arm_select, so we just eyeball them here too.

Run (from repo root):
  conda run -n RoboTwin python tests/attribute_select/spike_decal_render.py

Renders are written to notes/2026-09-01-attribute-select/evidence/.
Test decal PNGs are dropped into the submodule's background_texture dir with an
`_ifspike_` prefix and deleted on exit.
"""
import os
import sys
import numpy as np
from PIL import Image, ImageDraw

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RW = os.path.join(REPO, "third_party", "robotwin")
TEX_DIR = os.path.join(RW, "assets", "background_texture")
OUT = os.path.join(REPO, "notes", "2026-09-01-attribute-select", "evidence")
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, RW)
os.chdir(RW)  # texture path is resolved as ./assets/background_texture/{id}.png

import sapien.core as sapien
from envs.utils.create_actor import create_entity_box, create_sphere, create_cylinder


def make_decal(path, kind):
    """Bold, asymmetric pattern: mapped-once -> one big shape per face;
    tiled -> a grid of small shapes. Corner marker reveals rotation/flip."""
    img = Image.new("RGB", (512, 512), "white")
    d = ImageDraw.Draw(img)
    if kind == "A":
        d.ellipse([90, 90, 422, 422], outline="black", width=28)  # one big ring
        d.rectangle([10, 10, 110, 110], fill="red")               # TL corner marker
    else:
        d.line([100, 100, 412, 412], fill="black", width=32)      # big X
        d.line([412, 100, 100, 412], fill="black", width=32)
        d.rectangle([10, 10, 110, 110], fill="green")             # TL corner marker
    img.save(path)


def setup_scene():
    engine = sapien.Engine()
    renderer = sapien.SapienRenderer()
    engine.set_renderer(renderer)
    scene = engine.create_scene(sapien.SceneConfig())
    scene.set_timestep(1 / 250)
    scene.add_ground(0)
    scene.default_physical_material = scene.create_physical_material(0.5, 0.5, 0.0)
    scene.set_ambient_light([0.5, 0.5, 0.5])
    scene.add_directional_light([0, 0.5, -1], [0.7, 0.7, 0.7], shadow=True)
    scene.add_point_light([1, 0, 1.8], [1, 1, 1])
    scene.add_point_light([-1, 0, 1.8], [1, 1, 1])
    return scene


def add_cam(scene):
    cam = scene.add_camera(name="spike", width=960, height=540,
                           fovy=np.deg2rad(45), near=0.05, far=20)
    pos = np.array([0.0, -0.55, 0.55])          # in front, above, looking at row
    fwd = np.array([0.0, 1.0, -0.9]); fwd = fwd / np.linalg.norm(fwd)
    left = np.array([-1.0, 0.0, 0.0])
    up = np.cross(fwd, left)
    m = np.eye(4); m[:3, :3] = np.stack([fwd, left, up], axis=1); m[:3, 3] = pos
    cam.entity.set_pose(sapien.Pose(m))
    return cam


def shoot(scene, cam, name):
    scene.step(); scene.update_render(); cam.take_picture()
    rgba = cam.get_picture("Color")            # (H,W,4) float [0,1]
    arr = (np.clip(rgba[..., :3], 0, 1) * 255).astype(np.uint8)
    p = os.path.join(OUT, name)
    Image.fromarray(arr).save(p)
    print("wrote", p)


def box(scene, x, half, color=None, texture_id=None):
    h = half if isinstance(half, (list, tuple)) else (half, half, half)
    return create_entity_box(scene, sapien.Pose([x, 0, h[2]]), half_size=h,
                             color=color, texture_id=texture_id, name=f"b{x}")


def main():
    make_decal(os.path.join(TEX_DIR, "_ifspike_A.png"), "A")
    make_decal(os.path.join(TEX_DIR, "_ifspike_B.png"), "B")
    scene = setup_scene()
    cam = add_cam(scene)

    # Scene 1 — DECAL mode (the real unknown) + a color control
    box(scene, -0.22, 0.045, texture_id="_ifspike_A")   # ring decal
    box(scene, -0.07, 0.045, texture_id="_ifspike_B")   # X decal
    box(scene, 0.08, 0.045, color=[0.85, 0.1, 0.1])     # plain red (color mode)
    box(scene, 0.23, 0.045, color=[0.1, 0.3, 0.9])      # plain blue (color mode)
    shoot(scene, cam, "spike_decal_color.png")

    # Scene 2 — SHAPE + SIZE primitives (proven, sanity only)
    scene2 = setup_scene(); cam2 = add_cam(scene2)
    box(scene2, -0.22, 0.045, color=[0.2, 0.7, 0.2])                    # cube
    create_sphere(scene2, sapien.Pose([-0.07, 0, 0.045]), 0.045, color=[0.2, 0.7, 0.2], name="sph")
    create_cylinder(scene2, sapien.Pose([0.08, 0, 0.05]), 0.04, 0.05, color=[0.2, 0.7, 0.2], name="cyl")
    box(scene2, 0.25, (0.07, 0.07, 0.07), color=[0.7, 0.5, 0.1])       # big
    box(scene2, 0.40, (0.03, 0.03, 0.03), color=[0.7, 0.5, 0.1])       # small
    shoot(scene2, cam2, "spike_shape_size.png")


if __name__ == "__main__":
    try:
        main()
    finally:
        for f in ("_ifspike_A.png", "_ifspike_B.png"):
            p = os.path.join(TEX_DIR, f)
            if os.path.exists(p):
                os.remove(p)
        print("cleaned up test decals")
