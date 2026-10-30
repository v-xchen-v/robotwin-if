"""The frozen delivery is standalone and its scores agree with its exact seeds."""
import csv
import hashlib
import json
from pathlib import Path
import unittest
from tools.verify_benchmark import verify

ROOT = Path(__file__).resolve().parents[1]


class CurrentReleaseTest(unittest.TestCase):
    def test_delivery_is_self_consistent_without_git_history(self):
        self.assertEqual(verify(ROOT), dict(tasks=6, policies=6, episodes=2760, blocks=720))

    def test_one_seed_set_and_one_result_set_are_exposed(self):
        self.assertEqual([p.name for p in (ROOT / 'seed-manifests').iterdir() if p.is_dir()], ['20-blocks'])
        self.assertEqual([p.name for p in (ROOT / 'result').iterdir() if p.is_dir()], ['checkpoint-evidence'])

    def test_stapler_paired_scores_agree_with_episode_labels(self):
        with (ROOT / 'result/episodes.csv').open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        summary = json.loads((ROOT / 'result/stapler-summary.json').read_text())
        for policy, stats in summary.items():
            selected = [r for r in rows if r['policy'] == policy and r['task'] == 'press_lift_stapler']
            for mode in ('press', 'lift'):
                self.assertEqual(stats[mode+'_successes'], sum(int(r['success']) for r in selected if r['mode'] == mode))
            both = sum(all(int(r['success']) for r in selected if int(r['block_index']) == b) for b in range(20))
            self.assertEqual(stats['both_success_blocks'], both)

    def test_demos_have_current_size_and_matching_export_hashes(self):
        demo = ROOT / 'docs/assets/demos'
        sources = json.loads((demo / 'sources.json').read_text())
        self.assertEqual(len(sources['tasks']), 6)
        self.assertEqual([r['seed'] for r in sources['tasks']['attribute_select']['panels']], [100174, 100175])
        for task in sources['tasks'].values():
            for filename, spec in task['exports'].items():
                self.assertEqual(hashlib.sha256((demo / filename).read_bytes()).hexdigest(), spec['sha256'])


if __name__ == '__main__':
    unittest.main()
