"""Download pinned WAM resources and verify Hugging Face object hashes."""

import argparse
import hashlib
import json
from pathlib import Path

MANIFEST = Path(__file__).with_name("assets.json")
POLICY_RESOURCES = {
    "fastwam": ("yuanty/fastwam", "Wan-AI/Wan2.2-TI2V-5B"),
    "motus": ("motus-robotics/Motus_robotwin2", "motus-robotics/Motus_Wan2_2_5B_pretrain",
              "Qwen/Qwen3-VL-2B-Instruct", "Wan-AI/Wan2.2-TI2V-5B"),
    "xwam": ("sharinka0715/X-WAM-checkpoints", "Wan-AI/Wan2.2-TI2V-5B"),
}


def manifest():
    return json.loads(MANIFEST.read_text())


def verify_file(path, expected):
    path = Path(path)
    if not path.is_file() or path.stat().st_size != expected["size"]:
        raise ValueError(f"Missing or incorrect file size: {path}")
    if "sha256" in expected:
        digest = hashlib.sha256()
        wanted = expected["sha256"]
    else:
        digest = hashlib.sha1(f"blob {expected['size']}\0".encode())
        wanted = expected["git_blob_sha1"]
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(chunk)
    if digest.hexdigest() != wanted:
        raise ValueError(f"Pinned checkpoint object hash mismatch: {path}")


def verify_resources(root, policy, runtime_only=False):
    data = manifest()
    verified = {}
    for repo in POLICY_RESOURCES[policy]:
        files = data[repo]["files"]
        if runtime_only:
            if repo == "motus-robotics/Motus_Wan2_2_5B_pretrain":
                continue  # The Stage 3 checkpoint already includes its finetuned backbone.
            if repo == "Wan-AI/Wan2.2-TI2V-5B" and policy != "xwam":
                files = {name: info for name, info in files.items() if name.startswith("google/") or name in
                         ("Wan2.2_VAE.pth", "models_t5_umt5-xxl-enc-bf16.pth", "config.json")}
            if repo == "Qwen/Qwen3-VL-2B-Instruct":
                files = {name: info for name, info in files.items() if name.endswith((".json", ".txt"))}
        for name, expected in files.items():
            verify_file(Path(root) / repo / name, expected)
        print(f"Verified {'runtime ' if runtime_only else ''}assets: {repo}", flush=True)
        verified[repo] = {"revision": data[repo]["revision"], "files": files}
    return verified


def main(policy=None):
    parser = argparse.ArgumentParser(description=__doc__)
    if policy is None:
        parser.add_argument("--policy", choices=(*POLICY_RESOURCES, "all"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Shared asset root; repositories are stored in owner/name subdirectories")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    selected = policy or args.policy
    policies = tuple(POLICY_RESOURCES) if selected == "all" else (selected,)
    resources = list(dict.fromkeys(repo for item in policies for repo in POLICY_RESOURCES[item]))
    root = args.output_dir.resolve()
    data = manifest()
    if not args.verify_only:
        from huggingface_hub import snapshot_download
        for repo in resources:
            print(f"Downloading {repo}@{data[repo]['revision']}", flush=True)
            snapshot_download(repo, revision=data[repo]["revision"], local_dir=root / repo,
                              allow_patterns=list(data[repo]["files"]), max_workers=3)
            for name, expected in data[repo]["files"].items():
                verify_file(root / repo / name, expected)
            print(f"Verified {repo}", flush=True)
    else:
        for item in policies:
            verify_resources(root, item)
    print(f"Verified assets for {', '.join(policies)}: {root}", flush=True)


if __name__ == "__main__":
    main()
