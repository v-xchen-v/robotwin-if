"""Download and verify the pinned public DM05 RoboTwin2 checkpoint."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from huggingface_hub import snapshot_download

CHECKPOINT = "Dexmal/DM05-robotwin2"
REVISION = "bef09062f8d9744b7691d0a5db4e23834e46071e"
WEIGHTS_SHA256 = "74e8dbb475148080e35ede3f6823322eb6a0b061c8f843a932a4c4ce879bd282"
SOURCE_REVISION = "c4762fed95e430bf14e86beed73166b8dd18b094"


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
    identity.update(weights_sha256=WEIGHTS_SHA256,
                    files_sha256={p.name: sha256(p) for p in destination.iterdir()
                                  if p.is_file() and p.name not in ("model.safetensors", "checkpoint.json")},
                    downloaded_at=datetime.now(timezone.utc).isoformat())
    marker.write_text(json.dumps(identity, indent=2) + "\n")
    print(f"Checkpoint verified: {destination}", flush=True)


if __name__ == "__main__":
    main()
