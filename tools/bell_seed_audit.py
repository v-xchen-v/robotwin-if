"""Record and check paired press/lift observations during seed qualification."""
import hashlib
import importlib
from pathlib import Path

from tasks.envs._press_lift_bell import CONTEXT_LAYOUT_VERSION, mode_for_seed


class BellSeedAudit:
    def __init__(self, directory, task_name='press_lift_bell'):
        if task_name not in ('press_lift_bell', 'press_lift_stapler'):
            raise ValueError(f'Unsupported paired task: {task_name}')
        self.directory = Path(directory)
        self.task_name = task_name
        self.instructions = importlib.import_module(f'tasks.envs._{task_name}').INSTRUCTIONS
        self.previous = None

    def initial(self, task, seed):
        import numpy as np
        from policies.xvla.client import CAMERAS, encode_proprio

        mode = mode_for_seed(seed)
        instruction = task.policy_instruction('unseen')
        if instruction != self.instructions[mode] or task.step_lim != 250:
            raise ValueError('Press/Lift instruction or 250-action budget differs')
        if task.scene_layout != 'context' or task.scene_seed != seed // 2:
            raise ValueError('Press/Lift must use the paired randomized context scene')
        physical = dict(initial_position=task.initial_position.tolist(),
                        context_initial_positions=task.context_initial_positions)
        if self.task_name == 'press_lift_stapler':
            from tasks.envs._press_lift_stapler import ROTATION_VERSION, sample_rotations
            assert task.rotations == sample_rotations(seed // 2), 'Stapler rotation sampling differs'
            physical.update(stapler_id=task.stapler_id, initial_quaternion=task.initial_quaternion.tolist(),
                context_initial_quaternions=task.context_initial_quaternions,
                rotation_sampling_version=ROTATION_VERSION, rotations=task.rotations)
        else:
            physical['bell_id'] = task.bell_id
        obs = task.get_obs()
        arrays = {c: obs['observation'][c]['rgb'].copy() for c in CAMERAS}
        arrays['proprio'] = encode_proprio(obs).copy()
        hashes = {key: dict(sha256=hashlib.sha256(value.tobytes()).hexdigest(),
                            shape=list(value.shape), dtype=str(value.dtype))
                  for key, value in arrays.items()}
        self.directory.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self.directory / f'{seed}_initial.npz', **arrays)
        if seed % 2 == 0:
            self.previous = (seed, hashes, physical)
        elif self.previous != (seed - 1, hashes, physical):
            raise ValueError(f'Press/Lift initial RGB or proprio differs, or physical state differs, for seeds {seed - 1}/{seed}')
        return dict(instruction=instruction, action_limit=task.step_lim,
                    scene_seed=task.scene_seed,
                    context_sampling_version=CONTEXT_LAYOUT_VERSION,
                    initial_arrays=hashes, **physical)
