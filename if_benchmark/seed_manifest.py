"""Strict flat seed-manifest I/O for external policy evaluators."""

import hashlib
import json
import os
from pathlib import Path
import tempfile

from .seed_contracts import contract_for, mode_denominators, validate_complete_blocks


MANIFEST_SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_MANIFEST_SEEDS = 100_000
MANIFEST_KEYS = ("schema_version", "task", "task_config", "seeds")


class ManifestError(ValueError):
    pass


def validate_manifest(data):
    if not isinstance(data, dict):
        raise ManifestError("manifest must be a JSON object")
    if set(data) != set(MANIFEST_KEYS):
        raise ManifestError(
            f"manifest keys must be exactly {list(MANIFEST_KEYS)}, got {sorted(data)}"
        )
    if data["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise ManifestError(
            f"unsupported manifest schema_version: {data['schema_version']!r}"
        )

    task = data["task"]
    if not isinstance(task, str):
        raise ManifestError("task must be a string")
    try:
        contract_for(task)
    except ValueError as exc:
        raise ManifestError(str(exc)) from exc

    task_config = data["task_config"]
    if not isinstance(task_config, str) or not task_config.strip():
        raise ManifestError("task_config must be a non-empty string")
    if task_config != task_config.strip():
        raise ManifestError("task_config must not contain leading/trailing whitespace")

    seeds = data["seeds"]
    if not isinstance(seeds, list):
        raise ManifestError("seeds must be a JSON array")
    if len(seeds) > MAX_MANIFEST_SEEDS:
        raise ManifestError(
            f"manifest exceeds the {MAX_MANIFEST_SEEDS}-seed safety limit"
        )
    try:
        block_ids = validate_complete_blocks(task, seeds)
        denominators = mode_denominators(task, seeds)
    except ValueError as exc:
        raise ManifestError(str(exc)) from exc

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "task": task,
        "task_config": task_config,
        "seeds": list(seeds),
        "block_ids": block_ids,
        "mode_denominators": denominators,
    }


def canonical_manifest(data):
    checked = validate_manifest(data)
    return {
        "schema_version": checked["schema_version"],
        "task": checked["task"],
        "task_config": checked["task_config"],
        "seeds": checked["seeds"],
    }


def manifest_bytes(data):
    payload = canonical_manifest(data)
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def manifest_sha256(data):
    return hashlib.sha256(manifest_bytes(data)).hexdigest()


def load_manifest(path):
    path = Path(path)
    if not os.path.lexists(path):
        raise ManifestError(f"manifest does not exist: {path}")
    if path.is_symlink() or not path.is_file():
        raise ManifestError(f"manifest must be a regular file: {path}")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ManifestError(f"cannot stat manifest {path}: {exc}") from exc
    if size > MAX_MANIFEST_BYTES:
        raise ManifestError(
            f"manifest exceeds the {MAX_MANIFEST_BYTES}-byte safety limit: {path}"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc
    return canonical_manifest(data)


def write_manifest(path, data, overwrite=False):
    path = Path(path)
    payload = manifest_bytes(data)
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ManifestError(
            f"manifest exceeds the {MAX_MANIFEST_BYTES}-byte safety limit"
        )
    if os.path.lexists(path):
        if not overwrite:
            raise ManifestError(f"output exists: {path}")
        if path.is_symlink() or not path.is_file():
            raise ManifestError(f"refusing to replace non-regular output: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", dir=path.parent, delete=False
        ) as handle:
            temp_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except OSError as exc:
        raise ManifestError(f"cannot write manifest {path}: {exc}") from exc
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return manifest_sha256(data)
