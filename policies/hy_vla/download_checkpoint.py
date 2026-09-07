"""Download and verify the pinned public Hy-VLA RoboTwin checkpoint."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from huggingface_hub import snapshot_download

CHECKPOINT = "tencent/Hy-Embodied-0.5-VLA-RoboTwin"
REVISION = "bd7bba6f5934ad62293a2a34f74760c6a3ef2ff8"
WEIGHTS_SHA256 = "3bd6c16225f905a298340489d519498d4e5ecf5bcdd28a5c1df63e29894fef60"
NORM_SHA256 = "ce81158fb16dfcb16caa80ba33dd277d07b81e40de96d959616447d614feae41"
SOURCE_REVISION = "af57e7507ec5964b52fdf6296741e553cbcd3288"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    destination = parser.parse_args().output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    marker = destination / "checkpoint.json"
    identity = {"repo_id": CHECKPOINT, "revision": REVISION}
    if marker.exists():
        existing = json.loads(marker.read_text())
        if any(existing.get(k) != v for k, v in identity.items()):
            raise ValueError("Directory belongs to another checkpoint")
    snapshot_download(CHECKPOINT, revision=REVISION, local_dir=destination,
                      ignore_patterns=[".gitattributes"], max_workers=3)
    if sha256(destination / "model.safetensors") != WEIGHTS_SHA256:
        raise ValueError("Checkpoint SHA-256 differs from the pinned Hugging Face LFS object")
    if sha256(destination / "norm_stats.pkl") != NORM_SHA256:
        raise ValueError("Normalization pickle checksum mismatch")
    identity.update(weights_sha256=WEIGHTS_SHA256,
                    files_sha256={p.name: sha256(p) for p in destination.iterdir()
                                  if p.is_file() and p.name not in ("model.safetensors", "checkpoint.json")},
                    downloaded_at=datetime.now(timezone.utc).isoformat())
    marker.write_text(json.dumps(identity, indent=2) + "\n")
    print(f"Checkpoint verified: {destination}", flush=True)


if __name__ == "__main__":
    main()
