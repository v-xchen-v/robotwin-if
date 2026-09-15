#!/usr/bin/env python3
"""Isolated reachability sweep; never changes the frozen task or formal seeds."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gpu', required=True)
    parser.add_argument('--pci', required=True)
    parser.add_argument('--positions', type=Path, required=True)
    args = parser.parse_args()
    os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu
    import numpy as np
    from PIL import Image
    from tools.sim_device import pin_renderer
    from tools.run_formal_policy_suite import write, digest
    from policies.xvla.eval import load_task, instruction_for
    assert pin_renderer().lower() == args.pci.lower()
    args.output.mkdir(parents=True, exist_ok=False)
    positions = json.loads(args.positions.read_text())
    write(args.output / 'experiment.json', dict(positions=positions, gpu=args.gpu, pci=args.pci,
          task_sha256=digest(ROOT / 'tasks/envs/grasp_cube_approach.py'),
          note='Runtime-only translation override. Same riser, orientation, right oracle arm, face 6 and success rules. Not formal evaluation.'))
    env, config = load_task(ROOT / 'third_party/robotwin', 'grasp_cube_approach', 'demo_clean_grasp_approach_v2')
    cls = type(env)
    original = cls.__dict__['translation_xy']
    rows = []

    def beat(stage, **kw):
        write(args.output / 'heartbeat.json', dict(time=time.time(), stage=stage, **kw))

    try:
        for i, position in enumerate(positions):
            x, y = position['xy']
            cls.translation_xy = classmethod(lambda cls, scene_seed, profile=None, x=x, y=y: (x, y, 'range-probe'))
            signatures = []
            for mode in ('top', 'side'):
                seed = position.get('seed', 300000 + 2 * i) + (mode == 'side')
                row = dict(position=position['name'], xy=[x, y], seed=seed, mode=mode)
                started = time.monotonic()
                try:
                    beat('setup', **row)
                    env.setup_demo(now_ep_num=0, seed=seed, is_test=True, **config)
                    obs = env.get_obs()
                    images = {k: obs['observation'][k]['rgb'] for k in ('head_camera', 'left_camera', 'right_camera')}
                    row['rgb_sha256'] = {k: hashlib.sha256(v.tobytes()).hexdigest() for k, v in images.items()}
                    signatures.append(row['rgb_sha256'])
                    row['initial_pose'] = np.r_[env.cube.get_pose().p, env.cube.get_pose().q].tolist()
                    Image.fromarray(images['head_camera']).save(args.output / f'{i:02d}-{mode}-initial.png')
                    np.savez_compressed(args.output / f'{i:02d}-{mode}-initial.npz', **images)
                    beat('oracle', **row)
                    info = env.play_once()
                    row.update(plan_success=bool(env.plan_success), success=bool(env.check_success()),
                               signals=env.eval_signals(), oracle_info=info,
                               instruction=instruction_for('grasp_cube_approach', info, 'unseen', seed))
                    row['passed'] = row['plan_success'] and row['success']
                    Image.fromarray(env.get_obs()['observation']['head_camera']['rgb']).save(args.output / f'{i:02d}-{mode}-final.png')
                except Exception as exc:
                    traceback.print_exc()
                    row.update(passed=False, error=f'{type(exc).__name__}: {exc}')
                finally:
                    beat('closing', **row)
                    env.close_env()
                row['elapsed_seconds'] = time.monotonic() - started
                rows.append(row)
                write(args.output / 'episodes.json', rows)
                print(position['name'], mode, 'PASS' if row['passed'] else 'FAIL', flush=True)
                beat('episode_complete', **row)
            assert len(signatures) == 2 and signatures[0] == signatures[1], 'Paired scenes differ'
        write(args.output / 'summary.json', dict(complete=True, episodes=len(rows),
              paired_positions=[dict(position=p['name'], xy=p['xy'],
                  both_passed=all(r['passed'] for r in rows if r['position'] == p['name'])) for p in positions]))
    finally:
        cls.translation_xy = original
    return 0


if __name__ == '__main__':
    sys.exit(main())
