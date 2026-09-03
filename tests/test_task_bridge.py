#!/usr/bin/env python3
"""Simulator-free integration tests for the task bridge ownership protocol."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
REAL_ROBOTWIN = REPO / "third_party/robotwin"
SPEC = importlib.util.spec_from_file_location("task_bridge", REPO / "scripts/_task_bridge.py")
BRIDGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BRIDGE)


class TaskBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def fake_robotwin(self):
        target = self.root / "robotwin"
        files = (
            "envs/_base_task.py",
            "envs/_GLOBAL_CONFIGS.py",
            "description/utils/generate_episode_instructions.py",
            "script/collect_data.py",
            "script/eval_policy.py",
            "script/eval_policy_client.py",
            "task_config/_eval_step_limit.yml",
        )
        for rel in files:
            destination = target / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REAL_ROBOTWIN / rel, destination)
        shutil.copytree(REAL_ROBOTWIN / "envs/utils", target / "envs/utils")
        (target / "description/task_instruction").mkdir(parents=True)
        return target

    def quiet_bridge(self, target, **kwargs):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return BRIDGE.bridge(target, allow_compatible_commit=True, **kwargs)

    def quiet_unbridge(self, target, **kwargs):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return BRIDGE.unbridge(target, **kwargs)

    def assert_no_install(self, target, except_rel=None):
        for _source, rel in BRIDGE.desired_links():
            if rel == except_rel:
                continue
            self.assertFalse(os.path.lexists(target / rel), rel)
        self.assertFalse((target / BRIDGE.STATE_NAME).exists())

    def test_target_resolution_precedence_and_cli_validation(self):
        env_target = self.root / "from-env"
        cli_target = self.root / "from-cli"
        self.assertEqual(
            BRIDGE.resolve_robotwin_dir(str(cli_target), {"ROBOTWIN_DIR": str(env_target)}),
            cli_target.resolve(),
        )
        self.assertEqual(
            BRIDGE.resolve_robotwin_dir(None, {"ROBOTWIN_DIR": str(env_target)}),
            env_target.resolve(),
        )
        self.assertEqual(
            BRIDGE.resolve_robotwin_dir(None, {}, self.root),
            (self.root / "third_party/robotwin").resolve(),
        )
        with self.assertRaises(SystemExit):
            BRIDGE.build_parser().parse_args(["bridge", "--dry-run", "--check"])

    def test_real_locked_checkout_passes_exact_commit_dry_run(self):
        state_path = REAL_ROBOTWIN / BRIDGE.STATE_NAME
        before = state_path.read_bytes() if state_path.exists() else None
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            BRIDGE.bridge(REAL_ROBOTWIN, dry_run=True)
        after = state_path.read_bytes() if state_path.exists() else None
        self.assertEqual(after, before)

    def test_commit_mismatch_requires_explicit_compatible_override(self):
        target = self.fake_robotwin()
        with self.assertRaisesRegex(BRIDGE.BridgeError, "commit mismatch"):
            BRIDGE.bridge(target, dry_run=True)
        self.quiet_bridge(target, dry_run=True)
        self.assert_no_install(target)

    def test_dirty_target_contract_requires_explicit_override(self):
        target = self.fake_robotwin()
        with mock.patch.object(
            BRIDGE, "git_revision", return_value=BRIDGE.LOCKED_ROBOTWIN_COMMIT
        ), mock.patch.object(BRIDGE, "git_paths_dirty", return_value=True):
            with self.assertRaisesRegex(BRIDGE.BridgeError, "local changes"):
                BRIDGE.bridge(target, dry_run=True)
            self.quiet_bridge(target, dry_run=True)
        self.assert_no_install(target)

    def test_unknown_target_status_requires_explicit_override(self):
        target = self.fake_robotwin()
        with mock.patch.object(
            BRIDGE, "git_revision", return_value=BRIDGE.LOCKED_ROBOTWIN_COMMIT
        ), mock.patch.object(BRIDGE, "git_paths_dirty", return_value=None):
            with self.assertRaisesRegex(BRIDGE.BridgeError, "cannot determine"):
                BRIDGE.bridge(target, dry_run=True)
            self.quiet_bridge(target, dry_run=True)
        self.assert_no_install(target)

    def test_unused_compatible_override_does_not_make_check_flag_sensitive(self):
        target = self.fake_robotwin()
        with mock.patch.object(
            BRIDGE, "git_revision", return_value=BRIDGE.LOCKED_ROBOTWIN_COMMIT
        ), mock.patch.object(BRIDGE, "git_paths_dirty", return_value=False):
            self.quiet_bridge(target)
            state = json.loads((target / BRIDGE.STATE_NAME).read_text(encoding="utf-8"))
            self.assertFalse(state["allow_compatible_commit"])
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                BRIDGE.bridge(target, check=True)

    def test_git_revision_rejects_enclosing_repository_identity(self):
        self.assertIsNone(BRIDGE.git_revision(REPO / "tasks"))

    def test_missing_base_task_api_is_rejected(self):
        target = self.fake_robotwin()
        base = target / "envs/_base_task.py"
        text = base.read_text(encoding="utf-8")
        base.write_text(text.replace("    def take_action(", "    def removed_take_action("), encoding="utf-8")
        with self.assertRaisesRegex(BRIDGE.BridgeError, "take_action"):
            self.quiet_bridge(target, dry_run=True)
        self.assert_no_install(target)

    def test_evaluator_must_enable_eval_mode(self):
        target = self.fake_robotwin()
        client = target / "script/eval_policy_client.py"
        text = client.read_text(encoding="utf-8")
        client.write_text(
            text.replace('args["eval_mode"] = True', 'args["eval_mode"] = False'),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(BRIDGE.BridgeError, "eval_policy_client.py"):
            self.quiet_bridge(target, dry_run=True)
        self.assert_no_install(target)

    def test_unexported_utility_symbol_is_rejected(self):
        target = self.fake_robotwin()
        init = target / "envs/utils/__init__.py"
        text = init.read_text(encoding="utf-8")
        init.write_text(text.replace("from .action import *\n", ""), encoding="utf-8")
        with self.assertRaisesRegex(BRIDGE.BridgeError, "ArmTag"):
            self.quiet_bridge(target, dry_run=True)
        self.assert_no_install(target)

    def test_dry_run_does_not_write_links_or_state(self):
        target = self.fake_robotwin()
        before = set(target.iterdir())
        self.quiet_bridge(target, dry_run=True)
        self.assert_no_install(target)
        self.assertEqual(set(target.iterdir()), before)

    def test_concurrent_operation_is_rejected(self):
        target = self.fake_robotwin()
        with BRIDGE._operation_lock(target):
            with self.assertRaisesRegex(BRIDGE.BridgeError, "another bridge operation"):
                self.quiet_bridge(target, dry_run=True)
        self.assert_no_install(target)

    def test_collision_preflight_is_all_or_nothing(self):
        cases = ("regular", "directory", "foreign", "dangling")
        for case in cases:
            with self.subTest(case=case):
                target = self.fake_robotwin()
                _source, rel = BRIDGE.desired_links()[5]
                destination = target / rel
                if case == "regular":
                    destination.write_text("foreign\n", encoding="utf-8")
                elif case == "directory":
                    destination.mkdir()
                elif case == "foreign":
                    foreign = self.root / f"foreign-{case}.py"
                    foreign.write_text("foreign\n", encoding="utf-8")
                    destination.symlink_to(foreign)
                else:
                    destination.symlink_to(self.root / "does-not-exist.py")
                with self.assertRaisesRegex(BRIDGE.BridgeError, "preflight"):
                    self.quiet_bridge(target)
                self.assert_no_install(target, except_rel=rel)
                shutil.rmtree(target)

    def test_install_manifest_idempotence_and_check(self):
        target = self.fake_robotwin()
        self.quiet_bridge(target)
        state = json.loads((target / BRIDGE.STATE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(state["schema_version"], BRIDGE.STATE_SCHEMA_VERSION)
        self.assertEqual(state["source_root"], str(REPO))
        self.assertEqual(state["source_commit"], BRIDGE.git_revision(REPO))
        self.assertIsInstance(state["source_dirty"], bool)
        self.assertRegex(state["source_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(state["target_root"], str(target.resolve()))
        self.assertIsNone(state["target_commit"])
        self.assertIsNone(state["target_contract_dirty"])
        self.assertTrue(state["allow_compatible_commit"])
        self.assertEqual(len(state["links"]), len(BRIDGE.desired_links()))
        for source, rel in BRIDGE.desired_links():
            destination = target / rel
            self.assertTrue(destination.is_symlink(), rel)
            self.assertEqual(destination.resolve(), source.resolve())
        self.quiet_bridge(target)
        self.quiet_bridge(target, check=True)

    def test_adopts_correct_link_and_removes_inactive_legacy_link(self):
        target = self.fake_robotwin()
        source, rel = BRIDGE.desired_links()[0]
        destination = target / rel
        destination.symlink_to(os.path.relpath(source, destination.parent))
        inactive_source = REPO / "tasks/envs/laptop_verb.py"
        inactive_destination = target / "envs/laptop_verb.py"
        inactive_destination.symlink_to(os.path.relpath(inactive_source, inactive_destination.parent))
        self.quiet_bridge(target)
        self.assertTrue(destination.is_symlink())
        self.assertFalse(os.path.lexists(inactive_destination))
        self.quiet_bridge(target, check=True)

    def test_adopted_absolute_link_remains_unbridgeable(self):
        target = self.fake_robotwin()
        source, rel = BRIDGE.desired_links()[0]
        destination = target / rel
        destination.symlink_to(source)
        self.quiet_bridge(target)
        state = json.loads((target / BRIDGE.STATE_NAME).read_text(encoding="utf-8"))
        record = next(item for item in state["links"] if item["destination"] == str(rel))
        self.assertEqual(record["target"], str(source))
        self.quiet_unbridge(target)
        self.assertFalse(os.path.lexists(destination))

    def test_symlinked_injection_root_is_rejected(self):
        target = self.fake_robotwin()
        external_envs = self.root / "external-envs"
        (target / "envs").rename(external_envs)
        (target / "envs").symlink_to(external_envs, target_is_directory=True)
        with self.assertRaisesRegex(BRIDGE.BridgeError, "injection root"):
            self.quiet_bridge(target)
        for _source, rel in BRIDGE.desired_links():
            self.assertFalse(os.path.lexists(target / rel), rel)
        self.assertFalse((target / BRIDGE.STATE_NAME).exists())

    def test_unbridge_rejects_replaced_symlinked_injection_root(self):
        target = self.fake_robotwin()
        self.quiet_bridge(target)
        external_envs = self.root / "external-envs"
        (target / "envs").rename(external_envs)
        (target / "envs").symlink_to(external_envs, target_is_directory=True)
        owned_link = external_envs / "bottle_verb.py"
        with self.assertRaisesRegex(BRIDGE.BridgeError, "injection root"):
            self.quiet_unbridge(target)
        self.assertTrue(owned_link.is_symlink())
        self.assertTrue((target / BRIDGE.STATE_NAME).is_file())

    def test_manifest_backed_stale_link_is_removed(self):
        target = self.fake_robotwin()
        self.quiet_bridge(target)
        state_path = target / BRIDGE.STATE_NAME
        state = json.loads(state_path.read_text(encoding="utf-8"))
        source = REPO / "tasks/envs/laptop_verb.py"
        destination = target / "envs/laptop_verb.py"
        raw = os.path.relpath(source, destination.parent)
        destination.symlink_to(raw)
        state["links"].append(
            {
                "source": "tasks/envs/laptop_verb.py",
                "destination": "envs/laptop_verb.py",
                "target": raw,
            }
        )
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.quiet_bridge(target)
        self.assertFalse(os.path.lexists(destination))
        self.quiet_bridge(target, check=True)

    def test_unbridge_missing_target_is_idempotent(self):
        missing = self.root / "missing-robotwin"
        self.quiet_unbridge(missing)
        self.assertFalse(missing.exists())

    def test_unbridge_uses_manifest_when_source_is_deleted(self):
        target = self.fake_robotwin()
        self.quiet_bridge(target)
        state_path = target / BRIDGE.STATE_NAME
        state = json.loads(state_path.read_text(encoding="utf-8"))
        item = state["links"][0]
        destination = target / item["destination"]
        destination.unlink()
        item["source"] = "tasks/envs/deleted_task.py"
        item["target"] = os.path.relpath(REPO / item["source"], destination.parent)
        destination.symlink_to(item["target"])
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.quiet_unbridge(target)
        self.assertFalse(os.path.lexists(destination))
        self.assertFalse(state_path.exists())

    def test_unbridge_never_removes_modified_destination(self):
        target = self.fake_robotwin()
        self.quiet_bridge(target)
        state_path = target / BRIDGE.STATE_NAME
        state = json.loads(state_path.read_text(encoding="utf-8"))
        item = state["links"][0]
        destination = target / item["destination"]
        destination.unlink()
        foreign = self.root / "foreign.py"
        foreign.write_text("foreign\n", encoding="utf-8")
        destination.symlink_to(foreign)
        with self.assertRaisesRegex(BRIDGE.BridgeError, "incomplete"):
            self.quiet_unbridge(target)
        self.assertTrue(destination.is_symlink())
        self.assertEqual(destination.resolve(), foreign.resolve())
        retained = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(retained["links"], [item])

    def test_unlink_revalidates_raw_target_at_mutation(self):
        source = self.root / "source.py"
        foreign = self.root / "foreign.py"
        source.write_text("source\n", encoding="utf-8")
        foreign.write_text("foreign\n", encoding="utf-8")
        destination = self.root / "owned.py"
        destination.symlink_to(foreign)
        with self.assertRaisesRegex(BRIDGE.BridgeError, "changed during operation"):
            BRIDGE._unlink_owned_link(destination, str(source))
        self.assertTrue(destination.is_symlink())
        self.assertEqual(destination.resolve(), foreign.resolve())

    def test_corrupt_and_traversing_state_is_rejected(self):
        target = self.fake_robotwin()
        state_path = target / BRIDGE.STATE_NAME
        state_path.symlink_to(self.root / "missing-state.json")
        with self.assertRaisesRegex(BRIDGE.BridgeError, "not a regular file"):
            self.quiet_unbridge(target)
        state_path.unlink()

        state_path.write_text("not json", encoding="utf-8")
        with self.assertRaises(BRIDGE.BridgeError):
            self.quiet_unbridge(target)

        state_path.write_bytes(b" " * (BRIDGE.MAX_STATE_BYTES + 1))
        with self.assertRaisesRegex(BRIDGE.BridgeError, "safety limit"):
            self.quiet_unbridge(target)

        victim = self.root / "victim"
        victim.write_text("keep\n", encoding="utf-8")
        state = {
            "schema_version": BRIDGE.STATE_SCHEMA_VERSION,
            "source_root": str(REPO),
            "target_root": str(target.resolve()),
            "links": [
                {
                    "source": "tasks/envs/bottle_verb.py",
                    "destination": "../victim",
                    "target": str(REPO / "tasks/envs/bottle_verb.py"),
                }
            ],
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaisesRegex(BRIDGE.BridgeError, "escapes"):
            self.quiet_unbridge(target)
        self.assertEqual(victim.read_text(encoding="utf-8"), "keep\n")

        state["links"][0]["destination"] = "envs/nested/victim.py"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaisesRegex(BRIDGE.BridgeError, "direct child"):
            self.quiet_unbridge(target)
        self.assertEqual(victim.read_text(encoding="utf-8"), "keep\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
