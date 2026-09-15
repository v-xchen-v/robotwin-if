"""Keep the Clean and All weight identities from being mixed during reruns."""

import unittest

from policies.vlact.download_checkpoint import VARIANTS, checkpoint_spec


class CheckpointTests(unittest.TestCase):
    def test_published_variants_use_their_own_weights_and_training_mix(self):
        for variant, steps, mix in (("all", 100000, "robotwin_all_wrap_32"),
                                    ("clean", 50000, "robotwin_wrap_32")):
            with self.subTest(variant=variant):
                identity = VARIANTS[variant].copy()
                spec = checkpoint_spec(identity)
                self.assertEqual(spec["weights"], f"checkpoints/steps_{steps}_pytorch_model.pt")
                self.assertEqual(spec["data_mix"], mix)

    def test_mixed_clean_and_all_identities_are_rejected(self):
        for key in ("repo_id", "revision", "weights_sha256"):
            with self.subTest(key=key):
                mixed = dict(VARIANTS["all"], **{key: VARIANTS["clean"][key]})
                with self.assertRaises(ValueError):
                    checkpoint_spec(mixed)

    def test_unpinned_revision_and_missing_identity_are_rejected(self):
        for identity in ({}, dict(VARIANTS["all"], revision="main")):
            with self.assertRaises(ValueError):
                checkpoint_spec(identity)


if __name__ == "__main__":
    unittest.main()
