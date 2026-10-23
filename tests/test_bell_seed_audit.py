"""Seed qualification must retain complete, visually identical verb pairs."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from if_benchmark.seed_generation import new_generation_state, run_generation, accepted_seeds
from tools.bell_seed_audit import BellSeedAudit
from tasks.envs._press_lift_bell import INSTRUCTIONS
from policies.xvla.client import CAMERAS


class BellSeedAuditTest(unittest.TestCase):
    def test_changed_observation_rejects_whole_pair_and_retains_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = BellSeedAudit(tmp)
            state = new_generation_state(task='press_lift_bell', task_config='demo_clean',
                accepted_blocks=1, max_candidate_blocks=2, candidate_floor=100000, provenance={})

            def probe(seed):
                mode = ('press', 'lift')[seed % 2]
                pixels = np.full((2, 2, 3), seed == 100001, dtype=np.uint8)
                obs = {'observation': {c: {'rgb': pixels} for c in CAMERAS}}
                task = SimpleNamespace(step_lim=250, scene_layout='context', scene_seed=seed // 2,
                    bell_id=0, initial_position=np.zeros(3), context_initial_positions={},
                    policy_instruction=lambda split: INSTRUCTIONS[mode], get_obs=lambda: obs)
                return dict(setup_ok=True, plan_success=True, check_success=True, observed_mode=mode,
                            diagnostics=audit.initial(task, seed))

            with patch('policies.xvla.client.encode_proprio', return_value=np.zeros(14)):
                state = run_generation(state, probe)
            self.assertEqual(accepted_seeds(state), (100002, 100003))
            self.assertIn('initial RGB or proprio differs', state['blocks'][0]['episodes'][1]['failure']['message'])
            press, lift = state['blocks'][1]['episodes']
            self.assertEqual(press['diagnostics']['initial_arrays'], lift['diagnostics']['initial_arrays'])
            self.assertEqual(len(list(Path(tmp).glob('*.npz'))), 4)


if __name__ == '__main__':
    unittest.main()
