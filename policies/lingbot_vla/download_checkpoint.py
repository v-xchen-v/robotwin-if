"""Download pinned LingBot-VLA weights and Qwen processor assets (no Qwen weights)."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from huggingface_hub import snapshot_download

CHECKPOINT = "robbyant/lingbot-vla-4b-posttrain-robotwin"
REVISION = "fb71a2c9749ccfedbb7290c2c3f0e5e7c7305c9e"
QWEN = "Qwen/Qwen2.5-VL-3B-Instruct"
QWEN_REVISION = "66285546d2b821cf421d4f5eb2576359d3770cd3"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    identity = {"repo_id": CHECKPOINT, "revision": REVISION,
                "processor": {"repo_id": QWEN, "revision": QWEN_REVISION, "directory": "qwen_processor"}}
    marker = destination / "checkpoint.json"
    if marker.exists():
        existing = json.loads(marker.read_text())
        if any(existing.get(k) != v for k, v in identity.items()):
            raise ValueError("Directory belongs to a different checkpoint; choose a new output directory")
    present = sum(p.stat().st_size for p in destination.rglob("*") if p.is_file())
    if shutil.disk_usage(destination).free + present < 18 * 1024**3:
        raise OSError("Need about 18 GiB for the 15.6 GiB checkpoint and processor assets")
    snapshot_download(CHECKPOINT, revision=REVISION, local_dir=destination,
                      allow_patterns=["model.safetensors", "config.json", "lingbotvla_cli.yaml", "README.md"],
                      max_workers=3)
    snapshot_download(QWEN, revision=QWEN_REVISION, local_dir=destination / "qwen_processor",
                      allow_patterns=["config.json", "preprocessor_config.json", "tokenizer*", "vocab.json",
                                      "merges.txt", "chat_template.json", "LICENSE"], max_workers=3)
    identity["downloaded_at"] = datetime.now(timezone.utc).isoformat()
    marker.write_text(json.dumps(identity, indent=2) + "\n")
    print(f"Checkpoint ready: {destination}")


if __name__ == "__main__":
    main()
