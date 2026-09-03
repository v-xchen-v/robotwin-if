#!/usr/bin/env python3
"""Simulator-free tests for IF seed generator and validator CLIs."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from if_benchmark.seed_generation import (  # noqa: E402
    GenerationError,
    generation_summary,
    new_generation_state,
    run_generation,
    write_generation_state,
)
from if_benchmark.seed_manifest import manifest_sha256, write_manifest  # noqa: E402
from tools import generate_if_seed_manifest as generator  # noqa: E402
from tools import validate_if_seed_manifest as validator  # noqa: E402


class FakeArmTask:
    def __init__(self, close_error=False):
        self.close_error = close_error
        self.closed = 0

    def setup_demo(self, **kwargs):
        self.mode = ("left", "right")[kwargs["seed"] % 2]

    def play_once(self):
        self.plan_success = True

    def check_success(self):
        return True

    def close_env(self):
        self.closed += 1
        if self.close_error:
            raise RuntimeError("cannot close")


class SeedCliTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.manifest = {
            "schema_version": 1,
            "task": "arm_select",
            "task_config": "demo_clean",
            "seeds": [100000, 100001],
        }

    def tearDown(self):
        self.tempdir.cleanup()

    def evidence(self):
        state = new_generation_state(
            task="arm_select",
            task_config="demo_clean",
            accepted_blocks=1,
            max_candidate_blocks=1,
            candidate_floor=100000,
            provenance={
                "generator": {
                    "name": "tools/generate_if_seed_manifest.py",
                    "version": 1,
                    "generation_schema_version": 1,
                    "manifest_schema_version": 1,
                },
                "target_root": "/tmp/robotwin",
                "target_commit": "abc",
                "target_contract_dirty": False,
                "source_root": "/tmp/robotwin-if",
                "source_commit": "def",
                "source_dirty": True,
                "source_digest": "a" * 64,
                "bridge_allow_compatible_commit": False,
                "task_config_path": "task_config/demo_clean.yml",
                "task_config_sha256": "b" * 64,
            },
        )

        def probe(seed):
            return {
                "setup_ok": True,
                "plan_success": True,
                "check_success": True,
                "observed_mode": ("left", "right")[seed % 2],
            }

        state = run_generation(state, probe)
        state["manifest_sha256"] = manifest_sha256(self.manifest)
        state["summary"] = generation_summary(state)
        return state

    def test_validator_accepts_flat_manifest_without_evidence(self):
        path = self.root / "arm_select.json"
        write_manifest(path, self.manifest)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            status = validator.main([str(path)])
        self.assertEqual(status, 0)
        self.assertIn("left=1, right=1", stdout.getvalue())
        self.assertIn("evidence=not present", stdout.getvalue())

    def test_validator_requires_and_verifies_generation_evidence(self):
        path = self.root / "arm_select.json"
        evidence_path = self.root / "arm_select.generation.json"
        write_manifest(path, self.manifest)

        with redirect_stderr(io.StringIO()):
            self.assertEqual(validator.main(["--require-evidence", str(path)]), 1)

        write_generation_state(evidence_path, self.evidence())
        with redirect_stdout(io.StringIO()):
            self.assertEqual(validator.main(["--require-evidence", str(path)]), 0)

    def test_validator_directory_rejects_orphan_generation_evidence(self):
        evidence_path = self.root / "arm_select.generation.json"
        write_generation_state(evidence_path, self.evidence())
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            status = validator.main([str(self.root)])
        self.assertEqual(status, 1)
        self.assertIn("no adjacent manifest", stderr.getvalue())

    def test_validator_rejects_sidecar_hash_mismatch_when_present(self):
        path = self.root / "arm_select.json"
        evidence_path = self.root / "arm_select.generation.json"
        write_manifest(path, self.manifest)
        evidence = self.evidence()
        evidence["manifest_sha256"] = "0" * 64
        write_generation_state(evidence_path, evidence)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            status = validator.main([str(path)])
        self.assertEqual(status, 1)
        self.assertIn("SHA-256 mismatch", stderr.getvalue())

    def test_generator_probe_closes_each_exact_episode(self):
        task = FakeArmTask()
        first = generator._probe_seed("arm_select", task, {}, 100000)
        second = generator._probe_seed("arm_select", task, {}, 100001)
        self.assertEqual(first["observed_mode"], "left")
        self.assertEqual(second["observed_mode"], "right")
        self.assertTrue(first["check_success"])
        self.assertEqual(task.closed, 2)

    def test_generator_probe_records_close_failure(self):
        task = FakeArmTask(close_error=True)
        result = generator._probe_seed("arm_select", task, {}, 100000)
        self.assertEqual(result["failure"]["category"], "close")

    def test_task_config_identity_hashes_exact_yaml_and_rejects_paths(self):
        config_dir = self.root / "task_config"
        config_dir.mkdir()
        config = config_dir / "demo_clean.yml"
        config.write_text("episode_num: 2\n", encoding="utf-8")
        identity = generator._task_config_identity(self.root, "demo_clean")
        self.assertEqual(identity["task_config_path"], "task_config/demo_clean.yml")
        self.assertEqual(len(identity["task_config_sha256"]), 64)
        with self.assertRaisesRegex(GenerationError, "basename"):
            generator._task_config_identity(self.root, "../demo_clean")

    def test_resume_allows_not_yet_started_tasks_but_not_orphan_manifest(self):
        generator._preflight_outputs(
            self.root,
            ("arm_select", "bottle_verb"),
            resume=True,
            overwrite=False,
        )
        write_manifest(self.root / "arm_select.json", self.manifest)
        with self.assertRaisesRegex(GenerationError, "without resume evidence"):
            generator._preflight_outputs(
                self.root,
                ("arm_select", "bottle_verb"),
                resume=True,
                overwrite=False,
            )

    def test_observed_mode_adapters_use_initialized_environment_state(self):
        cases = (
            ("pick_diverse_object", SimpleNamespace(target_familiarity="unseen"), "unseen"),
            (
                "attribute_select",
                SimpleNamespace(
                    axis="decal",
                    value=1,
                    AXIS_VALUES={"decal": ("cat", "dog")},
                ),
                "decal:dog",
            ),
            (
                "stack_sequence",
                SimpleNamespace(
                    COLOR_NAMES=("red", "green", "blue"),
                    perm=(2, 0, 1),
                ),
                "blue>red>green",
            ),
            ("place_relative", SimpleNamespace(direction="front"), "front"),
        )
        for task_name, task, expected in cases:
            with self.subTest(task=task_name):
                self.assertEqual(generator._observed_mode(task_name, task), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
