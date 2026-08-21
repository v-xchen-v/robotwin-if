#!/usr/bin/env python3
"""Scan RoboTwin's data/ tree and emit manifest.json for the dataset viewer.

Layout expected under DATA_DIR:
    <task>/<demo>/video/episodeN.mp4
    <task>/<demo>/instructions/episodeN.json   {"seen": [...], "unseen": [...]}

Each episode pairs one video with one instruction file. Paths stored in the
manifest are server-absolute URLs assuming `python -m http.server` runs from
the repo root.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
DATA_DIR = REPO_ROOT / "third_party/robotwin/data"
OUT = HERE / "manifest.json"

_ep_re = re.compile(r"^episode(\d+)$")


def episode_num(stem: str):
    m = _ep_re.match(stem)
    return int(m.group(1)) if m else None


def load_instructions(path: Path):
    try:
        d = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"seen": [], "unseen": []}
    return {"seen": d.get("seen", []) or [], "unseen": d.get("unseen", []) or []}


def scan_demo(demo_dir: Path):
    video_dir = demo_dir / "video"
    instr_dir = demo_dir / "instructions"
    if not video_dir.is_dir():
        return []

    episodes = []
    for vid in video_dir.glob("*.mp4"):
        num = episode_num(vid.stem)
        if num is None:
            continue
        instr_path = instr_dir / f"{vid.stem}.json"
        instr = load_instructions(instr_path) if instr_path.is_file() else {"seen": [], "unseen": []}
        rel_video = "/" + str(vid.relative_to(REPO_ROOT))
        episodes.append({
            "num": num,
            "name": vid.stem,
            "video": rel_video,
            "seen": instr["seen"],
            "unseen": instr["unseen"],
            "hasInstr": instr_path.is_file(),
        })
    episodes.sort(key=lambda e: e["num"])
    return episodes


def main():
    tasks = []
    if not DATA_DIR.is_dir():
        print(f"[warn] data dir not found: {DATA_DIR}")
    else:
        for task_dir in sorted(p for p in DATA_DIR.iterdir() if p.is_dir()):
            for demo_dir in sorted(p for p in task_dir.iterdir() if p.is_dir()):
                episodes = scan_demo(demo_dir)
                if not episodes:
                    continue
                tasks.append({
                    "task": task_dir.name,
                    "demo": demo_dir.name,
                    "id": f"{task_dir.name}/{demo_dir.name}",
                    "episodes": episodes,
                })

    manifest = {"tasks": tasks}
    OUT.write_text(json.dumps(manifest, indent=1))
    n_ep = sum(len(t["episodes"]) for t in tasks)
    print(f"[ok] {len(tasks)} datasets, {n_ep} episodes -> {OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
