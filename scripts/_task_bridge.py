#!/usr/bin/env python3
"""Safely install the maintained RoboTwin-IF task plugins into RoboTwin."""

import argparse
import ast
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCKED_ROBOTWIN_COMMIT = "0aeea2d669c0f8516f4d5785f0aa33ba812c14b4"
STATE_NAME = ".robotwin-if-bridge.json"
STATE_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1024 * 1024
MAX_STATE_LINKS = 256

MAINTAINED_TASKS = (
    "bottle_verb",
    "pick_diverse_object",
    "attribute_select",
    "arm_select",
    "stack_sequence",
    "place_relative",
    "grasp_cube_approach",
)
ENV_HELPERS = (
    "_if_grounding.py",
    "_if_relative.py",
    "_pick_diverse_object_pool.py",
    "_if_eval.py",
)

BASE_TASK_METHODS = {
    "_init_task_env_",
    "move",
    "grasp_actor",
    "move_by_displacement",
    "place_actor",
    "delay",
    "add_prohibit_area",
    "get_arm_pose",
    "back_to_origin",
    "is_left_gripper_open",
    "is_right_gripper_open",
    "get_gripper_actor_contact_position",
    "take_action",
}
INSTRUCTION_FUNCTIONS = {
    "load_task_instructions",
    "filter_instructions",
    "replace_placeholders",
    "replace_placeholders_unseen",
}
UTILITY_SYMBOLS = {
    "Actor",
    "ArmTag",
    "UnStableError",
    "create_actor",
    "create_box",
    "rand_pose",
}
CONTRACT_PATHS = (
    "envs/_base_task.py",
    "envs/_GLOBAL_CONFIGS.py",
    "envs/utils",
    "description/utils/generate_episode_instructions.py",
    "script/collect_data.py",
    "script/eval_policy.py",
    "script/eval_policy_client.py",
    "task_config/_eval_step_limit.yml",
)
REQUIRED_PATHS = CONTRACT_PATHS + (
    "envs",
    "description/task_instruction",
)
ALLOWED_DESTINATION_ROOTS = (Path("envs"), Path("description/task_instruction"))


class BridgeError(RuntimeError):
    pass


def desired_links(repo_root=REPO_ROOT):
    repo_root = Path(repo_root).resolve()
    links = []
    for task in MAINTAINED_TASKS:
        links.append((repo_root / "tasks/envs" / f"{task}.py", Path("envs") / f"{task}.py"))
    for helper in ENV_HELPERS:
        links.append((repo_root / "tasks/envs" / helper, Path("envs") / helper))
    for task in MAINTAINED_TASKS:
        links.append(
            (
                repo_root / "tasks/task_instruction" / f"{task}.json",
                Path("description/task_instruction") / f"{task}.json",
            )
        )
    return tuple(links)


def resolve_robotwin_dir(cli_value=None, environ=None, repo_root=REPO_ROOT):
    environ = os.environ if environ is None else environ
    value = cli_value or environ.get("ROBOTWIN_DIR")
    if value:
        return Path(value).expanduser().resolve()
    return (Path(repo_root) / "third_party/robotwin").resolve()


def git_revision(path):
    path = Path(path).resolve()
    try:
        root = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        ).stdout.strip()
        if Path(root).resolve() != path:
            return None
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    revision = result.stdout.strip()
    return revision or None


def git_paths_dirty(path, relative_paths):
    if git_revision(path) is None:
        return None
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(path),
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                *relative_paths,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return bool(result.stdout.strip())


def _parse(path):
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise BridgeError(f"cannot parse required RoboTwin API file {path}: {exc}") from exc


def _top_level_symbols(tree):
    symbols = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    symbols.add(target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name != "*":
                    symbols.add(alias.asname or alias.name.split(".")[0])
    return symbols


def _star_export_symbols(tree):
    symbols = _top_level_symbols(tree)
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
            continue
        value = node.value
        if not isinstance(value, (ast.List, ast.Tuple)):
            raise BridgeError("envs.utils __all__ must be a literal list or tuple")
        try:
            return {ast.literal_eval(item) for item in value.elts}
        except (ValueError, TypeError) as exc:
            raise BridgeError("envs.utils __all__ must contain only literal names") from exc
    return {name for name in symbols if not name.startswith("_")}


def _package_export_symbols(package_dir):
    init_tree = _parse(package_dir / "__init__.py")
    exports = _top_level_symbols(init_tree)
    for node in init_tree.body:
        if not isinstance(node, ast.ImportFrom) or node.level != 1 or not node.module:
            continue
        module_path = package_dir.joinpath(*node.module.split(".")).with_suffix(".py")
        if not module_path.is_file():
            raise BridgeError(f"cannot resolve envs.utils export module: {node.module}")
        if any(alias.name == "*" for alias in node.names):
            exports.update(_star_export_symbols(_parse(module_path)))
        else:
            exports.update(alias.asname or alias.name for alias in node.names)
    return exports


def _validate_injection_roots(target, require_present=True):
    for root in ALLOWED_DESTINATION_ROOTS:
        injection_root = target / root
        if not os.path.lexists(injection_root):
            if require_present:
                raise BridgeError(f"RoboTwin injection root is missing: {root}")
            continue
        if injection_root.is_symlink() or not injection_root.is_dir():
            raise BridgeError(f"RoboTwin injection root must be a real directory: {root}")
        if not _path_is_within(injection_root.resolve(), target):
            raise BridgeError(f"RoboTwin injection root escapes target: {root}")


def _enables_eval_mode(tree):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant) or node.value.value is not True:
            continue
        for target in node.targets:
            if not isinstance(target, ast.Subscript):
                continue
            if not isinstance(target.value, ast.Name) or target.value.id != "args":
                continue
            key = target.slice
            if isinstance(key, ast.Constant) and key.value == "eval_mode":
                return True
    return False


def check_compatibility(target, allow_compatible_commit=False):
    target = Path(target).resolve()
    missing_paths = [rel for rel in REQUIRED_PATHS if not (target / rel).exists()]
    if missing_paths:
        raise BridgeError(
            "incompatible RoboTwin layout; missing: " + ", ".join(missing_paths)
        )
    _validate_injection_roots(target)

    base_tree = _parse(target / "envs/_base_task.py")
    base_methods = set()
    for node in base_tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Base_Task":
            base_methods = {
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            break
    missing_methods = sorted(BASE_TASK_METHODS - base_methods)
    if missing_methods:
        raise BridgeError("incompatible Base_Task API; missing: " + ", ".join(missing_methods))

    instruction_symbols = _top_level_symbols(
        _parse(target / "description/utils/generate_episode_instructions.py")
    )
    missing_instruction = sorted(INSTRUCTION_FUNCTIONS - instruction_symbols)
    if missing_instruction:
        raise BridgeError(
            "incompatible instruction API; missing: " + ", ".join(missing_instruction)
        )

    utility_symbols = _package_export_symbols(target / "envs/utils")
    missing_utils = sorted(UTILITY_SYMBOLS - utility_symbols)
    if missing_utils:
        raise BridgeError("incompatible env utility API; missing: " + ", ".join(missing_utils))

    for relative_path in ("script/eval_policy.py", "script/eval_policy_client.py"):
        if not _enables_eval_mode(_parse(target / relative_path)):
            raise BridgeError(
                f"incompatible evaluator contract; {relative_path} does not enable eval_mode"
            )

    revision = git_revision(target)
    contract_dirty = git_paths_dirty(target, CONTRACT_PATHS)
    incompatibilities = []
    if revision != LOCKED_ROBOTWIN_COMMIT:
        actual = revision or "unknown (no readable git metadata)"
        incompatibilities.append(
            f"commit mismatch: expected {LOCKED_ROBOTWIN_COMMIT}, got {actual}"
        )
    if contract_dirty is None:
        incompatibilities.append("cannot determine compatibility contract worktree status")
    elif contract_dirty:
        incompatibilities.append("compatibility contract files have local changes")
    if incompatibilities and not allow_compatible_commit:
        raise BridgeError(
            "RoboTwin "
            + "; ".join(incompatibilities)
            + "; re-run with --allow-compatible-commit only after reviewing the compatible API contract"
        )
    override_used = bool(incompatibilities and allow_compatible_commit)
    return revision, contract_dirty, override_used


def _path_is_within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_destination(destination):
    if not isinstance(destination, str) or not destination:
        raise BridgeError("bridge state contains an invalid destination")
    rel = Path(destination)
    if rel.is_absolute() or ".." in rel.parts or "." in rel.parts:
        raise BridgeError(f"bridge state destination escapes target: {destination!r}")
    if not any(
        _path_is_within(rel, root) and len(rel.parts) == len(root.parts) + 1
        for root in ALLOWED_DESTINATION_ROOTS
    ):
        raise BridgeError(
            f"bridge state destination is not a direct child of an injection root: {destination!r}"
        )
    return rel


def _validate_source(source):
    if not isinstance(source, str) or not source:
        raise BridgeError("bridge state contains an invalid source")
    rel = Path(source)
    if rel.is_absolute() or ".." in rel.parts or "." in rel.parts:
        raise BridgeError(f"bridge state source escapes repository: {source!r}")
    if not (
        _path_is_within(rel, Path("tasks/envs"))
        or _path_is_within(rel, Path("tasks/task_instruction"))
    ):
        raise BridgeError(f"bridge state source is outside task roots: {source!r}")
    return rel


def load_state(target):
    state_path = Path(target) / STATE_NAME
    if not os.path.lexists(state_path):
        return None
    if state_path.is_symlink() or not state_path.is_file():
        raise BridgeError(f"bridge state is not a regular file: {state_path}")
    if state_path.stat().st_size > MAX_STATE_BYTES:
        raise BridgeError(
            f"bridge state exceeds the {MAX_STATE_BYTES}-byte safety limit: {state_path}"
        )
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BridgeError(f"cannot read bridge state {state_path}: {exc}") from exc
    if not isinstance(state, dict) or state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise BridgeError("unsupported or malformed bridge state schema")
    if state.get("target_root") != str(Path(target).resolve()):
        raise BridgeError("bridge state belongs to a different RoboTwin target")
    source_root_value = state.get("source_root")
    if not isinstance(source_root_value, str) or not Path(source_root_value).is_absolute():
        raise BridgeError("bridge state contains an invalid source root")
    source_root = Path(source_root_value)
    links = state.get("links")
    if not isinstance(links, list):
        raise BridgeError("bridge state links must be a list")
    if len(links) > MAX_STATE_LINKS:
        raise BridgeError(
            f"bridge state exceeds the {MAX_STATE_LINKS}-link safety limit"
        )
    seen = set()
    for item in links:
        if not isinstance(item, dict):
            raise BridgeError("bridge state contains a malformed link entry")
        source = _validate_source(item.get("source"))
        destination = _validate_destination(item.get("destination"))
        raw_target = item.get("target")
        if not isinstance(raw_target, str) or not raw_target:
            raise BridgeError(f"bridge state has an invalid symlink target for {destination}")
        resolved_target = Path(raw_target)
        if not resolved_target.is_absolute():
            resolved_target = (Path(target) / destination).parent / resolved_target
        if resolved_target.resolve(strict=False) != (source_root / source).resolve(strict=False):
            raise BridgeError(f"bridge state target does not match its source: {destination}")
        if str(destination) in seen:
            raise BridgeError(f"bridge state has duplicate destination: {destination}")
        seen.add(str(destination))
    return state


def _lexists(path):
    return os.path.lexists(str(path))


def _raw_target(path):
    return os.readlink(str(path))


def _unlink_owned_link(destination, expected_raw_target):
    if not destination.is_symlink() or _raw_target(destination) != expected_raw_target:
        raise BridgeError(f"owned destination changed during operation: {destination}")
    destination.unlink()


def _resolved_link(path):
    raw = _raw_target(path)
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = path.parent / candidate
    return candidate.resolve(strict=False)


def _expected_raw_target(source, destination):
    return os.path.relpath(str(source), str(destination.parent))


def _link_record(source, destination_rel, target, raw_target=None):
    return {
        "source": str(source.relative_to(REPO_ROOT)),
        "destination": str(destination_rel),
        "target": raw_target or _expected_raw_target(source, target / destination_rel),
    }


def _legacy_links(target, desired_destinations):
    candidates = []
    roots = (
        (REPO_ROOT / "tasks/envs", target / "envs", "*.py"),
        (
            REPO_ROOT / "tasks/task_instruction",
            target / "description/task_instruction",
            "*.json",
        ),
    )
    for source_dir, destination_dir, pattern in roots:
        if not source_dir.is_dir() or not destination_dir.is_dir():
            continue
        for source in source_dir.glob(pattern):
            destination = destination_dir / source.name
            if destination in desired_destinations:
                continue
            if destination.is_symlink() and _resolved_link(destination) == source.resolve():
                candidates.append((destination, _raw_target(destination), source))
    return candidates


def _atomic_write_json(path, data):
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _source_digest(source_paths):
    digest = hashlib.sha256()
    for relative_path in sorted(source_paths):
        payload = (REPO_ROOT / relative_path).read_bytes()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _build_state(
    target,
    target_revision,
    target_contract_dirty,
    allow_compatible_commit,
    records,
):
    source_paths = tuple(record["source"] for record in records)
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "source_root": str(REPO_ROOT),
        "source_commit": git_revision(REPO_ROOT),
        "source_dirty": git_paths_dirty(REPO_ROOT, source_paths),
        "source_digest": _source_digest(source_paths),
        "target_root": str(target),
        "target_commit": target_revision,
        "target_contract_dirty": target_contract_dirty,
        "allow_compatible_commit": bool(allow_compatible_commit),
        "links": records,
    }


def _state_matches(state, expected):
    return state == expected


@contextmanager
def _operation_lock(target):
    try:
        directory_fd = os.open(target, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as exc:
        raise BridgeError(f"cannot open RoboTwin target for locking {target}: {exc}") from exc
    try:
        try:
            fcntl.flock(directory_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BridgeError(f"another bridge operation is active for {target}") from exc
        yield
    finally:
        try:
            fcntl.flock(directory_fd, fcntl.LOCK_UN)
        finally:
            os.close(directory_fd)


def bridge(target, dry_run=False, check=False, allow_compatible_commit=False):
    target = Path(target).resolve()
    if not target.is_dir():
        raise BridgeError(f"RoboTwin target is not a directory: {target}")
    with _operation_lock(target):
        return _bridge(target, dry_run, check, allow_compatible_commit)


def _bridge(target, dry_run=False, check=False, allow_compatible_commit=False):
    target_revision, target_contract_dirty, override_used = check_compatibility(
        target, allow_compatible_commit
    )
    state = load_state(target)
    if state is not None and state.get("source_root") != str(REPO_ROOT):
        raise BridgeError(
            f"target is owned by a different robotwin-if checkout: {state.get('source_root')}"
        )

    desired = desired_links()
    for source, _ in desired:
        if not source.is_file():
            raise BridgeError(f"required bridge source is missing: {source}")

    desired_by_destination = {str(rel): (source, rel) for source, rel in desired}
    desired_absolute = {target / rel for _, rel in desired}

    actions = []
    collisions = []
    create = []
    raw_targets = {}
    for source, rel in desired:
        destination = target / rel
        raw_targets[str(rel)] = _expected_raw_target(source, destination)
        if destination.is_symlink():
            if _resolved_link(destination) == source.resolve():
                raw_targets[str(rel)] = _raw_target(destination)
                status = "ok" if state and str(rel) in {
                    item["destination"] for item in state["links"]
                } else "adopt"
                actions.append((status, rel))
            else:
                kind = "dangling symlink" if not destination.exists() else "foreign symlink"
                collisions.append((rel, kind))
        elif _lexists(destination):
            kind = "directory" if destination.is_dir() else "regular file"
            collisions.append((rel, kind))
        else:
            raw_targets[str(rel)] = _expected_raw_target(source, destination)
            create.append((source, destination, rel))
            actions.append(("add", rel))

    records = [
        _link_record(source, rel, target, raw_targets[str(rel)])
        for source, rel in desired
    ]
    expected_state = _build_state(
        target,
        target_revision,
        target_contract_dirty,
        override_used,
        records,
    )

    stale = []
    if state:
        for item in state["links"]:
            rel_text = item["destination"]
            if rel_text in desired_by_destination:
                continue
            rel = _validate_destination(rel_text)
            destination = target / rel
            if not _lexists(destination):
                actions.append(("remove-stale", rel))
                continue
            if destination.is_symlink() and _raw_target(destination) == item["target"]:
                stale.append((destination, item["target"], rel))
                actions.append(("remove-stale", rel))
            else:
                collisions.append((rel, "modified owned destination"))

    stale_destinations = {destination for destination, _raw, _rel in stale}
    legacy = _legacy_links(target, desired_absolute)
    for destination, raw, _source in legacy:
        if destination in stale_destinations:
            continue
        rel = destination.relative_to(target)
        stale.append((destination, raw, rel))
        stale_destinations.add(destination)
        actions.append(("remove-stale", rel))

    if collisions:
        for rel, kind in collisions:
            print(f"collision       {rel} ({kind})", file=sys.stderr)
        raise BridgeError("bridge preflight failed; target was not modified")

    if check:
        wrong = False
        if create or stale:
            wrong = True
        for status, rel in actions:
            print(f"{status:<15} {rel}")
            if status != "ok":
                wrong = True
        if state is None:
            print(f"missing-state   {STATE_NAME}", file=sys.stderr)
            wrong = True
        elif not _state_matches(state, expected_state):
            print(f"state-mismatch  {STATE_NAME}", file=sys.stderr)
            wrong = True
        if wrong:
            raise BridgeError("bridge check failed: installation is incomplete or stale")
        print(f"check passed: {len(records)} owned links")
        return

    for status, rel in actions:
        print(f"{status:<15} {rel}")
    if dry_run:
        print(f"dry-run: add={len(create)} remove-stale={len(stale)} owned={len(records)}")
        return

    created = []
    removed = []
    try:
        for source, destination, _rel in create:
            raw = _expected_raw_target(source, destination)
            destination.symlink_to(raw)
            created.append((destination, raw))
        for destination, raw, _rel in stale:
            _unlink_owned_link(destination, raw)
            removed.append((destination, raw))
        _atomic_write_json(target / STATE_NAME, expected_state)
    except Exception as exc:
        for destination, raw in reversed(created):
            if destination.is_symlink() and _raw_target(destination) == raw:
                destination.unlink()
        for destination, raw in reversed(removed):
            if not _lexists(destination):
                destination.symlink_to(raw)
        raise BridgeError(f"bridge failed and link changes were rolled back: {exc}") from exc
    print(f"bridge complete: add={len(create)} remove-stale={len(removed)} owned={len(records)}")


def _legacy_unbridge(target, dry_run):
    links = _legacy_links(target, set())
    for destination, _raw, _source in links:
        print(f"remove          {destination.relative_to(target)}")
    if dry_run:
        print(f"dry-run: remove={len(links)} (legacy fallback; no ownership state)")
        return
    removed = []
    try:
        for destination, raw, _source in links:
            _unlink_owned_link(destination, raw)
            removed.append((destination, raw))
    except Exception as exc:
        for destination, raw in reversed(removed):
            if not _lexists(destination):
                destination.symlink_to(raw)
        raise BridgeError(
            f"legacy unbridge failed and link changes were rolled back: {exc}"
        ) from exc
    print(
        f"unbridge complete: removed={len(links)}; warning: no ownership state, "
        "historical links whose sources were deleted cannot be discovered"
    )


def unbridge(target, dry_run=False):
    target = Path(target).resolve()
    if not target.exists():
        print(f"RoboTwin directory does not exist: {target}; nothing to unbridge")
        return
    if not target.is_dir():
        raise BridgeError(f"RoboTwin target is not a directory: {target}")
    with _operation_lock(target):
        return _unbridge(target, dry_run)


def _unbridge(target, dry_run=False):
    _validate_injection_roots(target, require_present=False)
    state = load_state(target)
    if state is None:
        _legacy_unbridge(target, dry_run)
        return

    safe = []
    retained = []
    for item in state["links"]:
        rel = _validate_destination(item["destination"])
        destination = target / rel
        if not _lexists(destination):
            print(f"ok-missing      {rel}")
        elif destination.is_symlink() and _raw_target(destination) == item["target"]:
            print(f"remove          {rel}")
            safe.append((destination, item["target"]))
        else:
            print(f"skip-modified   {rel}", file=sys.stderr)
            retained.append(item)

    if dry_run:
        print(f"dry-run: remove={len(safe)} skip-modified={len(retained)}")
        if retained:
            raise BridgeError("unbridge would skip modified destinations")
        return

    removed = []
    try:
        for destination, raw in safe:
            _unlink_owned_link(destination, raw)
            removed.append((destination, raw))
        state_path = target / STATE_NAME
        if retained:
            new_state = dict(state)
            new_state["links"] = retained
            _atomic_write_json(state_path, new_state)
        else:
            state_path.unlink()
    except Exception as exc:
        for destination, raw in reversed(removed):
            if not _lexists(destination):
                destination.symlink_to(raw)
        raise BridgeError(f"unbridge failed and link changes were rolled back: {exc}") from exc

    print(f"unbridge complete: removed={len(removed)} skip-modified={len(retained)}")
    if retained:
        raise BridgeError("unbridge incomplete: modified destinations remain owned")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    bridge_parser = subparsers.add_parser("bridge", help="install maintained task plugins")
    bridge_parser.add_argument("--robotwin-dir")
    modes = bridge_parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--check", action="store_true")
    bridge_parser.add_argument("--allow-compatible-commit", action="store_true")

    unbridge_parser = subparsers.add_parser("unbridge", help="remove owned task plugins")
    unbridge_parser.add_argument("--robotwin-dir")
    unbridge_parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    target = resolve_robotwin_dir(args.robotwin_dir)
    try:
        if args.command == "bridge":
            bridge(
                target,
                dry_run=args.dry_run,
                check=args.check,
                allow_compatible_commit=args.allow_compatible_commit,
            )
        else:
            unbridge(target, dry_run=args.dry_run)
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
