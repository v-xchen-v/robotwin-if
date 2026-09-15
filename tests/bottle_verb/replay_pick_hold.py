#!/usr/bin/env python3
"""Replay saved X-VLA actions in one scene, recording bottle poses for diagnosis.

No model server or benchmark queue is started. The paired oracle gate is bypassed
for this raw-predicate probe; these outputs must never be imported as eval scores.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--complete-predicted-chunk', action='store_true',
                        help='Also execute the saved final prediction suffix (not part of the original rollout)')
    parser.add_argument('--observe-through-end', action='store_true',
                        help='Record candidate success without stopping physics at the first success')
    args = parser.parse_args()
    prefix = args.episode_prefix.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = Path(str(prefix) + '_actions.npz')
    record = json.loads(Path(str(prefix) + '_result.json').read_text())
    from tools.sim_device import pin_renderer
    pin_renderer()
    import numpy as np
    from policies.xvla.eval import load_task
    from policies.xvla.client import encode_proprio, decode_actions, CAMERAS
    env, config = load_task(ROOT / 'third_party/robotwin', 'bottle_verb', 'demo_clean')
    result = dict(source=str(source), actions_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  seed=record['seed'], diagnostic_only=True, paired_oracle_qualified=False,
                  observe_through_end=args.observe_through_end,
                  complete_predicted_chunk=args.complete_predicted_chunk)
    trace, action_signals = [], []
    try:
        random.seed(record['seed'])
        env.setup_demo(now_ep_num=0, seed=record['seed'], is_test=True, **config)
        env._partner_ok = lambda: True
        env.set_instruction(record['instruction'])
        obs = env.get_obs()
        with np.load(str(prefix) + '_initial_observation.npz') as initial:
            result['initial_proprio_max_error'] = float(np.max(np.abs(encode_proprio(obs) - initial['proprio'])))
            result['initial_images_identical'] = {name: bool(np.array_equal(obs['observation'][name]['rgb'], initial[name])) for name in CAMERAS}
        observe = env._pick_monitor.observe
        def record_pose(t, p, q):
            before = env._pick_monitor.sample_time
            observe(t, p, q)
            if env._pick_monitor.sample_time != before:
                trace.append(dict(t=t, p=[float(v) for v in p], q=[float(v) for v in q],
                                  action=env.take_action_cnt, signals=env.eval_signals()))
        env._pick_monitor.observe = record_pose
        if args.observe_through_end:
            def observe_success():
                env._record()
                return False
            env.check_success = observe_success
        with np.load(source) as data:
            actions = data['executed_actions']
            saved_count = len(actions)
            if args.complete_predicted_chunk:
                predicted = decode_actions(data['raw_actions'])
                if not np.allclose(actions, predicted[:saved_count], atol=1e-7, rtol=0):
                    raise ValueError('Saved predictions do not decode to the executed action prefix')
                actions = predicted
        for action in actions:
            if env.eval_success:
                break
            env.take_action(action, action_type='ee')
            env.get_obs()
            action_signals.append(env.eval_signals())
        result.update(action_calls=env.take_action_cnt, saved_action_calls=saved_count,
                      raw_success=env._raw_success('pick'), signals=env.eval_signals(),
                      pick_ever_succeeded=any(r['signals']['pick_success'] for r in trace))
    finally:
        (output / 'trajectory.json').write_text(json.dumps(trace, allow_nan=False) + '\n')
        (output / 'action-signals.json').write_text(json.dumps(action_signals, allow_nan=False) + '\n')
        (output / 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
        env.close_env()
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
