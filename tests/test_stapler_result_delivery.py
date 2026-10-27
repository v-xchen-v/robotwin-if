"""Guard against publishing incomplete runs and evaluating a changed stapler scene."""
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from tools import run_formal_policy_suite as formal
from tools.publish_stapler_policy_results import publish


class StaplerResultDeliveryTest(unittest.TestCase):
    def test_incomplete_run_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'run'
            output = Path(tmp) / 'result'
            formal.write(base / 'status.json', dict(status='running'))
            formal.write(base / 'validation.json', dict(complete=False))
            with self.assertRaises(AssertionError):
                publish(base, output)
            self.assertFalse(output.exists())

    def test_stapler_checker_is_pinned_for_success_and_failure(self):
        spec = formal.current_success_checker('press_lift_stapler')
        for success in (False, True):
            record = dict(success=success, signals=dict(checker_version=spec['success_checker_version'],
                          thresholds=spec['success_checker_parameters']))
            self.assertTrue(formal.matches_success_checker(spec, record))
            record['signals']['checker_version'] = 'outdated'
            self.assertFalse(formal.matches_success_checker(spec, record))

    def test_first_model_must_match_manifest_scene_before_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cameras = ('head_camera', 'left_camera', 'right_camera')
            arrays = {c: np.zeros((2, 2, 3), np.uint8) for c in cameras}
            arrays['proprio'] = np.zeros(14)
            expected = {k: dict(sha256=hashlib.sha256(v.tobytes()).hexdigest(),
                                dtype=str(v.dtype), shape=list(v.shape)) for k, v in arrays.items()}
            formal.write(base / 'manifests/press_lift_stapler.generation.json', dict(blocks=[dict(
                accepted=True, episodes=[dict(seed=seed, diagnostics=dict(initial_arrays=expected,
                    instruction=instruction, action_limit=250)) for seed, instruction in
                    ((110000, 'Press down on the stapler.'), (110001, 'Lift the stapler.'))])]))
            obs = {'observation': {c: dict(rgb=arrays[c]) for c in cameras}}
            spec = dict(task='press_lift_stapler', instructions=dict(press='Press down on the stapler.', lift='Lift the stapler.'))
            def check(instruction='Press down on the stapler.', seed=110000):
                formal.check_scene(base, 'xvla', spec, seed, instruction,
                                   obs, SimpleNamespace(step_lim=250), lambda suffix: base / suffix)
            with patch('policies.xvla.client.encode_proprio', return_value=arrays['proprio']):
                check()
                check('Lift the stapler.', 110001)
                with self.assertRaises(AssertionError):
                    check('Pick up the stapler.', 110001)
                with self.assertRaises(AssertionError):
                    check('Pick up the stapler.')
                arrays['head_camera'][0, 0, 0] = 1
                with self.assertRaisesRegex(AssertionError, 'qualification scene differs'):
                    check()


if __name__ == '__main__':
    unittest.main()
