#!/usr/bin/env python3
"""Generate oracle-qualified, balanced RoboTwin-IF seed manifests."""

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from if_benchmark.seed_contracts import IF_SEED_CONTRACTS  # noqa: E402
from if_benchmark.seed_generation import (  # noqa: E402
    GENERATION_SCHEMA_VERSION,
    GenerationError,
    accepted_seeds,
    generation_summary,
    load_generation_state,
    new_generation_state,
    run_generation,
    validate_generation_evidence,
    validate_resume_state,
    write_generation_state,
)
from if_benchmark.seed_manifest import (  # noqa: E402
    MANIFEST_SCHEMA_VERSION,
    load_manifest,
    manifest_sha256,
    validate_manifest,
    write_manifest,
)
from scripts import _task_bridge as bridge  # noqa: E402


GENERATOR_VERSION = 1


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _observed_mode(task_name, task):
    if task_name in ("bottle_verb", "arm_select", "grasp_cube_approach"):
        return str(task.mode)
    if task_name == "pick_diverse_object":
        return str(task.target_familiarity)
    if task_name == "attribute_select":
        axis = str(task.axis)
        value = int(task.value)
        values = task.AXIS_VALUES[axis]
        return f"{axis}:{values[value]}"
    if task_name == "stack_sequence":
        return ">".join(task.COLOR_NAMES[int(index)] for index in task.perm)
    if task_name == "place_relative":
        return str(task.direction)
    raise GenerationError(f"no observed-mode adapter for {task_name}")


def _failure(category, exc):
    return {"category": category, "message": f"{type(exc).__name__}: {exc}"}


def _probe_seed(task_name, task, task_args, seed):
    result = {
        "setup_ok": False,
        "plan_success": False,
        "check_success": False,
        "observed_mode": None,
        "failure": None,
    }
    stage = "setup"
    try:
        task.setup_demo(now_ep_num=0, seed=seed, is_test=True, **task_args)
        result["setup_ok"] = True
        result["observed_mode"] = _observed_mode(task_name, task)

        stage = "play_once"
        task.play_once()
        result["plan_success"] = bool(task.plan_success)
        if not result["plan_success"]:
            result["failure"] = {
                "category": "plan_success",
                "message": "task.plan_success is false",
            }
        else:
            stage = "check_success"
            result["check_success"] = bool(task.check_success())
            if not result["check_success"]:
                result["failure"] = {
                    "category": "check_success",
                    "message": "task.check_success() is false",
                }
    except Exception as exc:
        result["failure"] = _failure(stage, exc)
    finally:
        try:
            task.close_env()
        except Exception as exc:
            if result["failure"] is None:
                result["failure"] = _failure("close", exc)
    return result


@contextmanager
def _robotwin_runtime(target):
    target = Path(target).resolve()
    old_cwd = Path.cwd()
    additions = [str(target / "script"), str(target)]
    sys.path[:0] = additions
    os.chdir(target)
    try:
        import collect_data

        yield collect_data
    finally:
        os.chdir(old_cwd)
        for addition in additions:
            try:
                sys.path.remove(addition)
            except ValueError:
                pass


def _load_task(collect_data, task_name, task_config):
    captured = {}
    original_run = collect_data.run

    def capture(task, args):
        captured["task"] = task
        captured["args"] = deepcopy(args)

    collect_data.run = capture
    try:
        collect_data.main(task_name=task_name, task_config=task_config)
    finally:
        collect_data.run = original_run
    if set(captured) != {"task", "args"}:
        raise GenerationError(f"failed to capture RoboTwin task/config for {task_name}")
    task_args = captured["args"]
    task_args["render_freq"] = 0
    task_args["need_plan"] = True
    task_args["eval_mode"] = True
    return captured["task"], task_args


def _task_config_identity(target, task_config):
    if (
        not isinstance(task_config, str)
        or not task_config
        or Path(task_config).name != task_config
    ):
        raise GenerationError("task_config must be one config basename without path segments")
    path = target / "task_config" / f"{task_config}.yml"
    if not path.is_file():
        raise GenerationError(f"task config does not exist: {path}")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise GenerationError(f"cannot read task config {path}: {exc}") from exc
    return {
        "task_config_path": str(path.relative_to(target)),
        "task_config_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _provenance(target, bridge_state, config_identity):
    return {
        "generator": {
            "name": "tools/generate_if_seed_manifest.py",
            "version": GENERATOR_VERSION,
            "generation_schema_version": GENERATION_SCHEMA_VERSION,
            "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        },
        "target_root": str(target),
        "target_commit": bridge_state.get("target_commit"),
        "target_contract_dirty": bridge_state.get("target_contract_dirty"),
        "source_root": bridge_state.get("source_root"),
        "source_commit": bridge_state.get("source_commit"),
        "source_dirty": bridge_state.get("source_dirty"),
        "source_digest": bridge_state.get("source_digest"),
        "bridge_allow_compatible_commit": bridge_state.get("allow_compatible_commit"),
        **config_identity,
    }


def _paths(output_dir, task_name):
    manifest = output_dir / f"{task_name}.json"
    evidence = output_dir / f"{task_name}.generation.json"
    return manifest, evidence


def _preflight_outputs(output_dir, task_names, resume, overwrite):
    for task_name in task_names:
        manifest_path, evidence_path = _paths(output_dir, task_name)
        if resume:
            if os.path.lexists(evidence_path):
                if evidence_path.is_symlink() or not evidence_path.is_file():
                    raise GenerationError(
                        f"resume checkpoint must be a regular file: {evidence_path}"
                    )
            elif os.path.lexists(manifest_path):
                raise GenerationError(
                    f"manifest exists without resume evidence: {manifest_path}"
                )
            continue
        if overwrite:
            for path in (manifest_path, evidence_path):
                if os.path.lexists(path) and (path.is_symlink() or not path.is_file()):
                    raise GenerationError(f"refusing to replace non-regular output: {path}")
            continue
        for path in (manifest_path, evidence_path):
            if os.path.lexists(path):
                raise GenerationError(f"output exists: {path}")


def _publish_manifest(manifest_path, evidence_path, manifest, state, overwrite):
    validate_manifest(manifest)
    state["manifest_sha256"] = manifest_sha256(manifest)
    state["summary"] = generation_summary(state)
    state.setdefault("timing", {})["updated_at"] = _utc_now()
    write_generation_state(evidence_path, state, overwrite=True)

    if os.path.lexists(manifest_path):
        existing = load_manifest(manifest_path)
        if existing != manifest:
            if not overwrite:
                raise GenerationError(f"existing manifest differs: {manifest_path}")
            write_manifest(manifest_path, manifest, overwrite=True)
    else:
        write_manifest(manifest_path, manifest)
    validate_generation_evidence(load_manifest(manifest_path), state)


def _generate_task(collect_data, task_name, args, provenance):
    manifest_path, evidence_path = _paths(args.output_dir, task_name)
    expected = new_generation_state(
        task=task_name,
        task_config=args.task_config,
        accepted_blocks=args.accepted_blocks,
        max_candidate_blocks=args.max_candidate_blocks,
        candidate_floor=args.candidate_floor,
        provenance=provenance,
    )
    if args.resume and os.path.lexists(evidence_path):
        state = load_generation_state(evidence_path)
        validate_resume_state(state, expected)
    else:
        state = expected

    if state["status"] == "exhausted":
        raise GenerationError(f"checkpoint is exhausted: {evidence_path}")

    elapsed_base = float(state.get("timing", {}).get("elapsed_seconds", 0.0))
    started_at = state.get("timing", {}).get("started_at", _utc_now())
    run_started = time.monotonic()
    last_reported_blocks = len(state["blocks"])

    def checkpoint(value):
        nonlocal last_reported_blocks
        value["timing"] = {
            "started_at": started_at,
            "updated_at": _utc_now(),
            "elapsed_seconds": elapsed_base + time.monotonic() - run_started,
        }
        value["summary"] = generation_summary(value)
        write_generation_state(evidence_path, value, overwrite=True)
        if len(value["blocks"]) > last_reported_blocks:
            block = value["blocks"][-1]
            verdict = "accepted" if block["accepted"] else "rejected"
            print(
                f"{task_name}: block={block['block_index']} seeds={block['seeds']} {verdict}",
                flush=True,
            )
            last_reported_blocks = len(value["blocks"])

    if state["status"] != "complete":
        checkpoint(state)
        task, task_args = _load_task(collect_data, task_name, args.task_config)

        def probe(seed):
            return _probe_seed(task_name, task, task_args, seed)

        state = run_generation(state, probe, checkpoint=checkpoint)

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "task": task_name,
        "task_config": args.task_config,
        "seeds": list(accepted_seeds(state)),
    }
    _publish_manifest(
        manifest_path,
        evidence_path,
        manifest,
        state,
        overwrite=args.overwrite,
    )
    summary = generation_summary(state)
    print(
        f"{task_name}: complete seeds={len(manifest['seeds'])} "
        f"accepted_blocks={summary['accepted_blocks']} "
        f"rejected_blocks={summary['rejected_blocks']} manifest={manifest_path}",
        flush=True,
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Generate exact IF episode seeds by accepting only complete oracle-valid "
            "balance blocks. This does not modify RoboTwin."
        )
    )
    tasks = parser.add_mutually_exclusive_group(required=True)
    tasks.add_argument("--task", choices=tuple(IF_SEED_CONTRACTS))
    tasks.add_argument("--all", action="store_true", help="generate all maintained IF tasks")
    parser.add_argument("--task-config", default="demo_clean")
    parser.add_argument("--accepted-blocks", type=int, required=True)
    parser.add_argument("--max-candidate-blocks", type=int, required=True)
    parser.add_argument("--candidate-floor", type=int, default=100000)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--robotwin-dir")
    parser.add_argument(
        "--allow-compatible-commit",
        action="store_true",
        help="allow a reviewed API-compatible RoboTwin commit/contract override",
    )
    outputs = parser.add_mutually_exclusive_group()
    outputs.add_argument("--resume", action="store_true")
    outputs.add_argument("--overwrite", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.output_dir = args.output_dir.expanduser().resolve()
    task_names = tuple(IF_SEED_CONTRACTS) if args.all else (args.task,)
    try:
        target = bridge.resolve_robotwin_dir(args.robotwin_dir)
        bridge.bridge(
            target,
            check=True,
            allow_compatible_commit=args.allow_compatible_commit,
        )
        bridge_state = bridge.load_state(target)
        if bridge_state is None:
            raise GenerationError("bridge ownership state is missing after successful check")
        config_identity = _task_config_identity(target, args.task_config)
        provenance = _provenance(target, bridge_state, config_identity)
        _preflight_outputs(
            args.output_dir,
            task_names,
            resume=args.resume,
            overwrite=args.overwrite,
        )
    except (bridge.BridgeError, GenerationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    failures = 0
    try:
        with _robotwin_runtime(target) as collect_data:
            for task_name in task_names:
                try:
                    _generate_task(collect_data, task_name, args, provenance)
                except Exception as exc:
                    failures += 1
                    print(
                        f"ERROR {task_name}: {type(exc).__name__}: {exc}",
                        file=sys.stderr,
                    )
    except Exception as exc:
        print(f"error: cannot initialize RoboTwin runtime: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
