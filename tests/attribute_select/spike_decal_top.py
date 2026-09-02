"""
IF-Attribute-Select — decal-on-TOP-face spike.

Two things verified here:
1. cat vs dog head icons (procedurally drawn, no web/licensing) are distinguishable
   as decals — distinct silhouettes (pointy ears vs floppy ears).
2. decal on the TOP FACE ONLY, via a single rigid actor built from:
   gray cube body  +  a thin textured plate welded on top (a "sticker").
   This is also the production recipe (one grasp-able rigid body).

Textures are referenced by ABSOLUTE path through a hand-built RenderMaterial, so
nothing is written into the submodule assets.

Run (from repo root):
  conda run -n RoboTwin python tests/attribute_select/spike_decal_top.py
Output -> notes/2026-09-01-attribute-select/evidence/spike_decal_top.png
"""
import os
import sys
import numpy as np
from PIL import Image, ImageDraw

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RW = os.path.join(REPO, "third_party", "robotwin")
OUT = os.path.join(REPO, "notes", "2026-09-01-attribute-select", "evidence")
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, RW)
os.chdir(RW)

import sapien.core as sapien


def _cat_tile(T=128):
    """One cat head filling the tile (centered). Pointy ears = cat signature."""
    img = Image.new("RGB", (T, T), (250, 241, 228)); d = ImageDraw.Draw(img)
    fur = (238, 150, 60); cx, cy = T * 0.5, T * 0.52
    # pointy ears, tips near the top edge
    d.polygon([(cx - 0.34 * T, cy - 0.06 * T), (cx - 0.46 * T, cy - 0.48 * T),
               (cx - 0.02 * T, cy - 0.24 * T)], fill=fur)
    d.polygon([(cx + 0.34 * T, cy - 0.06 * T), (cx + 0.46 * T, cy - 0.48 * T),
               (cx + 0.02 * T, cy - 0.24 * T)], fill=fur)
    d.ellipse([cx - 0.40 * T, cy - 0.28 * T, cx + 0.40 * T, cy + 0.44 * T], fill=fur)
    for sx in (-1, 1):
        d.ellipse([cx + sx * 0.18 * T - 0.07 * T, cy - 0.02 * T,
                   cx + sx * 0.18 * T + 0.07 * T, cy + 0.12 * T], fill=(30, 30, 30))
    d.polygon([(cx - 0.06 * T, cy + 0.15 * T), (cx + 0.06 * T, cy + 0.15 * T),
               (cx, cy + 0.23 * T)], fill=(170, 70, 70))
    return img


def _dog_tile(T=128):
    """One dog head filling the tile (centered). Floppy side ears = dog signature."""
    img = Image.new("RGB", (T, T), (247, 240, 230)); d = ImageDraw.Draw(img)
    fur = (150, 100, 60); ear = (105, 68, 40); cx, cy = T * 0.5, T * 0.5
    d.ellipse([cx - 0.50 * T, cy - 0.22 * T, cx - 0.14 * T, cy + 0.42 * T], fill=ear)
    d.ellipse([cx + 0.14 * T, cy - 0.22 * T, cx + 0.50 * T, cy + 0.42 * T], fill=ear)
    d.ellipse([cx - 0.36 * T, cy - 0.34 * T, cx + 0.36 * T, cy + 0.38 * T], fill=fur)
    d.ellipse([cx - 0.18 * T, cy + 0.06 * T, cx + 0.18 * T, cy + 0.38 * T], fill=(210, 180, 145))
    for sx in (-1, 1):
        d.ellipse([cx + sx * 0.15 * T - 0.06 * T, cy - 0.10 * T,
                   cx + sx * 0.15 * T + 0.06 * T, cy + 0.03 * T], fill=(30, 30, 30))
    d.ellipse([cx - 0.07 * T, cy + 0.14 * T, cx + 0.07 * T, cy + 0.25 * T], fill=(20, 20, 20))
    return img


def _tile(fn, path, n=1, S=512):
    """n=1 -> a single centered head (used with a UV-correct quad mesh)."""
    T = S // n
    canvas = Image.new("RGB", (T * n, T * n), (248, 240, 229))
    head = fn(T)
    for i in range(n):
        for j in range(n):
            canvas.paste(head, (i * T, j * T))
    canvas.save(path)


def draw_cat(path): _tile(_cat_tile, path)
def draw_dog(path): _tile(_dog_tile, path)


_QUAD_OBJ = """mtllib {mtl}
o quad
v -0.5 -0.5 0
v 0.5 -0.5 0
v 0.5 0.5 0
v -0.5 0.5 0
vt 0 0
vt 1 0
vt 1 1
vt 0 1
vn 0 0 1
usemtl decal
f 1/1/1 2/2/2 3/3/3
f 1/1/1 3/3/3 4/4/4
"""


def write_quad(dirpath, tag, png_name):
    """A unit quad in XY plane (normal +z) with explicit [0,1] UV -> the whole
    image maps once, centered. Returns the .obj path."""
    mtl = f"{tag}.mtl"
    with open(os.path.join(dirpath, mtl), "w") as f:
        f.write(f"newmtl decal\nKa 1 1 1\nKd 1 1 1\nmap_Kd {png_name}\n")
    obj = os.path.join(dirpath, f"quad_{tag}.obj")
    with open(obj, "w") as f:
        f.write(_QUAD_OBJ.format(mtl=mtl))
    return obj


def draw_cat(path): _tile(_cat_tile, path)
def draw_dog(path): _tile(_dog_tile, path)


def setup_scene():
    scene = sapien.Engine().create_scene(sapien.SceneConfig()) if False else None
    engine = sapien.Engine()
    renderer = sapien.SapienRenderer()
    engine.set_renderer(renderer)
    scene = engine.create_scene(sapien.SceneConfig())
    scene.set_timestep(1 / 250)
    scene.add_ground(0)
    scene.default_physical_material = scene.create_physical_material(0.5, 0.5, 0.0)
    scene.set_ambient_light([0.6, 0.6, 0.6])
    scene.add_directional_light([0, 0.3, -1], [0.8, 0.8, 0.8], shadow=True)
    scene.add_point_light([0.3, 0, 1.2], [1, 1, 1])
    scene.add_point_light([-0.3, 0, 1.2], [1, 1, 1])
    return scene


def add_cam(scene):
    cam = scene.add_camera(name="spike", width=960, height=560,
                           fovy=np.deg2rad(42), near=0.05, far=20)
    pos = np.array([0.0, -0.16, 0.42])       # nearly overhead, slight front tilt
    fwd = np.array([0.0, 0.35, -1.0]); fwd /= np.linalg.norm(fwd)
    left = np.array([-1.0, 0.0, 0.0])
    up = np.cross(fwd, left)
    m = np.eye(4); m[:3, :3] = np.stack([fwd, left, up], axis=1); m[:3, 3] = pos
    cam.entity.set_pose(sapien.Pose(m))
    return cam


def decal_cube(scene, x, quad_obj, body=(0.42, 0.44, 0.5), half=0.05):
    """One rigid actor: gray cube body + a UV-correct textured quad on the top
    face (single centered decal). quad_obj carries its own mtl/texture."""
    b = scene.create_actor_builder()
    b.add_box_collision(half_size=[half, half, half])
    b.add_box_visual(half_size=[half, half, half], material=body)
    b.add_visual_from_file(filename=quad_obj,
                           pose=sapien.Pose([0, 0, half + 0.002]),
                           scale=[2 * half * 0.9, 2 * half * 0.9, 1])
    b.set_initial_pose(sapien.Pose([x, 0, half]))
    return b.build(name=f"decal{x}")


def shoot(scene, cam, name):
    scene.step(); scene.update_render(); cam.take_picture()
    rgba = cam.get_picture("Color")
    arr = (np.clip(rgba[..., :3], 0, 1) * 255).astype(np.uint8)
    Image.fromarray(arr).save(os.path.join(OUT, name)); print("wrote", name)


def main():
    cat = os.path.join(OUT, "_head_cat.png"); draw_cat(cat)
    dog = os.path.join(OUT, "_head_dog.png"); draw_dog(dog)
    quad_cat = write_quad(OUT, "cat", "_head_cat.png")
    quad_dog = write_quad(OUT, "dog", "_head_dog.png")
    scene = setup_scene(); cam = add_cam(scene)
    decal_cube(scene, -0.075, quad_cat)
    decal_cube(scene, 0.075, quad_dog)
    shoot(scene, cam, "spike_decal_top.png")


if __name__ == "__main__":
    main()
