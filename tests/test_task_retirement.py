"""Retired tasks remain readable as evidence but cannot be evaluated as raw tasks."""
import importlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from if_benchmark.seed_contracts import IF_SEED_CONTRACTS
from if_benchmark.seed_manifest import validate_manifest
from policies.xvla.eval import load_task
from tools.run_formal_policy_suite import check_active_tasks

ROOT = Path(__file__).resolve().parents[1]


class RetirementTest(unittest.TestCase):
    def test_all_policy_entrypoints_reject_retired_task_before_output_or_simulation(self):
        for policy in ('xvla', 'lingbot_va', 'lingbot_vla', 'vlact', 'dm05', 'hy_vla'):
            module = importlib.import_module(f'policies.{policy}.eval')
            with self.subTest(policy=policy), patch.object(sys, 'argv', [
                'eval.py', '--task', 'grasp_cube_approach', '--output-dir', 'unused-retired-output'
            ]), patch.object(module, 'load_task') as load:
                with self.assertRaisesRegex(ValueError, 'retired'):
                    module.main()
                load.assert_not_called()

    def test_direct_loader_rejects_retired_task(self):
        with self.assertRaisesRegex(ValueError, 'retired'):
            load_task(ROOT / 'third_party/robotwin', 'grasp_cube_approach', 'demo_clean')

    def test_archived_manifest_still_parses_without_reactivating_task(self):
        manifest = dict(schema_version=1, task='grasp_cube_approach', task_config='demo_clean',
                        seeds=list(range(40)))
        validate_manifest(manifest)
        self.assertEqual(len(manifest['seeds']), 40)
        self.assertNotIn(manifest['task'], IF_SEED_CONTRACTS)
        self.assertFalse((ROOT / 'tasks/envs/grasp_cube_approach.py').exists())
        self.assertTrue((ROOT / 'bak/grasp_cube_approach/tasks/envs/grasp_cube_approach.py').is_file())

    def test_formal_runs_require_full_current_inventory(self):
        specs = [dict(task=t) for t in IF_SEED_CONTRACTS]
        check_active_tasks(specs)
        for invalid in (specs[:-1], specs + [dict(task='grasp_cube_approach')]):
            with self.assertRaises(AssertionError):
                check_active_tasks(invalid)


if __name__ == '__main__':
    unittest.main()
