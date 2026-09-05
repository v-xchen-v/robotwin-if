#!/usr/bin/env python3
"""Static contract tests for the maintained task manifests.

This test does not import task envs or start the simulator. It locks the native-50
prefix, the canonical IF-seven suffix, and each maintained task's discovery files.

    python tests/test_task_manifests.py
"""
import ast
import importlib.util
import json
from pathlib import Path
import sys

import yaml


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from if_benchmark.seed_contracts import IF_SEED_CONTRACTS  # noqa: E402


NATIVE_TASKS = (
    "adjust_bottle",
    "beat_block_hammer",
    "blocks_ranking_rgb",
    "blocks_ranking_size",
    "click_alarmclock",
    "click_bell",
    "dump_bin_bigbin",
    "grab_roller",
    "handover_block",
    "handover_mic",
    "hanging_mug",
    "lift_pot",
    "move_can_pot",
    "move_pillbottle_pad",
    "move_playingcard_away",
    "move_stapler_pad",
    "open_laptop",
    "open_microwave",
    "pick_diverse_bottles",
    "pick_dual_bottles",
    "place_a2b_left",
    "place_a2b_right",
    "place_bread_basket",
    "place_bread_skillet",
    "place_burger_fries",
    "place_can_basket",
    "place_cans_plasticbox",
    "place_container_plate",
    "place_dual_shoes",
    "place_empty_cup",
    "place_fan",
    "place_mouse_pad",
    "place_object_basket",
    "place_object_scale",
    "place_object_stand",
    "place_phone_stand",
    "place_shoe",
    "press_stapler",
    "put_bottles_dustbin",
    "put_object_cabinet",
    "rotate_qrcode",
    "scan_object",
    "shake_bottle",
    "shake_bottle_horizontally",
    "stack_blocks_three",
    "stack_blocks_two",
    "stack_bowls_three",
    "stack_bowls_two",
    "stamp_seal",
    "turn_switch",
)

IF_TASKS = (
    "bottle_verb",
    "pick_diverse_object",
    "attribute_select",
    "arm_select",
    "stack_sequence",
    "place_relative",
    "grasp_cube_approach",
)

INACTIVE_TASKS = {
    "laptop_verb",
    "operate_stapler",
    "operate_tabletop",
    "operate_mic_drawer",
    "smoke_click_bell",
}

BRIDGE_HELPERS = (
    "_if_grounding.py",
    "_if_relative.py",
    "_pick_diverse_object_pool.py",
    "_if_eval.py",
)

_results = []


def check(name, ok, note=""):
    _results.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {note}")


def load_tasks(path):
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    check(f"{path.name}: top-level mapping", isinstance(data, dict))
    tasks = data.get("tasks") if isinstance(data, dict) else None
    check(f"{path.name}: tasks is a list", isinstance(tasks, list))
    return tasks if isinstance(tasks, list) else []


def main():
    if_manifest = REPO / "eval_cfg" / "if_tasks.yml"
    merged_manifest = REPO / "eval_cfg" / "all_tasks_plus_if.yml"

    if_tasks = load_tasks(if_manifest)
    merged_tasks = load_tasks(merged_manifest)

    check(
        "if_tasks.yml is the exact maintained IF-seven inventory",
        tuple(if_tasks) == IF_TASKS,
        note=f"got={if_tasks}",
    )
    check(
        "if_tasks.yml has seven unique entries",
        len(if_tasks) == 7 and len(set(if_tasks)) == 7,
        note=f"count={len(if_tasks)}, unique={len(set(if_tasks))}",
    )
    check(
        "seed-contract inventory equals canonical IF-seven",
        tuple(IF_SEED_CONTRACTS) == IF_TASKS,
        note=f"got={tuple(IF_SEED_CONTRACTS)}",
    )
    check(
        "seed-contract balance block sizes are exact",
        tuple(contract.block_size for contract in IF_SEED_CONTRACTS.values())
        == (2, 2, 8, 2, 6, 5, 2),
    )
    check(
        "all_tasks_plus_if.yml is exact native-50 + IF-seven",
        tuple(merged_tasks) == NATIVE_TASKS + IF_TASKS,
        note=f"count={len(merged_tasks)}",
    )
    check(
        "merged manifest has 57 unique entries",
        len(merged_tasks) == 57 and len(set(merged_tasks)) == 57,
        note=f"count={len(merged_tasks)}, unique={len(set(merged_tasks))}",
    )
    check(
        "native and IF inventories are disjoint",
        set(NATIVE_TASKS).isdisjoint(IF_TASKS),
    )

    active = set(if_tasks) | set(merged_tasks)
    leaked = sorted(active & INACTIVE_TASKS)
    check(
        "inactive retained tasks are absent from active manifests",
        not leaked,
        note=f"leaked={leaked}",
    )

    bridge_path = REPO / "scripts" / "_task_bridge.py"
    spec = importlib.util.spec_from_file_location("task_bridge_contract", bridge_path)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    check(
        "bridge task inventory equals canonical IF-seven",
        bridge.MAINTAINED_TASKS == IF_TASKS,
        note=f"got={bridge.MAINTAINED_TASKS}",
    )
    check(
        "bridge helper inventory is exact",
        bridge.ENV_HELPERS == BRIDGE_HELPERS,
        note=f"got={bridge.ENV_HELPERS}",
    )
    desired = bridge.desired_links()
    desired_env_tasks = tuple(
        source.stem
        for source, destination in desired
        if destination.parent == Path("envs") and source.name not in BRIDGE_HELPERS
    )
    desired_instructions = tuple(
        source.stem
        for source, destination in desired
        if destination.parent == Path("description/task_instruction")
    )
    check("bridge env task order is canonical", desired_env_tasks == IF_TASKS)
    check("bridge instruction order is canonical", desired_instructions == IF_TASKS)
    check("bridge owns exactly 18 task plugin links", len(desired) == 18)

    for helper in BRIDGE_HELPERS:
        check(f"bridge helper exists: {helper}", (REPO / "tasks/envs" / helper).is_file())

    for task in IF_TASKS:
        env_path = REPO / "tasks" / "envs" / f"{task}.py"
        instruction_path = REPO / "tasks" / "task_instruction" / f"{task}.json"

        check(f"{task}: env file exists", env_path.is_file())
        if env_path.is_file():
            try:
                tree = ast.parse(env_path.read_text(encoding="utf-8"), filename=str(env_path))
                top_level_classes = {
                    node.name for node in tree.body if isinstance(node, ast.ClassDef)
                }
                check(
                    f"{task}: top-level class matches task name",
                    task in top_level_classes,
                    note=f"classes={sorted(top_level_classes)}",
                )
            except (OSError, SyntaxError) as exc:
                check(f"{task}: env parses", False, note=str(exc))

        check(f"{task}: instruction JSON exists", instruction_path.is_file())
        if instruction_path.is_file():
            try:
                with instruction_path.open(encoding="utf-8") as f:
                    instructions = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                check(f"{task}: instruction JSON parses", False, note=str(exc))
                continue

            for pool_name in ("seen", "unseen"):
                pool = instructions.get(pool_name)
                check(
                    f"{task}: {pool_name} instruction pool is nonempty",
                    isinstance(pool, list) and bool(pool),
                    note=f"count={len(pool) if isinstance(pool, list) else 'not-a-list'}",
                )

    print(f"\n==== {sum(_results)}/{len(_results)} passed ====")
    return 0 if _results and all(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
