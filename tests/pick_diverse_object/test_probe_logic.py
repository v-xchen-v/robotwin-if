#!/usr/bin/env python3
"""Simulator-free Pick-Diverse-Object probe control regressions."""
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "tools"))

from _pick_diverse_probe_logic import (  # noqa: E402
    ensure_video_output_available,
    qualify_for_oracle,
    video_output_path,
)

RESULTS = []


def check(name, condition):
    ok = bool(condition)
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")


failed = {
    "settle_ok": False,
    "oracle_attempted": False,
    "oracle_ok": None,
    "failure": None,
}
check("generic settle failure prevents oracle execution",
      not qualify_for_oracle(failed)
      and failed["oracle_attempted"] is False
      and failed["oracle_ok"] is None
      and failed["failure"] == "settle")

passed = {
    "settle_ok": True,
    "oracle_attempted": False,
    "failure": None,
}
check("settled scene is marked for an oracle attempt",
      qualify_for_oracle(passed)
      and passed["oracle_attempted"] is True
      and passed["failure"] is None)

with tempfile.TemporaryDirectory() as video_dir:
    expected_path = os.path.join(video_dir, "seed25300-left.mp4")
    path = video_output_path(video_dir, 25300, "left")
    check("video path contains the exact seed and requested arm",
          path == expected_path)
    ensure_video_output_available(path)
    with open(path, "wb") as handle:
        handle.write(b"existing")
    try:
        ensure_video_output_available(path)
    except FileExistsError:
        conflict_rejected = True
    else:
        conflict_rejected = False
    check("existing video is rejected by default", conflict_rejected)
    try:
        ensure_video_output_available(path, overwrite=True)
    except FileExistsError:
        overwrite_allowed = False
    else:
        overwrite_allowed = True
    check("explicit overwrite allows an existing video", overwrite_allowed)

try:
    video_output_path("videos", 25300, "center")
except ValueError:
    invalid_arm_rejected = True
else:
    invalid_arm_rejected = False
check("video naming rejects an invalid arm", invalid_arm_rejected)

print(f"\n==== {sum(RESULTS)}/{len(RESULTS)} passed ====")
raise SystemExit(0 if RESULTS and all(RESULTS) else 1)
