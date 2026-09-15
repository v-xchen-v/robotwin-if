"""Six-task scores and explicit historical scope have independent denominators."""
import json
from pathlib import Path
import tempfile
import unittest

from if_benchmark.seed_contracts import contract_for, describe_seed, expand_block
from tools import summarize_formal_policy_results as report


class ResultScopeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)

    def fixture(self, historical=True, incomplete_grasp=False):
        tasks = list(report.TASKS) + (list(report.ARCHIVED_TASKS) if historical else [])
        specs = [dict(task=t, seeds=list(expand_block(t, 0, legacy=historical))) for t in tasks]
        rows = []
        for policy in report.POLICIES:
            for spec in specs:
                task = spec['task']
                pending = spec['seeds'][-1:] if task in report.ARCHIVED_TASKS and incomplete_grasp else []
                modes = {}
                for seed in spec['seeds']:
                    mode = describe_seed(task, seed).mode
                    success = task != 'bottle_verb'  # Equal task weighting differs from pooled episodes.
                    modes[mode] = dict(recorded=int(seed not in pending), successes=int(success and seed not in pending))
                    if seed in pending:
                        continue
                    pre = self.base / policy / task / f'{task}_ep{seed}'
                    pre.parent.mkdir(parents=True, exist_ok=True)
                    result = dict(task=task, seed=seed, mode=mode, success=success,
                                  status='success' if success else 'failure', oracle_success=True)
                    path = Path(str(pre) + '_result.json')
                    path.write_text(json.dumps(result))
                    marker = dict(policy=policy, task=task, seed=seed, mode=mode, success=success,
                                  formal_block=0, files_sha256={path.name: report.hashlib.sha256(path.read_bytes()).hexdigest()})
                    Path(str(pre) + '_provenance.json').write_text(json.dumps(marker))
                rows.append(dict(policy=policy, task=task, pending_seeds=pending, per_mode=modes,
                                 completed_blocks=int(not pending), recorded_episodes=len(spec['seeds'])-len(pending),
                                 complete=not pending, successes=sum(m['successes'] for m in modes.values())))
        source = dict(tasks=rows, updated_at='fixture', completed_episodes=sum(r['recorded_episodes'] for r in rows),
                      successes=sum(r['successes'] for r in rows), completed_blocks=sum(r['completed_blocks'] for r in rows))
        (self.base / 'summary.json').write_text(json.dumps(source))
        (self.base / 'plan.json').write_text(json.dumps(dict(policies=list(report.POLICIES), tasks=specs)))

    def test_six_task_projection_and_explicit_seven_task_average(self):
        self.fixture()
        current = report.snapshot(self.base)
        legacy = report.snapshot(self.base, include_archived_tasks=True, include_archived_modes=True)
        self.assertEqual(current['summary']['expected_episodes'], 138)
        self.assertEqual(legacy['summary']['expected_episodes'], 162)
        self.assertEqual(current['summary']['expected_blocks'], 36)
        self.assertEqual(legacy['summary']['expected_blocks'], 42)
        self.assertAlmostEqual(current['policies']['xvla']['overall_pct'], 500/6)
        self.assertAlmostEqual(legacy['policies']['xvla']['overall_pct'], 600/7)
        self.assertEqual(current['source_summary'], legacy['source_summary'])
        report.generate(current, self.base / 'current.md')
        text = (self.base / 'current.md').read_text()
        self.assertIn('138/138', text)
        self.assertIn('36/36', text)
        self.assertIn('6 个 Task Avg.', text)
        self.assertNotIn('Grasp v2', (self.base / 'current.html').read_text())

    def test_incomplete_retired_task_does_not_hide_completed_current_overall(self):
        self.fixture(incomplete_grasp=True)
        self.assertIsNotNone(report.snapshot(self.base)['policies']['xvla']['overall_pct'])
        self.assertIsNone(report.snapshot(self.base, True)['policies']['xvla']['overall_pct'])

    def test_native_six_task_plan_is_supported(self):
        self.fixture(historical=False)
        data = report.snapshot(self.base)
        self.assertEqual(data['tasks'], list(report.TASKS))
        self.assertEqual(data['excluded_tasks'], [])


if __name__ == '__main__':
    unittest.main()
