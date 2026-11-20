"""Scores use exact manifest seeds and complete blocks from the public evaluator."""
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from if_benchmark.seed_modes import build_seed_modes
from tools import summarize_formal_policy_results as report


class ResultScopeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.manifests = report.ROOT / 'seed-manifests/20-blocks'

    def fixture(self, blocks=1):
        for task in build_seed_modes(self.manifests)['tasks']:
            name = task['task']
            directory = self.base / 'vlact' / name
            directory.mkdir(parents=True)
            rows = []
            for r in task['episodes']:
                if r['block'] >= blocks:
                    continue
                success = name != 'press_lift_stapler'
                row = dict(task=name, seed=r['seed'], mode=r['mode'], success=success,
                           status='success' if success else 'failure', oracle_success=True)
                (directory / f'{name}_ep{r["seed"]}_result.json').write_text(json.dumps(row))
                rows.append(row)
            (directory / 'results.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))

    def test_public_evaluator_layout_needs_no_plan_or_history(self):
        self.fixture()
        data = report.snapshot(self.base, self.manifests, 1)
        self.assertEqual(data['summary']['completed_episodes'], 23)
        self.assertEqual(data['summary']['completed_blocks'], 6)
        self.assertAlmostEqual(data['policies']['vlact']['overall_pct'], 500/6)
        report.generate(data, self.base/'report.md')
        self.assertIn('Verb Stapler', (self.base/'report.md').read_text())
        self.assertIn('6 个 Task Avg.', (self.base/'report.md').read_text())

    def test_frozen_individual_records_match_jsonl_scores(self):
        self.fixture()
        original = report.snapshot(self.base, self.manifests, 1)
        for path in self.base.rglob('results.jsonl'):
            path.unlink()
        frozen = report.snapshot(self.base, self.manifests, 1)
        self.assertEqual(original['rows'], frozen['rows'])
        self.assertEqual(original['policies'], frozen['policies'])

    def test_full_expanded_run_scores_all_200_blocks_with_existing_rules(self):
        self.manifests = report.ROOT / 'seed-manifests/200-blocks'
        self.fixture(blocks=200)
        data = report.snapshot(self.base, self.manifests, 200)
        self.assertEqual(data['summary'], dict(completed_episodes=4600, expected_episodes=4600,
            completed_blocks=1200, expected_blocks=1200, complete_task_policy_runs=6))
        self.assertAlmostEqual(data['policies']['vlact']['overall_pct'], 500/6)
        for row, task in zip(data['rows'], build_seed_modes(self.manifests)['tasks']):
            self.assertTrue(row['complete'])
            self.assertEqual(row['included_seeds'], [r['seed'] for r in task['episodes']])
            self.assertEqual(row['complete_block_ids'], list(range(200)))
            self.assertEqual(row['partial_group_episodes'], 0)
            expected_successes = 0 if row['task'] == 'press_lift_stapler' else 200
            for mode in row['modes'].values():
                self.assertEqual((mode['included'], mode['successes']), (200, expected_successes))
        output = self.base / 'report with spaces.md'
        report.generate(data, output)
        refresh = output.read_text().split('```bash\n')[1].split('\n```')[0]
        self.assertEqual(shlex.split(refresh), ['python', 'tools/summarize_formal_policy_results.py',
            '--run-dir', str(self.base), '--manifest-dir', str(self.manifests),
            '--blocks', '200', '--output', str(output)])
        # A smaller plan must still reject extra records, never silently filter them.
        for blocks in (50, 100):
            with self.assertRaisesRegex(ValueError, 'unplanned seed'):
                report.snapshot(self.base, self.manifests, blocks)

    def test_plan_must_fit_the_selected_suite(self):
        for capacity in (20, 200):
            manifests = report.ROOT / f'seed-manifests/{capacity}-blocks'
            for blocks in (0, capacity + 1, True):
                with self.subTest(capacity=capacity, blocks=blocks):
                    with self.assertRaisesRegex(ValueError, f'blocks must be 1..{capacity}'):
                        report.snapshot(self.base, manifests, blocks)

    def test_partial_block_is_progress_but_never_score_or_overall(self):
        self.fixture()
        path = self.base/'vlact/place_relative/results.jsonl'
        rows = path.read_text().splitlines()
        path.write_text('\n'.join(rows[:-1])+'\n')
        data = report.snapshot(self.base, self.manifests, 1)
        self.assertIsNone(data['policies']['vlact']['overall_pct'])
        spatial = next(r for r in data['rows'] if r['task'] == 'place_relative')
        self.assertEqual((spatial['recorded_episodes'], spatial['included_episodes']), (2, 0))

    def test_duplicates_unplanned_seeds_and_tampered_records_rejected(self):
        self.fixture()
        index = self.base/'vlact/press_lift_stapler/results.jsonl'
        original = index.read_text()
        index.write_text(original+original.splitlines()[0]+'\n')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            report.snapshot(self.base, self.manifests, 1)
        index.write_text(original)
        path = next(index.parent.glob('*_result.json'))
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'differs from results.jsonl'):
            report.snapshot(self.base, self.manifests, 1)


if __name__ == '__main__':
    unittest.main()
