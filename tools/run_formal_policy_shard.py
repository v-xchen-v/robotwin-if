#!/usr/bin/env python3
"""Run a disjoint host assignment using the frozen formal evaluation contracts.

The original runner and evaluator remain unchanged. A deployment records host
paths, GPU identities and task ownership; completed failures remain immutable.
"""
import argparse
import datetime
import fcntl
import importlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import run_formal_policy_suite as suite


def relocate(value, mapping):
    if isinstance(value, str):
        if not mapping:
            return value
        pattern = '|'.join(re.escape(old) for old in sorted(mapping, key=len, reverse=True))
        return re.sub(pattern, lambda match: mapping[match.group(0)], value)
    if isinstance(value, list):
        return [relocate(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: relocate(v, mapping) for k, v in value.items()}
    return value


def load_config(path):
    cfg = suite.read(path)
    assert cfg['host'] == socket.gethostname(), 'Wrong deployment host'
    owners = cfg['assignments']
    from if_benchmark.seed_contracts import IF_SEED_CONTRACTS
    tasks = [t for row in owners.values() for t in row]
    assert len(tasks) == len(set(tasks)) and set(tasks) == set(IF_SEED_CONTRACTS)
    assert cfg['tasks'] == owners[cfg['host']]
    assert cfg['policies'] == suite.POLICIES, 'All policies for each task share one host'
    assert Path(cfg['repo_root']).resolve() == ROOT
    assert cfg['sim_gpu']['uuid'] != cfg['model_gpu']['uuid']
    return cfg


def check_sources(base, cfg):
    suite.check_sources(base)
    for name, sha in cfg['deployment_sha256'].items():
        assert suite.digest(ROOT / name) == sha, ('Deployment code changed', name)


def gpu_check(base, cfg, label, idle=False):
    proc = subprocess.run(['nvidia-smi', '--query-gpu=index,uuid,pci.bus_id,memory.used,memory.total,temperature.gpu,utilization.gpu',
                           '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=8, check=True)
    rows = [list(map(str.strip, line.split(','))) for line in proc.stdout.splitlines()]
    selected = []
    for role in ('sim_gpu', 'model_gpu'):
        device = cfg[role]
        matches = [r for r in rows if r[1] == device['uuid']]
        assert len(matches) == 1, ('GPU identity missing', device)
        row = matches[0]
        assert int(row[0]) == device['index'] and row[2].lower().endswith(device['pci'][4:].lower())
        used, total, temp, utilization = map(int, row[3:])
        assert temp < 87 and used < total * .96, ('GPU threshold', row)
        if role == 'sim_gpu':
            assert used < 24576, ('Simulator memory limit', row)
        if idle:
            assert used < 2048 and utilization < 10, ('GPU not idle', row)
        selected.append(row)
    assert __import__('shutil').disk_usage(base).free > 100 * 1024**3
    with (base / 'support' / ('gpu-' + cfg['host'] + '.jsonl')).open('a') as log:
        log.write(json.dumps(dict(time=time.time(), label=label, rows=selected)) + '\n')


def report(base, cfg, state, current=None, error=None):
    status = suite.report(base, state='distributed', current=current, error=error)
    rows = [r for r in suite.read(base / 'summary.json')['tasks'] if r['policy'] in cfg['policies'] and r['task'] in cfg['tasks']]
    shard = dict(host=cfg['host'], status=state, updated_at=status['updated_at'],
                 policies=cfg['policies'], tasks=cfg['tasks'], current=current, error=error,
                 completed_episodes=sum(r['recorded_episodes'] for r in rows),
                 expected_episodes=sum(r['expected_episodes'] for r in rows),
                 completed_blocks=sum(r['completed_blocks'] for r in rows),
                 expected_blocks=sum(r['expected_blocks'] for r in rows))
    suite.write(base / 'shards' / cfg['host'] / 'status.json', shard)
    return shard


def check_scene(base, cfg, policy, spec, seed, instruction, obs, env, path):
    """X-VLA establishes each scene; subsequent policies must match it exactly."""
    if policy == 'xvla':
        return
    import numpy as np
    from policies.xvla.client import encode_proprio
    task = spec['task']
    reference = suite.completed_record(base, 'xvla', spec, seed)
    assert reference is not None, ('Missing canonical X-VLA scene', task, seed)
    pre = base / 'xvla' / task / suite.prefix(task, seed)
    marker = suite.read(str(pre) + '_provenance.json')
    initial_path = Path(str(pre) + '_initial_observation.npz')
    expected_sha = marker['files_sha256'][initial_path.name]
    assert suite.digest(initial_path) == expected_sha, 'Reference checksum changed'
    assert instruction == reference['instruction'] and env.step_lim == reference['step_limit']
    with np.load(initial_path) as expected:
        for camera in ('head_camera', 'left_camera', 'right_camera'):
            assert np.array_equal(obs['observation'][camera]['rgb'], expected[camera]), (task, seed, camera, 'Initial RGB mismatch')
        np.testing.assert_allclose(encode_proprio(obs), expected['proprio'], atol=1e-6, rtol=0)
    suite.write(path('_same_host_scene.json'), dict(reference=str(pre), host=cfg['host'],
                initial_sha256=expected_sha, exact_rgb=True, instruction=True, state_atol=1e-6))


def worker(base, cfg, policy, task, output):
    assert policy in cfg['policies'] and task in cfg['tasks']
    check_sources(base, cfg)
    plan = suite.read(base / 'plan.json')
    spec = next(s for s in plan['tasks'] if s['task'] == task)
    old = suite.read(base / 'provenance/reused' / policy / task / 'run.json')['arguments']
    module = importlib.import_module('policies.' + policy + '.eval')
    original, setup = module.run_episode, module.setup_episode
    retained = {s: r for s in spec['seeds'] if (r := suite.completed_record(base, policy, spec, s)) is not None}

    def resume(env, config, client, args, seed, split, directory, block=None):
        if seed in retained:
            return retained[seed].copy()
        if (base / 'shards' / cfg['host'] / 'STOP_AFTER_EPISODE').exists():
            raise RuntimeError('Operator requested a stop at the episode boundary')
        return original(env, config, client, args, seed, split, directory, block=block)

    def guarded_setup(env, config, args, seed, split, record, path):
        instruction, obs = setup(env, config, args, seed, split, record, path)
        check_scene(base, cfg, policy, spec, seed, instruction, obs, env, path)
        return instruction, obs

    module.run_episode, module.setup_episode = resume, guarded_setup
    sim_device = cfg['sim_gpu']['uuid']
    argv = [str(module.__file__), '--task', task, '--task-config', spec['task_config'],
            '--seed-manifest', str(base / 'manifests' / spec['manifest']), '--blocks', '12',
            '--instruction-type', 'unseen', '--sim-gpu', sim_device, '--output-dir', str(output),
            '--server-url', old['server_url'], '--request-timeout', str(old['request_timeout']),
            '--oracle-cache-dir', str(base / 'oracle-cache'), '--render-sync', 'observation']
    for option in ('checkpoint', 'checkpoint_revision', 'feedback', 'gripper_threshold', 'denoising_steps'):
        if option in old:
            argv += ['--' + option.replace('_', '-'), str(old[option])]
    suite.write(output.parent / (task + '-resume.json'), dict(skipped_seeds=list(retained),
                canonical_directory=str(base / policy / task), argv=argv, host=cfg['host']))
    os.environ['CUDA_VISIBLE_DEVICES'] = sim_device
    from tools.sim_device import pin_renderer
    assert pin_renderer().lower() == cfg['sim_gpu']['pci'].lower()
    sys.argv = argv
    return module.main()


def server_command(base, cfg, policy, directory):
    old = suite.read(base / 'support/services-before-recovery.json')[policy]
    tail = relocate(old['argv'][1:], cfg['path_mapping'])
    if tail[0] == '-u':
        tail = tail[1:]
    cmd = [str(Path(cfg['envs'][policy]) / 'bin/python'), '-u'] + tail
    if '--gpu' in cmd:
        cmd[cmd.index('--gpu') + 1] = cfg['model_gpu']['uuid']
    flag = '--output_dir' if policy == 'xvla' else '--output-dir'
    cmd[cmd.index(flag) + 1] = str(directory)
    return [str(ROOT / a) if a.startswith('policies/') else a for a in cmd]


def server_identity(base, cfg, policy, directory):
    if policy == 'xvla':
        return
    expected = suite.read(base / 'provenance/reused' / policy / 'bottle_verb/run.json')['server_metadata']
    actual = suite.read(directory / 'server.json')
    for key, value in relocate(expected, cfg['path_mapping']).items():
        if key not in {'created_at', 'gpu', 'source_sha256'}:
            assert actual.get(key) == value, (policy, 'Server identity changed', key)


def run(base, cfg, config_path):
    lock = (base / 'scheduler.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    check_sources(base, cfg)
    plan = suite.read(base / 'plan.json')
    specs = [s for s in plan['tasks'] if s['task'] in cfg['tasks']]
    session = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + cfg['host']
    server = sim = None
    current = {}

    def interrupted(signum, frame):
        raise RuntimeError(f'Scheduler received signal {signum}')

    def launch(cmd, cwd, env, log):
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open('x') as stream:
            return subprocess.Popen(cmd, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        for previous in (base / 'batches').glob('*'):
            for policy in cfg['policies']:
                for spec in specs:
                    suite.ingest_batch(base, policy, spec, previous / policy / spec['task'])
        for policy in cfg['policies']:
            todo = [s for s in specs if any(suite.completed_record(base, policy, s, seed) is None for seed in s['seeds'])]
            if not todo:
                continue
            assert not any(suite.port_open(p) for p in suite.PORTS.values()), 'Another policy server is active'
            gpu_check(base, cfg, 'before ' + policy, idle=True)
            check_sources(base, cfg)
            for spec in todo:
                suite.check_oracle_budget(base, policy, spec)
            directory = base / 'servers' / session / policy
            cmd = server_command(base, cfg, policy, directory)
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=cfg['model_gpu']['uuid'], PYTHONNOUSERSITE='1',
                       HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
            env['PATH'] = str(Path(cfg['envs'][policy]) / 'bin') + os.pathsep + env.get('PATH', '')
            server = launch(cmd, ROOT / 'third_party/xvla' if policy == 'xvla' else ROOT,
                            env, base / 'batches' / session / policy / 'server.log')
            current = dict(policy=policy, phase='loading_server', server_pid=server.pid, argv=cmd, session=session)
            suite.write(base / 'batches' / session / policy / 'server-launch.json', current)
            report(base, cfg, 'running', current)
            deadline = time.monotonic() + 1200
            while not suite.port_open(suite.PORTS[policy]):
                assert server.poll() is None, f'{policy} server exited {server.returncode}'
                assert time.monotonic() < deadline, 'Server load timeout'
                gpu_check(base, cfg, 'loading ' + policy)
                time.sleep(15)
            server_identity(base, cfg, policy, directory)
            for index, spec in enumerate(todo):
                check_sources(base, cfg)
                suite.check_oracle_budget(base, policy, spec)
                task = spec['task']
                batch = base / 'batches' / f'{session}-{index:03d}' / policy
                output = batch / task
                cmd = [cfg['python'], '-u', str(Path(__file__).resolve()), 'worker', '--config', str(config_path),
                       '--policy', policy, '--task', task, '--output', str(output)]
                sim = launch(cmd, ROOT, dict(os.environ, CUDA_VISIBLE_DEVICES=cfg['sim_gpu']['uuid'], PYTHONNOUSERSITE='1'),
                             batch / (task + '-launch.log'))
                current = dict(policy=policy, task=task, phase='evaluating', session=batch.parent.name,
                               sim_pid=sim.pid, server_pid=server.pid, output=str(output), argv=cmd)
                suite.write(batch / (task + '-launch.json'), current)
                started = last_completed = time.time()
                previous_count = -1
                while sim.poll() is None:
                    assert server.poll() is None, 'Server exited during evaluation'
                    gpu_check(base, cfg, policy + '/' + task)
                    suite.ingest_batch(base, policy, spec, output)
                    status = report(base, cfg, 'running', current)
                    if status['completed_episodes'] != previous_count:
                        previous_count = status['completed_episodes']
                        last_completed = time.time()
                    logs = list(output.glob('*.log')) + [batch / (task + '-launch.log')]
                    assert time.time() - max([started] + [p.stat().st_mtime for p in logs if p.exists()]) < 1200
                    assert time.time() - last_completed < 7200
                    time.sleep(15)
                rc = sim.returncode
                suite.stop(sim)
                sim = None
                suite.ingest_batch(base, policy, spec, output)
                summary = suite.read(output / 'summary.json') if (output / 'summary.json').exists() else {}
                seed = suite.retryable_batch_failure(output, rc, summary)
                if seed is not None:
                    suite.check_oracle_budget(base, policy, spec)
                    gpu_check(base, cfg, 'before oracle retry')
                    suite.write(batch / (task + '-oracle-retry.json'), dict(seed=seed,
                                prior_failures=suite.oracle_failure_history(base, policy, spec)[seed],
                                max_attempts=suite.MAX_ORACLE_ATTEMPTS, policy_results_retried=False))
                    todo.insert(index + 1, spec)
                    continue
                assert rc in (0, 1) and summary.get('complete'), (policy, task, rc, summary)
                assert all(suite.completed_record(base, policy, spec, s) is not None for s in spec['seeds'])
                print('COMPLETE', policy, task, flush=True)
            suite.stop(server)
            server = None
            time.sleep(5)
            gpu_check(base, cfg, 'stopped ' + policy, idle=True)
        status = report(base, cfg, 'validating', {})
        assert status['completed_episodes'] == status['expected_episodes']
        assert status['completed_blocks'] == status['expected_blocks']
        # Full suite validation runs centrally after checksum-verified import.
        report(base, cfg, 'episodes_complete_awaiting_central_validation', {})
    except BaseException as exc:
        traceback.print_exc()
        for proc in (sim, server):
            try:
                suite.stop(proc)
            except Exception:
                traceback.print_exc()
        report(base, cfg, 'incomplete', current, f'{type(exc).__name__}: {exc}')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'worker', 'check'))
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--policy')
    parser.add_argument('--task')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    cfg = load_config(args.config)
    base = Path(cfg['run_dir'])
    if args.command == 'run':
        return run(base, cfg, args.config.resolve())
    if args.command == 'worker':
        return worker(base, cfg, args.policy, args.task, args.output.resolve())
    check_sources(base, cfg)
    gpu_check(base, cfg, 'preflight', idle=True)
    print('Deployment source, ownership and GPU checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
