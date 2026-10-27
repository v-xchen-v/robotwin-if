"""The stapler release replaces the verb task and preserves the other five seeds."""
import importlib
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from if_benchmark.seed_contracts import CURRENT_SUITE_TASKS
from tools.release_press_lift_stapler_v1 import RELEASE, verify
from tools.run_formal_policy_suite import current_success_checker
from tools import release_press_lift_stapler_v1 as release_tool
from tools import run_formal_policy_suite as formal


class StaplerManifestReleaseTest(unittest.TestCase):
    def test_rebuild_uses_only_the_retained_qualified_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / 'qualified-run'
            (run / 'generated').mkdir(parents=True)
            for suffix in ('.json', '.generation.json'):
                name = 'press_lift_stapler' + suffix
                shutil.copyfile(RELEASE / name, run / 'generated' / name)
            qualification = RELEASE / 'qualification'
            shutil.copytree(qualification / 'source-snapshot', run / 'source-snapshot')
            for name in ('source-hashes.json', 'run.json', 'robotwin-runtime.patch'):
                shutil.copyfile(qualification / name, run / name)
            (run / 'standard-setup').mkdir()
            shutil.copyfile(qualification / 'standard-setup-validation.json',
                            run / 'standard-setup/validation.json')
            output = root / 'rebuilt-release'
            with patch.object(release_tool, 'ROOT', qualification / 'source-snapshot'):
                release_tool.build(run, base=output, reference=RELEASE)
            for task in CURRENT_SUITE_TASKS:
                self.assertEqual((output / f'{task}.json').read_bytes(),
                                 (RELEASE / f'{task}.json').read_bytes())

    def test_current_formal_prepare_uses_the_stapler_replacement_flow(self):
        base, old = Path('/unused/new-run'), Path('/unused/old-run')
        with patch('tools.prepare_bell_policy_suite.prepare', return_value='prepared') as prepare:
            self.assertEqual(formal.prepare(base, RELEASE, old), 'prepared')
        prepare.assert_called_once_with(base, old, release=RELEASE,
            task_name='press_lift_stapler', verify_release_fn=release_tool.verify)

    def test_qualified_release_and_unchanged_five_manifests(self):
        suite = verify()
        self.assertEqual(suite['episodes_per_policy'], 460)
        self.assertEqual([t['task'] for t in suite['tasks']], list(CURRENT_SUITE_TASKS))
        self.assertNotIn('bottle_verb', CURRENT_SUITE_TASKS)
        self.assertNotIn('press_lift_bell', CURRENT_SUITE_TASKS)
        for spec in suite['tasks'][1:]:
            self.assertEqual(spec['manifest_sha256'], spec['qualification']['parent_manifest_sha256'])
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
