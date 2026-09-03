#!/usr/bin/env python3
"""Simulator-free tests for complete-block seed generation."""

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from if_benchmark.seed_contracts import describe_seed  # noqa: E402
from if_benchmark.seed_generation import (  # noqa: E402
    GenerationError,
    accepted_seeds,
    generation_summary,
    load_generation_state,
    new_generation_state,
    run_generation,
    validate_generation_evidence,
    validate_generation_state,
    validate_resume_state,
    write_generation_state,
)
from if_benchmark.seed_manifest import manifest_sha256  # noqa: E402


class SeedGenerationTests(unittest.TestCase):
    def state(self, **overrides):
        values = {
            "task": "arm_select",
            "task_config": "demo_clean",
            "accepted_blocks": 2,
            "max_candidate_blocks": 4,
            "candidate_floor": 100000,
            "provenance": {"target_commit": "abc", "source_digest": "def"},
        }
        values.update(overrides)
        return new_generation_state(**values)

    @staticmethod
    def passing(task="arm_select"):
        def probe(seed):
            return {
                "setup_ok": True,
                "plan_success": True,
                "check_success": True,
                "observed_mode": describe_seed(task, seed).mode,
            }
        return probe

    def test_all_pass_accepts_exact_seeds_once(self):
        calls = []
        probe = self.passing()

        def tracked(seed):
            calls.append(seed)
            return probe(seed)

        state = run_generation(self.state(), tracked)
        self.assertEqual(state["status"], "complete")
        self.assertEqual(accepted_seeds(state), (100000, 100001, 100002, 100003))
        self.assertEqual(calls, [100000, 100001, 100002, 100003])

    def test_one_failed_member_rejects_whole_block_without_substitution(self):
        calls = []

        def probe(seed):
            calls.append(seed)
            row = self.passing()(seed)
            if seed == 100001:
                row["check_success"] = False
            return row

        state = run_generation(self.state(), probe)
        self.assertFalse(state["blocks"][0]["accepted"])
        self.assertEqual(state["blocks"][0]["seeds"], [100000, 100001])
        self.assertEqual(accepted_seeds(state), (100002, 100003, 100004, 100005))
        self.assertEqual(calls, list(range(100000, 100006)))

    def test_mode_mismatch_rejects_block(self):
        def probe(seed):
            row = self.passing()(seed)
            if seed == 100000:
                row["observed_mode"] = "right"
            return row

        state = run_generation(self.state(accepted_blocks=1), probe)
        first = state["blocks"][0]
        self.assertFalse(first["accepted"])
        self.assertEqual(first["episodes"][0]["failure"]["category"], "mode_mismatch")
        self.assertEqual(accepted_seeds(state), (100002, 100003))

    def test_probe_exception_is_recorded_and_exhaustion_is_nonzero(self):
        def probe(seed):
            if seed % 2 == 0:
                raise RuntimeError("boom")
            return self.passing()(seed)

        state = self.state(accepted_blocks=1, max_candidate_blocks=2)
        with self.assertRaisesRegex(GenerationError, "accepted 0/1"):
            run_generation(state, probe)
        self.assertEqual(state["status"], "exhausted")
        self.assertEqual(
            state["blocks"][0]["episodes"][0]["failure"]["category"],
            "probe",
        )

    def test_checkpoint_runs_after_each_block_and_completion(self):
        snapshots = []
        state = run_generation(
            self.state(accepted_blocks=1),
            self.passing(),
            checkpoint=lambda value: snapshots.append(deepcopy(value)),
        )
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0]["status"], "running")
        self.assertEqual(snapshots[1]["status"], "complete")
        self.assertEqual(state, snapshots[-1])

    def test_resume_requires_exact_parameters_and_provenance(self):
        expected = self.state()
        running = deepcopy(expected)
        validate_resume_state(running, expected)

        changed = self.state(provenance={"target_commit": "other", "source_digest": "def"})
        with self.assertRaisesRegex(GenerationError, "provenance"):
            validate_resume_state(running, changed)

        changed = self.state(candidate_floor=200000)
        with self.assertRaisesRegex(GenerationError, "parameters"):
            validate_resume_state(running, changed)

    def test_stack_candidate_floor_aligns_up_to_complete_block(self):
        state = self.state(
            task="stack_sequence",
            accepted_blocks=1,
            max_candidate_blocks=1,
        )
        state = run_generation(state, self.passing("stack_sequence"))
        self.assertEqual(accepted_seeds(state), tuple(range(100002, 100008)))

    def test_explicit_probe_failure_rejects_otherwise_passing_episode(self):
        def probe(seed):
            row = self.passing()(seed)
            if seed == 100000:
                row["failure"] = {"category": "close", "message": "close failed"}
            return row

        state = run_generation(self.state(accepted_blocks=1), probe)
        self.assertFalse(state["blocks"][0]["accepted"])
        self.assertEqual(
            state["blocks"][0]["episodes"][0]["failure"]["category"],
            "close",
        )
        self.assertEqual(accepted_seeds(state), (100002, 100003))

    def test_checkpoint_structure_tampering_is_rejected(self):
        state = run_generation(self.state(accepted_blocks=1), self.passing())
        changed = deepcopy(state)
        changed["blocks"][0]["episodes"][0]["expected_mode"] = "right"
        with self.assertRaisesRegex(GenerationError, "expected mode"):
            validate_generation_state(changed)

        changed = deepcopy(state)
        changed["blocks"][0]["accepted"] = False
        with self.assertRaisesRegex(GenerationError, "block acceptance"):
            validate_generation_state(changed)

    def test_generation_evidence_round_trip_and_manifest_binding(self):
        state = run_generation(
            self.state(
                accepted_blocks=1,
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
            ),
            self.passing(),
        )
        manifest = {
            "schema_version": 1,
            "task": "arm_select",
            "task_config": "demo_clean",
            "seeds": list(accepted_seeds(state)),
        }
        state["manifest_sha256"] = manifest_sha256(manifest)
        state["summary"] = generation_summary(state)

        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "arm_select.generation.json"
            write_generation_state(path, state)
            loaded = load_generation_state(path)
            validate_generation_evidence(manifest, loaded)

            wrong = dict(manifest, seeds=[100002, 100003])
            with self.assertRaisesRegex(GenerationError, "accepted seeds"):
                validate_generation_evidence(wrong, loaded)

            malformed = deepcopy(loaded)
            malformed["provenance"]["source_digest"] = "not-a-digest"
            with self.assertRaisesRegex(GenerationError, "source_digest"):
                validate_generation_evidence(manifest, malformed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
