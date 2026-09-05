"""Simulator-free qualification helpers for Pick-Diverse-Object probes."""
import os


def video_output_path(video_dir, seed, arm):
    if arm not in {"left", "right"}:
        raise ValueError(f"video arm must be left or right, got {arm!r}")
    return os.path.join(video_dir, f"seed{int(seed)}-{arm}.mp4")


def ensure_video_output_available(path, overwrite=False):
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(f"video exists: {path} (pass --overwrite to replace it)")


def qualify_for_oracle(record):
    """Fail closed on generic scene settling before an oracle attempt."""
    if not record["settle_ok"]:
        record["oracle_attempted"] = False
        record["failure"] = "settle"
        return False
    record["oracle_attempted"] = True
    return True
