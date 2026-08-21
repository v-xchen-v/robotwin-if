#!/usr/bin/env python3
"""Scan RoboTwin's assets/objects tree and emit manifest.json for the gallery.

Object formats found in the tree:
  - glb : numbered objects with visual/base{K}.glb (+ collision/)   -> GLTFLoader
  - obj : objaverse/<cat>/<inst>/textured.obj (+ separate .obj.mtl) -> OBJ+MTLLoader
          also 'cube' (textured.obj with inline mtllib)
  - urdf: numbered PartNet-mobility objects with <inst>/mobility.urdf-> URDFLoader

Paths stored in the manifest are relative to `objectsRoot`, which is a
server-absolute URL assuming `python -m http.server` runs from the repo root.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
OBJECTS_DIR = REPO_ROOT / "third_party/robotwin/assets/objects"
# server-absolute URL to the objects dir (http.server served from repo root)
OBJECTS_ROOT_URL = "/" + str(OBJECTS_DIR.relative_to(REPO_ROOT))
OUT = HERE / "manifest.json"

_num_re = re.compile(r"^(\d+)[_-](.+)$")


def natural_key(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def pretty_name(dirname: str) -> str:
    m = _num_re.match(dirname)
    base = m.group(2) if m else dirname
    return base.replace("-", " ").replace("_", " ").strip()


def glb_instances(obj_dir: Path):
    vis = obj_dir / "visual"
    files = sorted(vis.glob("*.glb"), key=lambda p: natural_key(p.name))
    return [{"mesh": f"visual/{f.name}"} for f in files]


def root_glb_instances(obj_dir: Path):
    files = sorted(obj_dir.glob("*.glb"), key=lambda p: natural_key(p.name))
    return [{"mesh": f.name} for f in files]


def urdf_instances(obj_dir: Path):
    out = []
    for inst in sorted(obj_dir.iterdir(), key=lambda p: natural_key(p.name)):
        urdf = inst / "mobility.urdf"
        if urdf.is_file():
            out.append({"mesh": f"{inst.name}/mobility.urdf"})
    return out


def obj_instance_for(inst_dir: Path):
    """Return {mesh, mtl?} for a dir containing textured.obj, else None."""
    mesh = inst_dir / "textured.obj"
    if not mesh.is_file():
        # some may just be *.obj
        objs = sorted(inst_dir.glob("*.obj"))
        objs = [o for o in objs if "collision" not in o.name.lower()]
        if not objs:
            return None
        mesh = objs[0]
    entry = {"mesh": mesh.name}
    # objaverse pattern: <inst>.obj.mtl beside textured.obj (no mtllib in obj)
    cand = list(inst_dir.glob("*.obj.mtl")) + list(inst_dir.glob("*.mtl"))
    if cand:
        entry["mtl"] = cand[0].name
    return entry


def build():
    objects = []
    for d in sorted(OBJECTS_DIR.iterdir(), key=lambda p: natural_key(p.name)):
        if not d.is_dir():
            continue
        name = d.name

        if name == "objaverse":
            # each category subdir becomes its own gallery entry
            for cat in sorted(d.iterdir(), key=lambda p: natural_key(p.name)):
                if not cat.is_dir():
                    continue
                insts = []
                for inst in sorted(cat.iterdir(), key=lambda p: natural_key(p.name)):
                    if not inst.is_dir():
                        continue
                    e = obj_instance_for(inst)
                    if e:
                        e["mesh"] = f"{inst.name}/{e['mesh']}"
                        if "mtl" in e:
                            e["mtl"] = f"{inst.name}/{e['mtl']}"
                        insts.append(e)
                if insts:
                    objects.append({
                        "id": f"objaverse/{cat.name}",
                        "dir": f"objaverse/{cat.name}",
                        "name": f"{cat.name.replace('_', ' ')}",
                        "group": "objaverse",
                        "type": "obj",
                        "instances": insts,
                    })
            continue

        # numbered / misc single objects
        if (d / "visual").is_dir() and list((d / "visual").glob("*.glb")):
            insts, typ = glb_instances(d), "glb"
        elif any((d / sub / "mobility.urdf").is_file() for sub in
                 (p.name for p in d.iterdir() if p.is_dir())):
            insts, typ = urdf_instances(d), "urdf"
        elif list(d.glob("*.glb")):
            insts, typ = root_glb_instances(d), "glb"
        elif (d / "textured.obj").is_file():
            e = obj_instance_for(d)
            insts, typ = ([e] if e else []), "obj"
        else:
            # no renderable mesh (e.g. sapien-block* with only points_info.json)
            continue

        if not insts:
            continue
        m = _num_re.match(name)
        objects.append({
            "id": name,
            "dir": name,
            "name": pretty_name(name),
            "group": "numbered" if m else "misc",
            "type": typ,
            "instances": insts,
        })

    manifest = {
        "objectsRoot": OBJECTS_ROOT_URL,
        "count": len(objects),
        "objects": objects,
    }
    OUT.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    # summary
    by_type = {}
    for o in objects:
        by_type[o["type"]] = by_type.get(o["type"], 0) + 1
    total_inst = sum(len(o["instances"]) for o in objects)
    print(f"objects: {len(objects)}  instances: {total_inst}  by_type: {by_type}")
    print(f"objectsRoot: {OBJECTS_ROOT_URL}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
