#!/usr/bin/env python3
"""Validate flat RoboTwin-IF seed manifests without importing the simulator."""

import argparse
import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from if_benchmark.seed_generation import (  # noqa: E402
    GenerationError,
    load_generation_state,
    validate_generation_evidence,
)
from if_benchmark.seed_manifest import (  # noqa: E402
    ManifestError,
    load_manifest,
    validate_manifest,
)


def _manifest_paths(inputs):
    paths = []
    orphan_evidence = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir() and not path.is_symlink():
            candidates = sorted(path.rglob("*.json"))
            paths.extend(
                candidate
                for candidate in candidates
                if not candidate.name.endswith(".generation.json")
            )
            for evidence in candidates:
                if not evidence.name.endswith(".generation.json"):
                    continue
                manifest_name = evidence.name.removesuffix(".generation.json") + ".json"
                if not (evidence.parent / manifest_name).is_file():
                    orphan_evidence.append(evidence)
        else:
            paths.append(path)
    unique = []
    seen = set()
    for path in paths:
        resolved = os.path.abspath(path)
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique, orphan_evidence


def _format_denominators(denominators):
    return ", ".join(f"{mode}={count}" for mode, count in denominators.items())


def build_parser():
    parser = argparse.ArgumentParser(
        description="Validate exact, balanced RoboTwin-IF episode seed lists."
    )
    parser.add_argument("paths", nargs="+", help="manifest file(s) or directories")
    parser.add_argument(
        "--require-evidence",
        action="store_true",
        help="require and verify each adjacent .generation.json sidecar",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    paths, orphan_evidence = _manifest_paths(args.paths)
    if not paths and not orphan_evidence:
        print("error: no manifest JSON files found", file=sys.stderr)
        return 2

    failures = 0
    for evidence_path in orphan_evidence:
        failures += 1
        print(
            f"ERROR {evidence_path}: generation evidence has no adjacent manifest",
            file=sys.stderr,
        )
    for path in paths:
        try:
            manifest = load_manifest(path)
            checked = validate_manifest(manifest)
            evidence_path = path.with_name(f"{path.stem}.generation.json")
            evidence_status = "not present"
            if os.path.lexists(evidence_path):
                evidence = load_generation_state(evidence_path)
                validate_generation_evidence(manifest, evidence)
                evidence_status = "verified"
            elif args.require_evidence:
                raise GenerationError(f"generation evidence does not exist: {evidence_path}")

            print(
                f"OK {path}: task={manifest['task']} seeds={len(manifest['seeds'])} "
                f"blocks={len(checked['block_ids'])} "
                f"modes=[{_format_denominators(checked['mode_denominators'])}] "
                f"evidence={evidence_status}"
            )
        except (ManifestError, GenerationError, OSError) as exc:
            failures += 1
            print(f"ERROR {path}: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
