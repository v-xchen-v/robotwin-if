#!/usr/bin/env python3
"""Diagnostic only: no policy, scored artifacts, or runtime source changes."""
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time

REPO = Path('/home/xichen6/Documents/repos/robotwin-if')
OUT = Path('/Data/robotwin-if/tmp/oracle-planner-isolation-20261105')
sys.path.insert(0, str(REPO))
OUT.mkdir(exist_ok=False)
from tools.sim_device import pin_renderer
pin_renderer()
from policies.xvla.eval import load_task

env, config = load_task(REPO / 'third_party/robotwin', 'stack_sequence', 'demo_clean')
config['policy_name'] = 'xwam'
assert config == json.loads((Path('/Data/robotwin-if/evaluations/wam-full-20261104') / 'xwam/stack_sequence/resolved_config.json').read_text())
results = []
traces = []

def sha(array):
    return hashlib.sha256(array.tobytes()).hexdigest()

def state():
    if not hasattr(env, 'robot'):
        return None
    result = {'communication_flag': env.robot.communication_flag, 'planners': {}}
    assert not env.robot.communication_flag
    for arm in ('left', 'right'):
        planner = getattr(env.robot, arm + '_planner')
        for name in ('motion_gen', 'motion_gen_batch'):
            mg = getattr(planner, name)
            sampler = mg.ik_solver.q_sample_gen
            result['planners'][arm + '.' + name] = {
                'planner_id': id(planner), 'motion_gen_id': id(mg),
                'ik_rng_sha256': sha(sampler._int_gen.get_state().cpu().numpy()),
                'ik_halton_generated': sampler.sequencer.num_generated,
            }
    return result

def reset():
    for arm in ('left', 'right'):
        planner = getattr(env.robot, arm + '_planner')
        for name in ('motion_gen', 'motion_gen_batch'):
            getattr(planner, name).reset(reset_seed=True)

def wrap_planners():
    for arm in ('left', 'right'):
        planner = getattr(env.robot, arm + '_planner')
        if getattr(planner, '_diagnostic_wrapped', False):
            continue
        for name in ('plan_path', 'plan_batch'):
            original = getattr(planner, name)
            def wrapped(*args, _original=original, _name=name, _arm=arm, **kwargs):
                result = _original(*args, **kwargs)
                entry = {'arm': _arm, 'method': _name, 'status': str(result.get('status'))}
                for key in ('position', 'velocity'):
                    if key in result:
                        import numpy as np
                        a = np.asarray(result[key])
                        entry[key] = {'shape': list(a.shape), 'sha256': sha(a)}
                traces.append(entry)
                return result
            setattr(planner, name, wrapped)
        planner._diagnostic_wrapped = True

def setup():
    random.seed(100065)
    env.setup_demo(now_ep_num=0, seed=100065, is_test=True, **config)
    wrap_planners()

def save(row):
    results.append(row)
    (OUT / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print('DIAGNOSTIC', json.dumps({k:v for k,v in row.items() if k not in ('before_setup', 'after_setup', 'before_oracle', 'after_oracle', 'planner_trace', 'action_state_before', 'action_state_after')}), flush=True)

for intervention in ('retained',) * 4 + ('reset_both_generators',) * 4:
    row = {'attempt': len(results) + 1, 'intervention': intervention, 'seed': 100065,
           'before_setup': state()}
    started = time.monotonic()
    setup()
    row['after_setup'] = state()
    row['initial_blocks'] = [{'p': b.get_pose().p.tolist(), 'q': b.get_pose().q.tolist()} for b in env.blocks]
    if intervention != 'retained':
        reset()
    row['before_oracle'] = state()
    traces.clear()
    env.play_once()
    row.update(plan_success=bool(env.plan_success), success=bool(env.check_success()),
               after_oracle=state(), planner_trace=list(traces), seconds=time.monotonic()-started)
    env.close_env()
    save(row)

# Exercise actual qpos and EE executor paths with the current pose as target,
# and inspect private generator state across the following scene setup.
for action_type in ('qpos', 'ee'):
    setup()
    reset()
    row = {'action_type': action_type, 'action_state_before': state()}
    if action_type == 'qpos':
        action = env.robot.get_left_arm_jointState() + env.robot.get_right_arm_jointState()
    else:
        from policies.lingbot_va.client import encode_proprio
        action = encode_proprio(env.get_obs())
    traces.clear()
    env.take_action(action, action_type=action_type)
    row.update(action_state_after=state(), action_calls=env.take_action_cnt, planner_trace=list(traces))
    env.close_env()
    row['before_setup'] = state()
    setup()
    row['after_setup'] = state()
    env.close_env()
    save(row)
print('COMPLETE', OUT, flush=True)
