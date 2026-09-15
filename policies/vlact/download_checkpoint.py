"""Download pinned VLAct fine-tuning weights and the exact Qwen3 base assets."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

VARIANTS = {
    "all": {
        "repo_id": "StarVLA/VLAct_Qwen3OFT_Robotwin_all_Finetune",
        "revision": "999b37d4d7c1bd0f5588f78d72a185f6f052bf83",
        "weights": "checkpoints/steps_100000_pytorch_model.pt",
        "weights_sha256": "beb2c0ec39c3bc7173a5bd90eb59ef99854b73ca1aa3bf50fb6ffc353f477c2a",
        "data_mix": "robotwin_all_wrap_32",
    },
    "clean": {
        "repo_id": "StarVLA/VLAct_Qwen3OFT_Robotwin_Finetune",
        "revision": "dcf0f1d7239b28ae81a039c8d05bdfcd1d4792a5",
        "weights": "checkpoints/steps_50000_pytorch_model.pt",
        "weights_sha256": "e3823ca683057371ab94d4d66434538e2e2a53b861a87ee77a1981f941209873",
        "data_mix": "robotwin_wrap_32",
    },
}
QWEN = "StarVLA/Qwen3-VL-4B-Instruct-Action"
QWEN_REVISION = "c41500cf1d287cd79e9f6602f419937b05048bd8"
QWEN_DIRECTORY = "Qwen3-VL-4B-Instruct-Action"


def checkpoint_spec(identity):
    """Resolve only published, pinned identities; never infer from a directory name."""
    for spec in VARIANTS.values():
        if (identity.get("repo_id"), identity.get("revision")) == (spec["repo_id"], spec["revision"]):
            if identity.get("weights_sha256") != spec["weights_sha256"]:
                raise ValueError("Checkpoint identity has an unexpected weights SHA-256")
            return spec
    raise ValueError("Use a pinned VLAct RoboTwin All or Clean checkpoint")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    from huggingface_hub import snapshot_download

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--variant", choices=VARIANTS, default="all")
    args = parser.parse_args()
    spec = VARIANTS[args.variant]
    destination = args.output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    identity = {"repo_id": spec["repo_id"], "revision": spec["revision"],
                "base_model": {"repo_id": QWEN, "revision": QWEN_REVISION, "directory": QWEN_DIRECTORY}}
    marker = destination / "checkpoint.json"
    if marker.exists():
        existing = json.loads(marker.read_text())
        if any(existing.get(k) != v for k, v in identity.items()):
            raise ValueError("Directory belongs to another checkpoint")
    present = sum(p.stat().st_size for p in destination.rglob("*") if p.is_file())
    if shutil.disk_usage(destination).free + present < 20 * 1024**3:
        raise OSError("Need about 20 GiB for fine-tuned and base weights")
    snapshot_download(spec["repo_id"], revision=spec["revision"], local_dir=destination,
                      allow_patterns=[spec["weights"], "config.yaml", "dataset_statistics.json", "README.md"], max_workers=3)
    if sha256(destination / spec["weights"]) != spec["weights_sha256"]:
        raise ValueError("Checkpoint SHA-256 differs from the published model card")
    snapshot_download(QWEN, revision=QWEN_REVISION, local_dir=destination / QWEN_DIRECTORY,
                      ignore_patterns=[".gitattributes"], max_workers=3)
    identity["weights_sha256"] = spec["weights_sha256"]
    identity["downloaded_at"] = datetime.now(timezone.utc).isoformat()
    marker.write_text(json.dumps(identity, indent=2) + "\n")
    print(f"Checkpoint ready: {destination}", flush=True)


if __name__ == "__main__":
    main()
