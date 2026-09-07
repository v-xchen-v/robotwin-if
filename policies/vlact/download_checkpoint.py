"""Download pinned VLAct fine-tuning weights and the exact Qwen3 base assets."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from huggingface_hub import snapshot_download

CHECKPOINT = "StarVLA/VLAct_Qwen3OFT_Robotwin_Finetune"
REVISION = "dcf0f1d7239b28ae81a039c8d05bdfcd1d4792a5"
WEIGHTS = "checkpoints/steps_50000_pytorch_model.pt"
WEIGHTS_SHA256 = "e3823ca683057371ab94d4d66434538e2e2a53b861a87ee77a1981f941209873"
QWEN = "StarVLA/Qwen3-VL-4B-Instruct-Action"
QWEN_REVISION = "c41500cf1d287cd79e9f6602f419937b05048bd8"
QWEN_DIRECTORY = "Qwen3-VL-4B-Instruct-Action"


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
    identity = {"repo_id": CHECKPOINT, "revision": REVISION,
                "base_model": {"repo_id": QWEN, "revision": QWEN_REVISION, "directory": QWEN_DIRECTORY}}
    marker = destination / "checkpoint.json"
    if marker.exists():
        existing = json.loads(marker.read_text())
        if any(existing.get(k) != v for k, v in identity.items()):
            raise ValueError("Directory belongs to another checkpoint")
    present = sum(p.stat().st_size for p in destination.rglob("*") if p.is_file())
    if shutil.disk_usage(destination).free + present < 20 * 1024**3:
        raise OSError("Need about 20 GiB for fine-tuned and base weights")
    snapshot_download(CHECKPOINT, revision=REVISION, local_dir=destination,
                      allow_patterns=[WEIGHTS, "config.yaml", "dataset_statistics.json", "README.md"], max_workers=3)
    if sha256(destination / WEIGHTS) != WEIGHTS_SHA256:
        raise ValueError("Checkpoint SHA-256 differs from the published model card")
    snapshot_download(QWEN, revision=QWEN_REVISION, local_dir=destination / QWEN_DIRECTORY,
                      ignore_patterns=[".gitattributes"], max_workers=3)
    identity["weights_sha256"] = WEIGHTS_SHA256
    identity["downloaded_at"] = datetime.now(timezone.utc).isoformat()
    marker.write_text(json.dumps(identity, indent=2) + "\n")
    print(f"Checkpoint ready: {destination}", flush=True)


if __name__ == "__main__":
    main()
