#!/usr/bin/env python3
"""Static contract tests for maintained IF policy-action budgets."""

import ast
import importlib.util
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[1]
TASKS = (
    "bottle_verb",
    "pick_diverse_object",
    "attribute_select",
    "arm_select",
    "stack_sequence",
    "place_relative",
    "grasp_cube_approach",
)
EXPECTED = {
    "bottle_verb": 700,
    "pick_diverse_object": 400,
    "attribute_select": 400,
    "arm_select": 400,
    "stack_sequence": 1200,
    "place_relative": 400,
    "grasp_cube_approach": 400,
}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_helper():
    return load_module("if_eval", REPO / "tasks/envs/_if_eval.py")


def load_bridge():
    return load_module("task_bridge", REPO / "scripts/_task_bridge.py")


def task_tree(task):
    path = REPO / "tasks/envs" / f"{task}.py"
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def setup_demo_definition(tree):
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == "setup_demo":
                return child
    return None


def direct_call(statement):
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return None
    func = statement.value.func
    if isinstance(func, ast.Attribute):
        return func.attr, statement.value
    if isinstance(func, ast.Name):
        return func.id, statement.value
    return None


class EvalStepLimitTests(unittest.TestCase):
    def test_task_inventory_matches_bridge(self):
        self.assertEqual(TASKS, load_bridge().MAINTAINED_TASKS)
        self.assertEqual(set(EXPECTED), set(TASKS))

    def test_fixed_eval_limit_map_is_exact(self):
        self.assertEqual(load_helper().IF_EVAL_STEP_LIMITS, EXPECTED)

    def test_collect_mode_is_unchanged(self):
        helper = load_helper()

        class Dummy:
            task_name = "stack_sequence"
            eval_mode = False
            step_lim = 17

        dummy = Dummy()
        helper.apply_if_eval_step_limit(dummy)
        self.assertEqual(dummy.step_lim, 17)

    def test_eval_mode_receives_fixed_limit(self):
        helper = load_helper()

        class Dummy:
            task_name = "stack_sequence"
            eval_mode = True
            step_lim = 17

        dummy = Dummy()
        helper.apply_if_eval_step_limit(dummy)
        self.assertEqual(dummy.step_lim, 1200)


def make_import_test(task):
    def test(self):
        tree = task_tree(task)
        imports_helper = any(
            isinstance(node, ast.ImportFrom)
            and node.level == 1
            and node.module == "_if_eval"
            and any(alias.name == "apply_if_eval_step_limit" for alias in node.names)
            for node in tree.body
        )
        self.assertTrue(imports_helper)

    return test


def make_wiring_test(task):
    def test(self):
        definition = setup_demo_definition(task_tree(task))
        self.assertIsNotNone(definition)
        calls = []
        for index, statement in enumerate(definition.body):
            call = direct_call(statement)
            if call is not None:
                calls.append((index, *call))

        init_calls = [item for item in calls if item[1] == "_init_task_env_"]
        helper_calls = [item for item in calls if item[1] == "apply_if_eval_step_limit"]
        self.assertEqual(len(init_calls), 1)
        self.assertEqual(len(helper_calls), 1)
        init_index, _init_name, _init_call = init_calls[0]
        helper_index, _helper_name, helper_call = helper_calls[0]
        self.assertGreater(helper_index, init_index)

        unsafe_control_flow = (
            ast.Return,
            ast.If,
            ast.For,
            ast.AsyncFor,
            ast.While,
            ast.Try,
            ast.With,
            ast.AsyncWith,
            ast.Match,
            ast.Raise,
        )
        self.assertFalse(
            any(isinstance(statement, unsafe_control_flow) for statement in definition.body[:helper_index])
        )
        self.assertEqual(len(helper_call.args), 1)
        self.assertIsInstance(helper_call.args[0], ast.Name)
        self.assertEqual(helper_call.args[0].id, "self")
        self.assertFalse(helper_call.keywords)

    return test


for _task in TASKS:
    setattr(
        EvalStepLimitTests,
        f"test_{_task}_imports_eval_helper",
        make_import_test(_task),
    )
    setattr(
        EvalStepLimitTests,
        f"test_{_task}_helper_follows_task_initialization",
        make_wiring_test(_task),
    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
