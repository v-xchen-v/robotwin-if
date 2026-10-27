"""Seed qualification must retain complete, visually identical verb pairs."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from if_benchmark.seed_generation import new_generation_state, run_generation, accepted_seeds
from tools.bell_seed_audit import BellSeedAudit
from tasks.envs._press_lift_stapler import INSTRUCTIONS, sample_rotations
from policies.xvla.client import CAMERAS


class PressLiftSeedAuditTest(unittest.TestCase):
    def test_stapler_hidden_rotation_mismatch_rejects_pair_even_when_pixels_match(self):
        from tasks.envs._press_lift_stapler import INSTRUCTIONS as STAPLER_INSTRUCTIONS, sample_rotations
        with tempfile.TemporaryDirectory() as tmp:
            audit = BellSeedAudit(tmp, 'press_lift_stapler')
            state = new_generation_state(task='press_lift_stapler', task_config='demo_clean',
                accepted_blocks=1, max_candidate_blocks=2, candidate_floor=110000, provenance={})
            def probe(seed):
                mode = ('press', 'lift')[seed % 2]
                obs = {'observation': {c: {'rgb': np.zeros((2, 2, 3), dtype=np.uint8)} for c in CAMERAS}}
                task = SimpleNamespace(step_lim=250, scene_layout='context', scene_seed=seed // 2,
                    stapler_id=0, initial_position=np.zeros(3), context_initial_positions={},
                    initial_quaternion=np.array([0., 0., 0., 1.] if seed == 110001 else [.5]*4),
                    context_initial_quaternions={}, rotations=sample_rotations(seed // 2),
                    policy_instruction=lambda split: STAPLER_INSTRUCTIONS[mode], get_obs=lambda: obs)
                return dict(setup_ok=True, plan_success=True, check_success=True, observed_mode=mode,
                            diagnostics=audit.initial(task, seed))
            with patch('policies.xvla.client.encode_proprio', return_value=np.zeros(14)):
                state = run_generation(state, probe)
            self.assertEqual(accepted_seeds(state), (110002, 110003))
            self.assertIn('physical state differs', state['blocks'][0]['episodes'][1]['failure']['message'])

    def test_changed_observation_rejects_whole_pair_and_retains_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = BellSeedAudit(tmp, 'press_lift_stapler')
            state = new_generation_state(task='press_lift_stapler', task_config='demo_clean',
                accepted_blocks=1, max_candidate_blocks=2, candidate_floor=110000, provenance={})

            def probe(seed):
                mode = ('press', 'lift')[seed % 2]
                pixels = np.full((2, 2, 3), seed == 110001, dtype=np.uint8)
                obs = {'observation': {c: {'rgb': pixels} for c in CAMERAS}}
                task = SimpleNamespace(step_lim=250, scene_layout='context', scene_seed=seed // 2,
                    stapler_id=0, initial_position=np.zeros(3), context_initial_positions={},
                    initial_quaternion=np.array(sample_rotations(seed // 2)['048_stapler']['quaternion']),
                    context_initial_quaternions={}, rotations=sample_rotations(seed // 2),
                    policy_instruction=lambda split: INSTRUCTIONS[mode], get_obs=lambda: obs)
                return dict(setup_ok=True, plan_success=True, check_success=True, observed_mode=mode,
                            diagnostics=audit.initial(task, seed))

            with patch('policies.xvla.client.encode_proprio', return_value=np.zeros(14)):
                state = run_generation(state, probe)
            self.assertEqual(accepted_seeds(state), (110002, 110003))
            self.assertIn('initial RGB or proprio differs', state['blocks'][0]['episodes'][1]['failure']['message'])
            press, lift = state['blocks'][1]['episodes']
            self.assertEqual(press['diagnostics']['initial_arrays'], lift['diagnostics']['initial_arrays'])
            self.assertEqual(len(list(Path(tmp).glob('*.npz'))), 4)


if __name__ == '__main__':
    unittest.main()
