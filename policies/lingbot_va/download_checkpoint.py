"""Download the pinned, public RoboTwin checkpoint without a second cache copy."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from huggingface_hub import snapshot_download

CHECKPOINT = "robbyant/lingbot-va-posttrain-robotwin"
REVISION = "8c9dea8abbc5c91cc9e18bc3264b8915083bbe70"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    identity = destination / "checkpoint.json"
    if identity.exists():
        existing = json.loads(identity.read_text())
        if existing["repo_id"] != CHECKPOINT or existing["revision"] != REVISION:
            raise ValueError("Directory belongs to a different checkpoint; choose a new output directory")
    # Account for already downloaded shards on resume.
    present = sum(p.stat().st_size for p in destination.rglob("*.safetensors"))
    if shutil.disk_usage(destination).free + present < 25 * 1024**3:
        raise OSError("Need about 25 GiB for the 22.7 GiB checkpoint; choose a filesystem with more space")
    snapshot_download(CHECKPOINT, revision=REVISION, local_dir=destination,
                      allow_patterns=["text_encoder/*", "tokenizer/*", "transformer/*", "vae/*", "README.md"],
                      max_workers=3)
    identity.write_text(json.dumps({"repo_id": CHECKPOINT, "revision": REVISION,
                                   "downloaded_at": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n")
    print(f"Checkpoint ready: {destination}")


if __name__ == "__main__":
    main()
