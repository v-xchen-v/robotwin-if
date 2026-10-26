from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import sys

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root))
from tools.sim_device import pin_renderer
pin_renderer()
from policies.xvla.eval import load_task, select_seeds
from policies.evaluation import setup_episode
from policies.xvla.client import CAMERAS, encode_proprio
from tools.release_press_lift_bell_v1 import RELEASE

run = Path(__file__).resolve().parent
out = run / 'standard-setup'
out.mkdir(exist_ok=False)
args = SimpleNamespace(task='press_lift_bell', task_config='demo_clean',
    seed_manifest=RELEASE / 'press_lift_bell.json', blocks=1, instruction_type='unseen')
seeds, manifest, split = select_seeds(args)
evidence = json.loads((RELEASE / 'press_lift_bell.generation.json').read_text())
env, config = load_task(root / 'third_party/robotwin', args.task, args.task_config)
records = []
for seed in seeds:
    record = dict(mode=('press', 'lift')[seed % 2], seed=seed)
    try:
        instruction, obs = setup_episode(env, config, args, seed, split, record,
                                        lambda suffix: out / f'{seed}{suffix}')
        expected = next(e['diagnostics'] for b in evidence['blocks'] for e in b['episodes'] if e['seed'] == seed)
        arrays = {c: obs['observation'][c]['rgb'] for c in CAMERAS}
        arrays['proprio'] = encode_proprio(obs)
        hashes = {k: dict(sha256=hashlib.sha256(v.tobytes()).hexdigest(), shape=list(v.shape), dtype=str(v.dtype))
                  for k, v in arrays.items()}
        assert expected['initial_arrays'] == hashes
        assert instruction == expected['instruction'] and env.step_lim == expected['action_limit'] == 250
        record.update(initial_arrays_match=True, initial_arrays=hashes, model_requests=0)
        records.append(record)
    finally:
        env.close_env()
report = dict(complete=True, purpose='standard evaluator oracle/reset/instruction/observation wiring',
              model_requests=0, records=records)
(out / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
