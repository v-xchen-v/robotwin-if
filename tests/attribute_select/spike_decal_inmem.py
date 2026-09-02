"""
IF-Attribute-Select — decal via FULLY IN-MEMORY mesh + texture (no files).

This is the RECOMMENDED production recipe for the decal mode. Unlike
spike_decal_top.py (which writes quad.obj/mtl/png to disk and references them by
path), here nothing touches the filesystem:

  PIL draw -> numpy RGBA array
    -> RenderTexture2D(array, "R8G8B8A8Unorm", srgb=True)         # texture from array
    -> RenderMaterial().set_base_color_texture(tex)
    -> RenderShapeTriangleMesh(verts, tris, normals, uvs, mat)    # quad + explicit [0,1] UV
    -> manual Entity: PhysX box collision + RenderBody(cube body box + decal mesh on top)

Why file-free matters: no paths to resolve => immune to (a) robotwin-if being
nested as a submodule of another repo, (b) symlinks being dereferenced by
copy/vendor/Docker, (c) CWD-relative surprises. The env stays pure code, exactly
like the create_box-based IF tasks (laptop_verb / arm_select / grasp_cube).

Run (from repo root):
  conda run -n RoboTwin python tests/attribute_select/spike_decal_inmem.py
Output -> notes/2026-09-01-attribute-select/evidence/spike_inmem.png
"""
import os
import numpy as np
from PIL import Image, ImageDraw
import sapien.core as sapien
import sapien.render as R

OUT = os.path.join(os.path.dirname(__file__), "..", "..",
                   "notes", "2026-09-01-attribute-select", "evidence")
OUT = os.path.abspath(OUT)


def cat_arr(S=512):
    """Cat head (pointy ears) as an RGBA uint8 array — no file written."""
    img = Image.new("RGBA", (S, S), (248, 240, 229, 255)); d = ImageDraw.Draw(img)
    cx, cy = S * 0.5, S * 0.52; fur = (238, 150, 60, 255)
    d.polygon([(cx - 0.34 * S, cy - 0.06 * S), (cx - 0.46 * S, cy - 0.48 * S),
               (cx - 0.02 * S, cy - 0.24 * S)], fill=fur)
    d.polygon([(cx + 0.34 * S, cy - 0.06 * S), (cx + 0.46 * S, cy - 0.48 * S),
               (cx + 0.02 * S, cy - 0.24 * S)], fill=fur)
    d.ellipse([cx - 0.40 * S, cy - 0.28 * S, cx + 0.40 * S, cy + 0.44 * S], fill=fur)
    for sx in (-1, 1):
        d.ellipse([cx + sx * 0.18 * S - 0.07 * S, cy - 0.02 * S,
                   cx + sx * 0.18 * S + 0.07 * S, cy + 0.12 * S], fill=(30, 30, 30, 255))
    d.polygon([(cx - 0.06 * S, cy + 0.15 * S), (cx + 0.06 * S, cy + 0.15 * S),
               (cx, cy + 0.23 * S)], fill=(170, 70, 70, 255))
    return np.asarray(img, dtype=np.uint8)


def dog_arr(S=512):
    """Dog head (floppy side ears) as an RGBA uint8 array."""
    img = Image.new("RGBA", (S, S), (247, 240, 230, 255)); d = ImageDraw.Draw(img)
    cx, cy = S * 0.5, S * 0.5; fur = (150, 100, 60, 255); ear = (105, 68, 40, 255)
    d.ellipse([cx - 0.50 * S, cy - 0.22 * S, cx - 0.14 * S, cy + 0.42 * S], fill=ear)
    d.ellipse([cx + 0.14 * S, cy - 0.22 * S, cx + 0.50 * S, cy + 0.42 * S], fill=ear)
    d.ellipse([cx - 0.36 * S, cy - 0.34 * S, cx + 0.36 * S, cy + 0.38 * S], fill=fur)
    d.ellipse([cx - 0.18 * S, cy + 0.06 * S, cx + 0.18 * S, cy + 0.38 * S], fill=(210, 180, 145, 255))
    for sx in (-1, 1):
        d.ellipse([cx + sx * 0.15 * S - 0.06 * S, cy - 0.10 * S,
                   cx + sx * 0.15 * S + 0.06 * S, cy + 0.03 * S], fill=(30, 30, 30, 255))
    d.ellipse([cx - 0.07 * S, cy + 0.14 * S, cx + 0.07 * S, cy + 0.25 * S], fill=(20, 20, 20, 255))
    return np.asarray(img, dtype=np.uint8)


def make_scene():
    engine = sapien.Engine(); renderer = sapien.SapienRenderer()
    engine.set_renderer(renderer)
    scene = engine.create_scene(sapien.SceneConfig()); scene.add_ground(0)
    scene.default_physical_material = scene.create_physical_material(0.5, 0.5, 0)
    scene.set_ambient_light([0.6, 0.6, 0.6])
    scene.add_directional_light([0, 0.3, -1], [0.8, 0.8, 0.8])
    return scene


def decal_cube_inmem(scene, x, arr, half=0.05, body=(0.42, 0.44, 0.5)):
    """One rigid entity: gray cube body + a top decal built entirely from arrays.

    NOTE (stage ③): this manual-entity path has no create_box grasp metadata.
    In the real env, prefer building the body via create_box (keeps contact
    points) and attaching only the decal RenderShapeTriangleMesh to its
    RenderBodyComponent.
    """
    ent = sapien.Entity()
    rc = sapien.physx.PhysxRigidDynamicComponent()
    rc.attach(sapien.physx.PhysxCollisionShapeBox(
        half_size=[half] * 3, material=scene.default_physical_material))
    rb = R.RenderBodyComponent()
    rb.attach(R.RenderShapeBox([half] * 3, R.RenderMaterial(base_color=[*body, 1])))
    # decal: texture from array + quad mesh with explicit UV, no files
    tex = R.RenderTexture2D(arr, "R8G8B8A8Unorm", srgb=True)
    mat = R.RenderMaterial(); mat.set_base_color_texture(tex)
    mat.base_color = [1, 1, 1, 1]; mat.roughness = 0.7
    q = half * 0.9
    verts = np.array([[-q, -q, 0], [q, -q, 0], [q, q, 0], [-q, q, 0]], dtype=np.float32)
    tris = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.uint32)
    norms = np.tile([0, 0, 1], (4, 1)).astype(np.float32)
    uvs = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], dtype=np.float32)  # v-flip -> upright
    mesh = R.RenderShapeTriangleMesh(verts, tris, norms, uvs, mat)
    mesh.set_local_pose(sapien.Pose([0, 0, half + 0.002]))
    rb.attach(mesh)
    ent.add_component(rc); ent.add_component(rb)
    ent.set_pose(sapien.Pose([x, 0, half])); scene.add_entity(ent)
    return ent


def add_cam(scene):
    cam = scene.add_camera(name="c", width=640, height=480,
                           fovy=np.deg2rad(42), near=0.05, far=20)
    pos = np.array([0.0, -0.16, 0.42]); fwd = np.array([0, 0.35, -1.0]); fwd /= np.linalg.norm(fwd)
    left = np.array([-1.0, 0, 0]); up = np.cross(fwd, left)
    m = np.eye(4); m[:3, :3] = np.stack([fwd, left, up], 1); m[:3, 3] = pos
    cam.entity.set_pose(sapien.Pose(m))
    return cam


def main():
    scene = make_scene()
    decal_cube_inmem(scene, -0.075, cat_arr())
    decal_cube_inmem(scene, 0.075, dog_arr())
    cam = add_cam(scene)
    scene.step(); scene.update_render(); cam.take_picture()
    a = (np.clip(cam.get_picture("Color")[..., :3], 0, 1) * 255).astype(np.uint8)
    Image.fromarray(a).save(os.path.join(OUT, "spike_inmem.png"))
    print("wrote spike_inmem.png (no files created for the decal)")


if __name__ == "__main__":
    main()
