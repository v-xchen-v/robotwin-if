"""Complete-block collection and manifest routing without a simulator."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest

from if_benchmark.seed_contracts import describe_seed
from if_benchmark.seed_manifest import write_manifest
from tools import collect_if_expert as collect


class CollectionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def args(self, *extra):
        return collect.build_parser().parse_args(["--output-dir", str(self.root / "output"), *extra])

    def manifest(self, task="press_lift_stapler", seeds=(0, 1, 4, 5), config="demo_clean"):
        path = self.root / f"{task}.json"
        write_manifest(path, dict(schema_version=2, task=task, task_config=config, seeds=list(seeds)))
        return str(path)

    def test_defaults_cover_all_modes_and_current_arm_config(self):
        args = self.args()
        specs = collect.collection_specs(args)
        self.assertEqual(args.blocks, 1)
        self.assertEqual(len(specs), 6)
        seeds = {s["task"]: next(collect.candidates(s))[1] for s in specs}
        self.assertEqual(sum(map(len, seeds.values())), 23)
        self.assertEqual(seeds["place_relative"], (0, 1, 4))
        self.assertEqual(specs[3]["task_config"], "demo_clean_arm_select_v3")

    def test_manifest_infers_task_config_and_preserves_gaps(self):
        path = self.manifest("place_relative", (10, 11, 14, 25, 26, 29))
        spec, = collect.collection_specs(self.args("--seed-manifest", path))
        self.assertEqual(list(collect.candidates(spec)), [(2, (10, 11, 14)), (5, (25, 26, 29))])
        arm = self.manifest("arm_select", (500000, 500001), "demo_clean_arm_select_v3")
        specs = collect.collection_specs(self.args("--seed-manifest", path, "--seed-manifest", arm))
        self.assertEqual(specs[1]["task_config"], "demo_clean_arm_select_v3")

    def test_invalid_manifest_requests_fail_before_collection(self):
        path = self.manifest()
        for extra in (("--task", "arm_select"), ("--task", "all"),
                      ("--blocks", "3"), ("--start-seed", "5"),
                      ("--task-config", "demo_randomized")):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                collect.collection_specs(self.args("--seed-manifest", path, *extra))
        old = self.manifest("bottle_verb")
        with self.assertRaisesRegex(ValueError, "retired"):
            collect.collection_specs(self.args("--seed-manifest", old))

    def run_fake(self, args, fail_at):
        args.output_dir.mkdir()
        spec, = collect.collection_specs(args)
        report = dict(task=spec["task"], requested_blocks=args.blocks, accepted_blocks=0,
                      attempted_blocks=0, rejected_blocks=0, complete=False, blocks=[])
        calls = []
        failure_type = collect.ExpertFailure
        def episode(seed, directory, *, collect):
            calls.append((seed, collect))
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "marker.txt").write_text("partial data")
            if (seed, collect) in fail_at:
                raise failure_type("failed test scene")
            return dict(seed=seed, mode=describe_seed(spec["task"], seed).mode,
                        instruction="Press <the> stapler & wait. \U0001f3ac")
        with redirect_stdout(io.StringIO()):
            collect.collect_task(spec, args, report, episode,
                                 lambda: collect.write_review(args.output_dir, [report]))
        return report, calls

    def test_plan_failure_discards_whole_pair_and_retries_until_two_blocks(self):
        args = self.args("--task", "press_lift_stapler", "--blocks", "2")
        report, calls = self.run_fake(args, {(1, False)})
        self.assertTrue(report["complete"])
        self.assertEqual(report["attempted_blocks"], 3)
        self.assertEqual([b["seeds"] for b in report["blocks"]], [[2, 3], [4, 5]])
        self.assertNotIn((0, True), calls)
        self.assertEqual(list(args.output_dir.rglob(".candidate-*")), [])
        page = (args.output_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn("Press &lt;the&gt; stapler &amp; wait.", page)
        self.assertIn("press_lift_stapler/block_000/00_press/video/episode0.mp4", page)

    def test_replay_failure_uses_next_manifest_block_without_mixing_modes(self):
        path = self.manifest()
        args = self.args("--seed-manifest", path)
        report, calls = self.run_fake(args, {(1, True)})
        self.assertTrue(report["complete"])
        self.assertEqual(report["blocks"][0]["seeds"], [4, 5])
        self.assertEqual([s for s, record in calls if record], [0, 1, 4, 5])
        rejected = json.loads((args.output_dir / "press_lift_stapler/rejected.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(rejected["stage"], "collect")
        self.assertEqual(rejected["failed_seed"], 1)

    def test_manifest_exhaustion_never_falls_back_to_unlisted_seeds(self):
        args = self.args("--seed-manifest", self.manifest(seeds=(0, 1)))
        report, calls = self.run_fake(args, {(1, False)})
        self.assertFalse(report["complete"])
        self.assertEqual(report["accepted_blocks"], 0)
        self.assertEqual(calls, [(0, False), (1, False)])
        self.assertIn("exhausted", report["error"])

    def test_optional_attempt_limit_reports_incomplete(self):
        args = self.args("--task", "press_lift_stapler", "--max-candidate-blocks", "1")
        report, _ = self.run_fake(args, {(0, False)})
        self.assertFalse(report["complete"])
        self.assertEqual(report["attempted_blocks"], 1)

    def test_data_write_error_is_fatal_instead_of_retrying_forever(self):
        args = self.args("--task", "press_lift_stapler")
        args.output_dir.mkdir()
        spec, = collect.collection_specs(args)
        report = dict(attempted_blocks=0)
        def broken_writer(seed, directory, *, collect):
            raise OSError("disk full")
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(OSError, "disk full"):
            collect.collect_task(spec, args, report, broken_writer, lambda: None)
        self.assertEqual(report["attempted_blocks"], 1)

    def test_dry_run_does_not_create_output_or_load_simulator(self):
        output = self.root / "dry"
        with redirect_stdout(io.StringIO()):
            status = collect.main(["--output-dir", str(output), "--dry-run"])
        self.assertEqual(status, 0)
        self.assertFalse(output.exists())
        output.mkdir()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(collect.main(["--output-dir", str(output), "--dry-run"]), 2)


if __name__ == "__main__":
    unittest.main()
