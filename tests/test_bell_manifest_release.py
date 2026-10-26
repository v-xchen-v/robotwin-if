"""Frozen bell release, legacy compatibility, and exact-seed CLI selection."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from if_benchmark.seed_contracts import CURRENT_SUITE_TASKS
from tools.release_press_lift_bell_v1 import PARENT, RELEASE, verify
from policies.xvla.eval import select_seeds
from tasks.envs._press_lift_bell import INSTRUCTIONS


class BellManifestReleaseTest(unittest.TestCase):
    def test_release_qualification_checksums_and_unchanged_five_manifests(self):
        suite = verify()
        self.assertEqual(suite['episodes_per_policy'], 460)
        bell = suite['tasks'][0]
        self.assertEqual(bell['instructions'], INSTRUCTIONS)
        self.assertEqual(bell['instruction_override']['previous_instructions']['lift'], 'Pick up the bell.')
        for task in CURRENT_SUITE_TASKS[1:]:
            self.assertEqual((RELEASE / f'{task}.json').read_bytes(), (PARENT / f'{task}.json').read_bytes())
        self.assertTrue((PARENT / 'bottle_verb.json').exists())
        self.assertFalse((RELEASE / 'bottle_verb.json').exists())

    def test_bell_contract_selects_complete_prefix_for_all_policy_entrypoints(self):
        args = SimpleNamespace(task='press_lift_bell', task_config='demo_clean',
            seed_manifest=RELEASE / 'press_lift_bell.json', blocks=20, instruction_type=None)
        expected = json.loads(args.seed_manifest.read_text())['seeds']
        for policy in ('xvla', 'lingbot_va', 'lingbot_vla', 'vlact', 'dm05', 'hy_vla'):
            module = importlib.import_module(f'policies.{policy}.eval')
            with self.subTest(policy=policy):
                seeds, manifest, split = module.select_seeds(args)
                self.assertEqual(seeds, expected)
                self.assertEqual(split, 'unseen')
        args.blocks = 1
        self.assertEqual(select_seeds(args)[0], expected[:2])
        args.blocks = 21
        with self.assertRaises(ValueError):
            select_seeds(args)


if __name__ == '__main__':
    unittest.main()
