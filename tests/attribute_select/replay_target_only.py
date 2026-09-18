#!/usr/bin/env python3
"""Diagnose archived Attribute-Select actions with the target-only checker.

Replay the exact saved EE actions and preserve the historical target-lift stop
condition, including its final partial action. Observe the new predicate beside
it. This is a diagnostic replay, never a replacement formal policy result.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prefix, output = args.episode_prefix.resolve(), args.output.resolve()
    policy = prefix.parent.parent.name
    if policy not in ('xvla', 'lingbot_va'):
        parser.error('This replay supports archived X-VLA and LingBot-VA EE actions')
    source = {key: Path(str(prefix) + suffix) for key, suffix in (
        ('record', '_result.json'), ('actions', '_actions.npz'),
        ('initial', '_initial_observation.npz'), ('summary', '_summary.json'))}
    record = json.loads(source['record'].read_text())
    summary = json.loads(source['summary'].read_text())
    assert record['task'] == 'attribute_select'
    output.mkdir(parents=True, exist_ok=False)

    from tools.sim_device import pin_renderer
    pci = pin_renderer()
    import numpy as np
    from policies.xvla.eval import load_task
    from policies.xvla.client import CAMERAS
    encode_proprio = importlib.import_module(f'policies.{policy}.client').encode_proprio

    env, config = load_task(ROOT / 'third_party/robotwin', 'attribute_select', summary['config'])
    events, action_signals = [], []
    result = dict(policy=policy, seed=record['seed'], instruction=record['instruction'],
                  source_episode=str(prefix), historical_success=record['success'],
                  diagnostic_only=True, paired_oracle_qualified=False,
                  stop_protocol='historical target-lift stop; saved actions only', renderer_pci=pci,
                  source_sha256={k: digest(p) for k, p in source.items()},
                  checker_sources_sha256={str(p.relative_to(ROOT)): digest(p) for p in (
                      ROOT / 'tasks/envs/attribute_select.py', ROOT / 'tasks/envs/_if_grounding.py',
                      ROOT / 'third_party/robotwin/envs/_base_task.py')})
    try:
        random.seed(record['seed'])
        env.setup_demo(now_ep_num=0, seed=record['seed'], is_test=True, **config)
        env.set_instruction(record['instruction'])
        obs = env.get_obs()
        with np.load(source['initial']) as initial:
            result['initial_images_identical'] = {
                name: bool(np.array_equal(obs['observation'][name]['rgb'], initial[name])) for name in CAMERAS}
            result['initial_proprio_max_error'] = float(np.max(np.abs(encode_proprio(obs) - initial['proprio'])))
        assert all(result['initial_images_identical'].values()), 'Initial RGB differs from the archived scene'
        assert result['initial_proprio_max_error'] < 1e-6, 'Initial robot state differs'

        observe = env._observe_pick
        previous = [None]
        def record_observation():
            observe()
            monitor = env._pick_monitor
            signature = (monitor.lifted, monitor.distractor_lifted_ever)
            if signature != previous[0]:
                events.append(dict(action=env.take_action_cnt, signals=env.eval_signals_without_observing()))
                previous[0] = signature
        # Avoid recursively polling the observer while recording its transitions.
        env.eval_signals_without_observing = lambda: dict(env._pick_monitor.signals(), axis=env.axis, value=env.value)
        env._observe_pick = record_observation
        def legacy_success():
            env._observe_pick()
            return env._pick_monitor.lift['target'] > env.LIFT_THRESH
        env.check_success = legacy_success
        with np.load(source['actions']) as saved:
            actions = saved['executed_actions']
        assert actions.shape == (record['action_calls'], 16)
        for action in actions:
            if env.eval_success:
                break
            env.take_action(action, action_type='ee')
            env.get_obs()
            action_signals.append(dict(action=env.take_action_cnt, signals=env.eval_signals()))
        result.update(replayed_actions=env.take_action_cnt, saved_actions=len(actions),
                      legacy_success=bool(env.eval_success or legacy_success()),
                      new_success=env._raw_success(), signals=env.eval_signals())
    finally:
        for name, data in [('result.json', result), ('events.json', events), ('action-signals.json', action_signals)]:
            (output / name).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
        env.close_env()
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
