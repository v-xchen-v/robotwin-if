"""Simulator-free complete-block generation state machine."""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile

from .seed_contracts import (
    CONTRACT_SCHEMA_VERSION,
    contract_for,
    describe_seed,
    expand_block,
    first_block_at_or_above,
)


GENERATION_SCHEMA_VERSION = 1
MAX_GENERATION_BYTES = 16 * 1024 * 1024


class GenerationError(RuntimeError):
    pass


def new_generation_state(
    *,
    task,
    task_config,
    accepted_blocks,
    max_candidate_blocks,
    candidate_floor,
    provenance,
):
    contract_for(task)
    if not isinstance(task_config, str) or not task_config.strip():
        raise GenerationError("task_config must be a non-empty string")
    if isinstance(accepted_blocks, bool) or not isinstance(accepted_blocks, int) or accepted_blocks < 1:
        raise GenerationError("accepted_blocks must be a positive integer")
    if (
        isinstance(max_candidate_blocks, bool)
        or not isinstance(max_candidate_blocks, int)
        or max_candidate_blocks < accepted_blocks
    ):
        raise GenerationError("max_candidate_blocks must be an integer >= accepted_blocks")
    if not isinstance(provenance, dict):
        raise GenerationError("provenance must be an object")
    first_block = first_block_at_or_above(task, candidate_floor)
    return {
        "schema_version": GENERATION_SCHEMA_VERSION,
        "contract_schema_version": CONTRACT_SCHEMA_VERSION,
        "status": "running",
        "parameters": {
            "task": task,
            "task_config": task_config,
            "accepted_blocks": accepted_blocks,
            "max_candidate_blocks": max_candidate_blocks,
            "candidate_floor": candidate_floor,
            "first_block": first_block,
        },
        "provenance": deepcopy(provenance),
        "next_block": first_block,
        "blocks": [],
    }


def _require_int(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise GenerationError(f"{name} must be an integer >= {minimum}")


def validate_generation_state(state):
    if not isinstance(state, dict):
        raise GenerationError("generation checkpoint must be an object")
    if state.get("schema_version") != GENERATION_SCHEMA_VERSION:
        raise GenerationError("generation checkpoint schema mismatch")
    if state.get("contract_schema_version") != CONTRACT_SCHEMA_VERSION:
        raise GenerationError("seed contract schema mismatch")

    params = state.get("parameters")
    if not isinstance(params, dict):
        raise GenerationError("generation checkpoint parameters must be an object")
    required = {
        "task",
        "task_config",
        "accepted_blocks",
        "max_candidate_blocks",
        "candidate_floor",
        "first_block",
    }
    if set(params) != required:
        raise GenerationError("generation checkpoint parameters have unexpected keys")
    try:
        contract_for(params["task"])
    except ValueError as exc:
        raise GenerationError(str(exc)) from exc
    if not isinstance(params["task_config"], str) or not params["task_config"].strip():
        raise GenerationError("generation checkpoint task_config is invalid")
    _require_int(params["accepted_blocks"], "accepted_blocks", 1)
    _require_int(params["max_candidate_blocks"], "max_candidate_blocks", params["accepted_blocks"])
    _require_int(params["candidate_floor"], "candidate_floor")
    expected_first = first_block_at_or_above(params["task"], params["candidate_floor"])
    if params["first_block"] != expected_first:
        raise GenerationError("generation checkpoint first_block is inconsistent")
    if not isinstance(state.get("provenance"), dict):
        raise GenerationError("generation checkpoint provenance must be an object")

    blocks = state.get("blocks")
    if not isinstance(blocks, list):
        raise GenerationError("generation checkpoint blocks must be a list")
    if len(blocks) > params["max_candidate_blocks"]:
        raise GenerationError("generation checkpoint exceeds max_candidate_blocks")

    accepted_count = 0
    for position, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise GenerationError("generation checkpoint block must be an object")
        block_index = expected_first + position
        if block.get("block_index") != block_index:
            raise GenerationError("generation checkpoint block order is inconsistent")
        expected_seeds = list(expand_block(params["task"], block_index))
        if block.get("seeds") != expected_seeds:
            raise GenerationError("generation checkpoint block seeds are inconsistent")
        episodes = block.get("episodes")
        if not isinstance(episodes, list) or len(episodes) != len(expected_seeds):
            raise GenerationError("generation checkpoint episodes are incomplete")

        episode_passes = []
        for seed, episode in zip(expected_seeds, episodes):
            if not isinstance(episode, dict) or episode.get("seed") != seed:
                raise GenerationError("generation checkpoint episode seed is inconsistent")
            expected_mode = describe_seed(params["task"], seed).mode
            if episode.get("expected_mode") != expected_mode:
                raise GenerationError("generation checkpoint expected mode is inconsistent")
            for field in ("setup_ok", "plan_success", "check_success", "accepted"):
                if not isinstance(episode.get(field), bool):
                    raise GenerationError(f"generation checkpoint episode {field} must be boolean")
            passes = (
                episode["setup_ok"]
                and episode["plan_success"]
                and episode["check_success"]
                and episode.get("observed_mode") == expected_mode
                and episode.get("failure") is None
            )
            if episode["accepted"] != passes:
                raise GenerationError("generation checkpoint episode acceptance is inconsistent")
            if not passes:
                failure = episode.get("failure")
                if not isinstance(failure, dict):
                    raise GenerationError("rejected generation episode must record failure")
                if not isinstance(failure.get("category"), str) or not failure["category"]:
                    raise GenerationError("generation failure category is invalid")
                if not isinstance(failure.get("message"), str):
                    raise GenerationError("generation failure message is invalid")
            episode_passes.append(passes)

        block_passes = all(episode_passes)
        if not isinstance(block.get("accepted"), bool) or block["accepted"] != block_passes:
            raise GenerationError("generation checkpoint block acceptance is inconsistent")
        accepted_count += int(block_passes)

    expected_next = expected_first + len(blocks)
    if state.get("next_block") != expected_next:
        raise GenerationError("generation checkpoint next_block is inconsistent")
    status = state.get("status")
    if status not in ("running", "complete", "exhausted"):
        raise GenerationError("invalid generation checkpoint status")
    if status == "complete" and accepted_count != params["accepted_blocks"]:
        raise GenerationError("complete generation checkpoint has wrong accepted count")
    if status == "exhausted" and (
        accepted_count >= params["accepted_blocks"]
        or len(blocks) != params["max_candidate_blocks"]
    ):
        raise GenerationError("exhausted generation checkpoint is inconsistent")
    return state


def validate_resume_state(state, expected):
    validate_generation_state(state)
    validate_generation_state(expected)
    for field in ("parameters", "provenance"):
        if state.get(field) != expected.get(field):
            raise GenerationError(f"resume {field} do not match the requested run")
    return state


def _failed_episode(seed, expected_mode, category, message):
    return {
        "seed": seed,
        "expected_mode": expected_mode,
        "observed_mode": None,
        "setup_ok": False,
        "plan_success": False,
        "check_success": False,
        "accepted": False,
        "failure": {"category": category, "message": str(message)},
    }


def _normalize_episode(task, seed, probe):
    expected_mode = describe_seed(task, seed).mode
    try:
        raw = probe(seed)
    except Exception as exc:
        return _failed_episode(seed, expected_mode, "probe", f"{type(exc).__name__}: {exc}")
    if not isinstance(raw, dict):
        return _failed_episode(seed, expected_mode, "probe", "probe did not return an object")

    episode = {
        "seed": seed,
        "expected_mode": expected_mode,
        "observed_mode": raw.get("observed_mode"),
        "setup_ok": raw.get("setup_ok") is True,
        "plan_success": raw.get("plan_success") is True,
        "check_success": raw.get("check_success") is True,
        "accepted": False,
        "failure": raw.get("failure"),
    }
    if not episode["setup_ok"]:
        category = "setup"
    elif not episode["plan_success"]:
        category = "plan_success"
    elif not episode["check_success"]:
        category = "check_success"
    elif episode["observed_mode"] != expected_mode:
        category = "mode_mismatch"
    elif episode["failure"] is not None:
        category = "probe"
    else:
        episode["accepted"] = True
        episode["failure"] = None
        return episode

    if episode["failure"] is None:
        episode["failure"] = {"category": category, "message": category}
    elif isinstance(episode["failure"], str):
        episode["failure"] = {"category": category, "message": episode["failure"]}
    elif not isinstance(episode["failure"], dict):
        episode["failure"] = {"category": category, "message": repr(episode["failure"])}
    else:
        episode["failure"] = dict(episode["failure"])
        episode["failure"].setdefault("category", category)
        episode["failure"].setdefault("message", category)
    if category == "mode_mismatch":
        episode["failure"] = {
            "category": category,
            "message": f"expected {expected_mode!r}, observed {episode['observed_mode']!r}",
        }
    return episode


def accepted_block_records(state):
    return tuple(block for block in state["blocks"] if block["accepted"])


def rejected_block_records(state):
    return tuple(block for block in state["blocks"] if not block["accepted"])


def accepted_seeds(state):
    return tuple(
        seed
        for block in accepted_block_records(state)
        for seed in block["seeds"]
    )


def generation_summary(state):
    validate_generation_state(state)
    accepted = accepted_block_records(state)
    rejected = rejected_block_records(state)
    categories = {}
    for block in rejected:
        for episode in block["episodes"]:
            if episode["accepted"]:
                continue
            category = episode["failure"]["category"]
            categories[category] = categories.get(category, 0) + 1
    return {
        "candidate_blocks": len(state["blocks"]),
        "accepted_blocks": len(accepted),
        "rejected_blocks": len(rejected),
        "accepted_block_ids": [block["block_index"] for block in accepted],
        "rejected_block_ids": [block["block_index"] for block in rejected],
        "failure_categories": categories,
    }


def _validate_provenance(provenance):
    required = {
        "generator",
        "target_root",
        "target_commit",
        "target_contract_dirty",
        "source_root",
        "source_commit",
        "source_dirty",
        "source_digest",
        "bridge_allow_compatible_commit",
        "task_config_path",
        "task_config_sha256",
    }
    if set(provenance) != required:
        raise GenerationError("generation evidence provenance has unexpected keys")
    generator = provenance["generator"]
    if not isinstance(generator, dict) or set(generator) != {
        "name",
        "version",
        "generation_schema_version",
        "manifest_schema_version",
    }:
        raise GenerationError("generation evidence generator provenance is invalid")
    if generator["name"] != "tools/generate_if_seed_manifest.py":
        raise GenerationError("generation evidence generator name is invalid")
    for field in ("version", "generation_schema_version", "manifest_schema_version"):
        _require_int(generator[field], f"generator {field}", 1)
    for field in ("target_root", "source_root"):
        value = provenance[field]
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise GenerationError(f"generation evidence {field} must be an absolute path")
    for field in ("target_commit", "source_commit"):
        value = provenance[field]
        if value is not None and (not isinstance(value, str) or not value):
            raise GenerationError(f"generation evidence {field} is invalid")
    for field in ("target_contract_dirty", "source_dirty"):
        if provenance[field] not in (True, False, None):
            raise GenerationError(f"generation evidence {field} is invalid")
    if not isinstance(provenance["bridge_allow_compatible_commit"], bool):
        raise GenerationError("generation evidence bridge override flag is invalid")
    config_path = provenance["task_config_path"]
    if (
        not isinstance(config_path, str)
        or Path(config_path).is_absolute()
        or Path(config_path).parts != ("task_config", Path(config_path).name)
        or not config_path.endswith(".yml")
    ):
        raise GenerationError("generation evidence task_config_path is invalid")
    for field in ("source_digest", "task_config_sha256"):
        digest = provenance[field]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise GenerationError(f"generation evidence {field} is invalid")


def validate_generation_evidence(manifest, evidence):
    from .seed_manifest import canonical_manifest, manifest_sha256

    manifest = canonical_manifest(manifest)
    validate_generation_state(evidence)
    _validate_provenance(evidence["provenance"])
    params = evidence["parameters"]
    if evidence["status"] != "complete":
        raise GenerationError("generation evidence is not complete")
    if params["task"] != manifest["task"] or params["task_config"] != manifest["task_config"]:
        raise GenerationError("generation evidence task/config do not match manifest")
    expected_config_path = f"task_config/{manifest['task_config']}.yml"
    if evidence["provenance"]["task_config_path"] != expected_config_path:
        raise GenerationError("generation evidence task-config path does not match manifest")
    if list(accepted_seeds(evidence)) != manifest["seeds"]:
        raise GenerationError("generation evidence accepted seeds do not match manifest")
    if evidence.get("manifest_sha256") != manifest_sha256(manifest):
        raise GenerationError("generation evidence manifest SHA-256 mismatch")
    if "summary" in evidence and evidence["summary"] != generation_summary(evidence):
        raise GenerationError("generation evidence summary is inconsistent")
    return evidence


def _generation_bytes(state):
    validate_generation_state(state)
    return (json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def load_generation_state(path):
    path = Path(path)
    if not os.path.lexists(path):
        raise GenerationError(f"generation checkpoint does not exist: {path}")
    if path.is_symlink() or not path.is_file():
        raise GenerationError(f"generation checkpoint must be a regular file: {path}")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise GenerationError(f"cannot stat generation checkpoint {path}: {exc}") from exc
    if size > MAX_GENERATION_BYTES:
        raise GenerationError(
            f"generation checkpoint exceeds the {MAX_GENERATION_BYTES}-byte safety limit"
        )
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GenerationError(f"cannot read generation checkpoint {path}: {exc}") from exc
    return validate_generation_state(state)


def write_generation_state(path, state, overwrite=False):
    path = Path(path)
    payload = _generation_bytes(state)
    if len(payload) > MAX_GENERATION_BYTES:
        raise GenerationError(
            f"generation checkpoint exceeds the {MAX_GENERATION_BYTES}-byte safety limit"
        )
    if os.path.lexists(path):
        if not overwrite:
            raise GenerationError(f"output exists: {path}")
        if path.is_symlink() or not path.is_file():
            raise GenerationError(f"refusing to replace non-regular output: {path}")

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
        raise GenerationError(f"cannot write generation checkpoint {path}: {exc}") from exc
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def run_generation(state, probe, checkpoint=None):
    validate_generation_state(state)
    params = state["parameters"]
    task = params["task"]
    target = params["accepted_blocks"]
    limit = params["max_candidate_blocks"]

    if state["status"] == "complete":
        return state
    if state["status"] == "exhausted":
        raise GenerationError("generation checkpoint is already exhausted")

    while len(accepted_block_records(state)) < target and len(state["blocks"]) < limit:
        block_index = state["next_block"]
        seeds = expand_block(task, block_index)
        episodes = [_normalize_episode(task, seed, probe) for seed in seeds]
        block = {
            "block_index": block_index,
            "seeds": list(seeds),
            "accepted": all(item["accepted"] for item in episodes),
            "episodes": episodes,
        }
        state["blocks"].append(block)
        state["next_block"] = block_index + 1
        if checkpoint is not None:
            checkpoint(state)

    if len(accepted_block_records(state)) == target:
        state["status"] = "complete"
        if checkpoint is not None:
            checkpoint(state)
        return state

    state["status"] = "exhausted"
    if checkpoint is not None:
        checkpoint(state)
    raise GenerationError(
        f"accepted {len(accepted_block_records(state))}/{target} blocks after "
        f"{len(state['blocks'])} candidates"
    )
