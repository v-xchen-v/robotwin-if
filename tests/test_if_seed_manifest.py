#!/usr/bin/env python3
"""Simulator-free tests for flat IF seed manifests."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import sys


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from if_benchmark import seed_manifest as sm  # noqa: E402


class SeedManifestTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.data = {
            "schema_version": 1,
            "task": "arm_select",
            "task_config": "demo_clean",
            "seeds": [100000, 100001, 100004, 100005],
        }

    def tearDown(self):
        self.tempdir.cleanup()

    def test_round_trip_is_canonical_and_deterministic(self):
        path = self.root / "nested" / "arm_select.json"
        digest = sm.write_manifest(path, self.data)
        self.assertEqual(sm.load_manifest(path), self.data)
        self.assertEqual(digest, sm.manifest_sha256(self.data))
        self.assertEqual(path.read_bytes(), sm.manifest_bytes(self.data))

    def test_validation_reports_blocks_and_equal_denominators(self):
        checked = sm.validate_manifest(self.data)
        self.assertEqual(checked["block_ids"], (50000, 50002))
        self.assertEqual(checked["mode_denominators"], {"left": 2, "right": 2})

    def test_no_overwrite_and_nonregular_outputs_are_rejected(self):
        path = self.root / "manifest.json"
        sm.write_manifest(path, self.data)
        with self.assertRaisesRegex(sm.ManifestError, "output exists"):
            sm.write_manifest(path, self.data)
        target = self.root / "target.json"
        target.write_text("keep", encoding="utf-8")
        link = self.root / "link.json"
        link.symlink_to(target)
        with self.assertRaisesRegex(sm.ManifestError, "non-regular"):
            sm.write_manifest(link, self.data, overwrite=True)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_wrong_keys_and_schema_are_rejected(self):
        cases = []
        extra = dict(self.data, provenance={})
        cases.append(extra)
        missing = dict(self.data)
        missing.pop("task_config")
        cases.append(missing)
        schema = dict(self.data, schema_version=2)
        cases.append(schema)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(sm.ManifestError):
                sm.validate_manifest(data)

    def test_bad_seed_lists_are_rejected(self):
        cases = (
            [],
            [100000],
            [100001, 100000],
            [100000, 100000],
            [100000, True],
            [-2, -1],
        )
        for seeds in cases:
            with self.subTest(seeds=seeds), self.assertRaises(sm.ManifestError):
                sm.validate_manifest(dict(self.data, seeds=seeds))

    def test_corrupt_symlink_and_oversized_inputs_are_rejected(self):
        corrupt = self.root / "corrupt.json"
        corrupt.write_text("not json", encoding="utf-8")
        with self.assertRaises(sm.ManifestError):
            sm.load_manifest(corrupt)

        target = self.root / "target.json"
        target.write_text(json.dumps(self.data), encoding="utf-8")
        link = self.root / "link.json"
        link.symlink_to(target)
        with self.assertRaisesRegex(sm.ManifestError, "regular file"):
            sm.load_manifest(link)

        large = self.root / "large.json"
        large.write_bytes(b" " * (sm.MAX_MANIFEST_BYTES + 1))
        with self.assertRaisesRegex(sm.ManifestError, "safety limit"):
            sm.load_manifest(large)

    def test_seed_count_limit_is_enforced_without_allocating_a_large_file(self):
        with mock.patch.object(sm, "MAX_MANIFEST_SEEDS", 3):
            with self.assertRaisesRegex(sm.ManifestError, "seed safety limit"):
                sm.validate_manifest(self.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
