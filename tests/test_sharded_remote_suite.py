import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import run_sharded_remote_suite as sharded


class ShardTests(unittest.TestCase):
    def test_balances_remaining_blocks_and_never_reassigns_completed_seeds(self):
        seeds = list(range(500000, 500040))
        completed = set(seeds[:9])
        left, right = sharded.split_remaining(seeds, completed)
        self.assertFalse(set(left) & set(right))
        self.assertEqual(set(left + right), set(seeds) - completed)
        self.assertLessEqual(abs(len(left) - len(right)), 2)
        for block in range(20):
            remaining = set(seeds[2 * block:2 * block + 2]) - completed
            self.assertTrue(remaining <= set(left) or remaining <= set(right))

    def test_partition_rejects_missing_and_overlapping_work(self):
        slots = [dict(id='a', lane=1, policy='hy_vla', seeds=[0, 1]),
                 dict(id='b', lane=2, policy='hy_vla', seeds=[2, 3])]
        pending = {('hy_vla', s) for s in range(4)}
        sharded.validate_partition(slots, list(range(4)), pending)
        with self.assertRaisesRegex(AssertionError, 'no shard owner'):
            sharded.validate_partition(slots[:1], list(range(4)), pending)
        with self.assertRaisesRegex(AssertionError, 'Overlapping'):
            sharded.validate_partition([slots[0], dict(slots[1], seeds=[1, 2])], list(range(4)), pending)

    def test_same_seed_for_different_policies_is_valid(self):
        slots = [dict(id='a', lane=0, policy='dm05', seeds=[0, 1]),
                 dict(id='b', lane=2, policy='hy_vla', seeds=[0, 1])]
        sharded.validate_partition(slots, [0, 1], {('dm05', 0), ('hy_vla', 1)})

    def test_selection_keeps_original_manifest_and_order(self):
        manifest = dict(seeds=list(range(8)))
        args = object()
        def original(given):
            self.assertIs(given, args)
            return manifest['seeds'], manifest, 'unseen'
        seeds, observed, split = sharded.select_shard(original, args, [2, 3, 6, 7])
        self.assertEqual(seeds, [2, 3, 6, 7])
        self.assertIs(observed, manifest)
        self.assertEqual(manifest['seeds'], list(range(8)))
        self.assertEqual(split, 'unseen')
        with self.assertRaises(AssertionError):
            sharded.select_shard(original, args, [10])

    def test_shard_uses_original_block_ordinals_and_records_ownership(self):
        seeds = list(range(500000, 500008))
        calls = []
        def episode(*args, block=None):
            calls.append((args[4], block))
            return 'episode'
        select = lambda args: (seeds, dict(seeds=seeds), 'unseen')
        setup = lambda *args: ('instruction', 'observation')
        module = SimpleNamespace(select_seeds=select, run_episode=episode, setup_episode=setup)
        cfg = dict(run_dir='/unused', task='arm_select', controller_sha256='controller')
        slot = dict(id='b', config='/unused/config', config_sha256='config', lane=1,
                    policy='hy_vla', seeds=seeds[4:6])
        spec = dict(task='arm_select', seeds=seeds)
        with tempfile.TemporaryDirectory() as tmp:
            def original_worker(child, lane, policy, output):
                self.assertEqual(module.select_seeds(None)[0], seeds[4:6])
                module.run_episode(None, None, None, None, seeds[4], 'unseen', output, block=0)
                self.assertEqual(calls, [(seeds[4], 2)])
                with self.assertRaisesRegex(AssertionError, 'another shard'):
                    module.run_episode(None, None, None, None, seeds[0], 'unseen', output)
                return module.setup_episode(None, None, None, seeds[4], 'unseen', {},
                                            lambda suffix: Path(tmp) / suffix)
            with patch.object(sharded.remote, 'load_config', return_value={}), \
                 patch.object(sharded.formal, 'read', return_value=dict(tasks=[spec])), \
                 patch.object(sharded.importlib, 'import_module', return_value=module), \
                 patch.object(sharded.remote, 'worker', side_effect=original_worker):
                self.assertEqual(sharded.worker(cfg, slot, Path(tmp)), ('instruction', 'observation'))
            self.assertIs(module.run_episode, episode)
            self.assertIs(module.select_seeds, select)
            self.assertIn('"formal_block": 2', (Path(tmp) / '_execution_shard.json').read_text())


if __name__ == '__main__':
    unittest.main()
