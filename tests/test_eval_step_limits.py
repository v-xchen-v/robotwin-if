#!/usr/bin/env python3
"""Static contract tests for maintained IF policy-action budgets."""

import ast
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from if_benchmark.seed_contracts import CURRENT_SUITE_TASKS

# These six implementations use the shared helper. Press/lift tasks set their
# own budget after native initialization and are checked separately below.
TASKS = (
    "bottle_verb",
    "pick_diverse_object",
    "attribute_select",
    "arm_select",
    "stack_sequence",
    "place_relative",
)
EXPECTED = {
    "bottle_verb": 700,
    "pick_diverse_object": 400,
    "attribute_select": 400,
    "arm_select": 400,
    "stack_sequence": 1200,
    "place_relative": 400,
}
PRESS_LIFT_LIMITS = {"press_lift_stapler": 250, "press_lift_bell": 250}


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
    def test_current_inventory_and_compatibility_tasks_match_bridge(self):
        self.assertEqual(set(load_bridge().MAINTAINED_TASKS),
                         set(CURRENT_SUITE_TASKS) | {"bottle_verb", "press_lift_bell"})
        self.assertEqual(set(EXPECTED), set(TASKS))
        self.assertEqual(set(EXPECTED) | set(PRESS_LIFT_LIMITS),
                         set(load_bridge().MAINTAINED_TASKS))

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

    def test_press_lift_budgets_override_native_default_only_in_eval(self):
        for task, limit in PRESS_LIFT_LIMITS.items():
            with self.subTest(task=task):
                tree = task_tree(task)
                cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
                declared = next(n.value for n in cls.body if isinstance(n, ast.Assign)
                                and any(isinstance(t, ast.Name) and t.id == 'ACTION_LIMIT' for t in n.targets))
                self.assertEqual(ast.literal_eval(declared), limit)
                setup = setup_demo_definition(tree)
                init_index = next(i for i, n in enumerate(setup.body)
                                  if direct_call(n) and direct_call(n)[0] == '_init_task_env_')
                index, guard = next((i, n) for i, n in enumerate(setup.body)
                                    if isinstance(n, ast.If) and isinstance(n.test, ast.Attribute)
                                    and isinstance(n.test.value, ast.Name) and n.test.value.id == 'self'
                                    and n.test.attr == 'eval_mode')
                self.assertGreater(index, init_index)
                # Execute the actual budget guard with the native fallback in
                # place; collect must keep it, while eval must replace it.
                code = compile(ast.Module(body=[guard], type_ignores=[]), '<budget>', 'exec')
                for eval_mode in (False, True):
                    env = SimpleNamespace(eval_mode=eval_mode, ACTION_LIMIT=limit, step_lim=1000)
                    exec(code, {'self': env})
                    self.assertEqual(env.step_lim, limit if eval_mode else 1000)


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
        # Config validation may branch before initialization. Once initialization
        # succeeds, no control flow may bypass the policy step-limit helper.
        self.assertFalse(
            any(isinstance(statement, unsafe_control_flow)
                for statement in definition.body[init_index + 1:helper_index])
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
