"""Record and check paired bell observations during expert seed qualification."""
import hashlib
from pathlib import Path

from tasks.envs._press_lift_bell import CONTEXT_LAYOUT_VERSION, INSTRUCTIONS, mode_for_seed


class BellSeedAudit:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.previous = None

    def initial(self, task, seed):
        import numpy as np
        from policies.xvla.client import CAMERAS, encode_proprio

        mode = mode_for_seed(seed)
        instruction = task.policy_instruction('unseen')
        if instruction != INSTRUCTIONS[mode] or task.step_lim != 250:
            raise ValueError('Bell instruction or 250-action budget differs')
        if task.scene_layout != 'context' or task.scene_seed != seed // 2:
            raise ValueError('Bell must use the paired randomized context scene')
        obs = task.get_obs()
        arrays = {c: obs['observation'][c]['rgb'].copy() for c in CAMERAS}
        arrays['proprio'] = encode_proprio(obs).copy()
        hashes = {key: dict(sha256=hashlib.sha256(value.tobytes()).hexdigest(),
                            shape=list(value.shape), dtype=str(value.dtype))
                  for key, value in arrays.items()}
        self.directory.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self.directory / f'{seed}_initial.npz', **arrays)
        if seed % 2 == 0:
            self.previous = (seed, hashes)
        elif self.previous != (seed - 1, hashes):
            raise ValueError(f'Press/Lift initial RGB or proprio differs for seeds {seed - 1}/{seed}')
        return dict(instruction=instruction, action_limit=task.step_lim,
                    scene_seed=task.scene_seed, bell_id=task.bell_id,
                    context_sampling_version=CONTEXT_LAYOUT_VERSION,
                    initial_arrays=hashes,
                    initial_position=task.initial_position.tolist(),
                    context_initial_positions=task.context_initial_positions)
