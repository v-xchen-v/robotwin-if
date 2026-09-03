#!/usr/bin/env python3
"""Simulator-free tests for maintained IF seed contracts."""

from pathlib import Path
import sys
import unittest


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from if_benchmark.seed_contracts import (  # noqa: E402
    IF_SEED_CONTRACTS,
    describe_seed,
    expand_block,
    first_block_at_or_above,
    mode_denominators,
    validate_complete_blocks,
)


TASKS = (
    "bottle_verb",
    "pick_diverse_object",
    "attribute_select",
    "arm_select",
    "stack_sequence",
    "place_relative",
    "grasp_cube_approach",
)
SIZES = (2, 2, 8, 2, 6, 5, 2)


class SeedContractTests(unittest.TestCase):
    def test_inventory_and_sizes_are_exact(self):
        self.assertEqual(tuple(IF_SEED_CONTRACTS), TASKS)
        self.assertEqual(
            tuple(contract.block_size for contract in IF_SEED_CONTRACTS.values()),
            SIZES,
        )

    def test_pair_modes_and_shared_scenes(self):
        cases = {
            "bottle_verb": ("pick", "shake"),
            "arm_select": ("left", "right"),
            "grasp_cube_approach": ("top", "side"),
        }
        for task, modes in cases.items():
            with self.subTest(task=task):
                first = describe_seed(task, 100000)
                second = describe_seed(task, 100001)
                self.assertEqual((first.mode, second.mode), modes)
                self.assertEqual(first.scene_index, second.scene_index)

    def test_pick_balance_pair_uses_independent_scenes(self):
        seen = describe_seed("pick_diverse_object", 100000)
        unseen = describe_seed("pick_diverse_object", 100001)
        self.assertEqual((seen.mode, unseen.mode), ("seen", "unseen"))
        self.assertEqual(seen.block_index, unseen.block_index)
        self.assertNotEqual(seen.scene_index, unseen.scene_index)

    def test_attribute_block_has_four_same_scene_pairs(self):
        seeds = expand_block("attribute_select", 12500)
        rows = [describe_seed("attribute_select", seed) for seed in seeds]
        self.assertEqual(
            tuple(row.mode for row in rows),
            (
                "color:red", "color:blue",
                "decal:cat", "decal:dog",
                "shape:block", "shape:bar",
                "size:big", "size:small",
            ),
        )
        self.assertEqual(
            tuple(row.scene_index for row in rows),
            (50000, 50000, 50001, 50001, 50002, 50002, 50003, 50003),
        )

    def test_stack_alignment_starts_at_complete_block(self):
        block = first_block_at_or_above("stack_sequence", 100000)
        self.assertEqual(block, 16667)
        self.assertEqual(expand_block("stack_sequence", block), tuple(range(100002, 100008)))

    def test_complete_blocks_may_have_candidate_gaps(self):
        seeds = [100000, 100001, 100004, 100005]
        self.assertEqual(validate_complete_blocks("arm_select", seeds), (50000, 50002))
        self.assertEqual(mode_denominators("arm_select", seeds), {"left": 2, "right": 2})

    def test_partial_reordered_duplicate_and_invalid_seeds_are_rejected(self):
        bad = (
            [100000],
            [100001, 100000],
            [100000, 100000],
            [100000, True],
            [100000, -1],
        )
        for seeds in bad:
            with self.subTest(seeds=seeds), self.assertRaises(ValueError):
                validate_complete_blocks("arm_select", seeds)


if __name__ == "__main__":
    unittest.main(verbosity=2)
