"""The stapler release replaces the verb task and preserves the other five seeds."""
import importlib
import json
from types import SimpleNamespace
import unittest

from if_benchmark.seed_contracts import CURRENT_SUITE_TASKS
from tools.release_press_lift_stapler_v1 import PARENT, RELEASE, verify
from tools.run_formal_policy_suite import current_success_checker


class StaplerManifestReleaseTest(unittest.TestCase):
    def test_qualified_release_and_unchanged_five_manifests(self):
        suite = verify()
        self.assertEqual(suite['episodes_per_policy'], 460)
        self.assertEqual([t['task'] for t in suite['tasks']], list(CURRENT_SUITE_TASKS))
        self.assertNotIn('bottle_verb', CURRENT_SUITE_TASKS)
        self.assertNotIn('press_lift_bell', CURRENT_SUITE_TASKS)
        for task in CURRENT_SUITE_TASKS[1:]:
            self.assertEqual((RELEASE / f'{task}.json').read_bytes(), (PARENT / f'{task}.json').read_bytes())
        spec = suite['tasks'][0]
        for key, expected in current_success_checker('press_lift_stapler').items():
            self.assertEqual(spec[key], expected)
        self.assertEqual(spec['rotation_sampling_version'], 'random-yaw-v1')

    def test_every_policy_uses_exact_complete_prefix(self):
        args = SimpleNamespace(task='press_lift_stapler', task_config='demo_clean',
            seed_manifest=RELEASE / 'press_lift_stapler.json', blocks=20, instruction_type=None)
        expected = json.loads(args.seed_manifest.read_text())['seeds']
        self.assertEqual(len(expected), 40)
        self.assertGreaterEqual(min(expected), 110000)
        for policy in ('xvla', 'lingbot_va', 'lingbot_vla', 'vlact', 'dm05', 'hy_vla'):
            module = importlib.import_module(f'policies.{policy}.eval')
            with self.subTest(policy=policy):
                args.blocks = 20
                seeds, manifest, split = module.select_seeds(args)
                self.assertEqual(seeds, expected)
                self.assertEqual(split, 'unseen')
                args.blocks = 1
                self.assertEqual(module.select_seeds(args)[0], expected[:2])
                args.blocks = 21
                with self.assertRaises(ValueError):
                    module.select_seeds(args)


if __name__ == '__main__':
    unittest.main()
