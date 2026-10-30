"""Retired tasks remain readable as evidence but cannot be evaluated as raw tasks."""
import importlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from if_benchmark.seed_contracts import (
    ARCHIVED_SEED_CONTRACTS, BELL_SUITE_TASKS, CURRENT_SUITE_TASKS, LEGACY_SUITE_TASKS,
    IF_SEED_CONTRACTS, RETIRED_TASKS,
)
from if_benchmark.seed_manifest import validate_manifest
from policies.xvla.eval import load_task

ROOT = Path(__file__).resolve().parents[1]


class RetirementTest(unittest.TestCase):
    def test_all_policy_entrypoints_reject_retired_task_before_output_or_simulation(self):
        for policy in ('xvla', 'lingbot_va', 'lingbot_vla', 'vlact', 'dm05', 'hy_vla'):
            module = importlib.import_module(f'policies.{policy}.eval')
            for task in sorted(RETIRED_TASKS):
                with self.subTest(policy=policy, task=task), patch.object(sys, 'argv', [
                    'eval.py', '--task', task, '--output-dir', 'unused-retired-output'
                ]), patch.object(module, 'load_task') as load:
                    with self.assertRaisesRegex(ValueError, 'retired'):
                        module.main()
                    load.assert_not_called()

    def test_direct_loader_rejects_retired_task(self):
        for task in sorted(RETIRED_TASKS):
            with self.subTest(task=task), self.assertRaisesRegex(ValueError, 'retired'):
                load_task(ROOT / 'third_party/robotwin', task, 'demo_clean')

    def test_archived_manifest_still_parses_without_reactivating_task(self):
        for task in ARCHIVED_SEED_CONTRACTS:
            with self.subTest(task=task):
                manifest = dict(schema_version=1, task=task, task_config='demo_clean', seeds=list(range(40)))
                validate_manifest(manifest)
                self.assertEqual(len(manifest['seeds']), 40)
                self.assertNotIn(task, IF_SEED_CONTRACTS)
        for task in RETIRED_TASKS:
            self.assertFalse((ROOT / f'tasks/envs/{task}.py').exists())
            self.assertFalse((ROOT / f'tasks/task_instruction/{task}.json').exists())



if __name__ == '__main__':
    unittest.main()
