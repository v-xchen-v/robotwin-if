#!/usr/bin/env python3
"""Split a frozen policy rerun across independent model/simulator pairs.

Each slot owns explicit seeds and a separately identified model endpoint. The
original manifest, evaluator, scene checks, action pacing and artifact validator
are reused without modifying their frozen sources.
"""
import argparse
import datetime
import fcntl
import importlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import run_formal_policy_suite as formal
from tools import run_parallel_attribute_suite as parallel
from tools import run_remote_attribute_suite as remote


def validate_partition(slots, seeds, pending):
    """Reject overlap, missing pending seeds and unexpected policy/seed IDs."""
    assert 1 <= len(slots) <= 3
    assert len({s['id'] for s in slots}) == len(slots)
    assert len({s['lane'] for s in slots}) == len(slots)
    assigned = set()
    for slot in slots:
        assert slot['policy'] in formal.POLICIES
        assert slot['lane'] in (0, 1, 2)
        assert slot['seeds'] and slot['seeds'] == sorted(set(slot['seeds']))
        assert set(slot['seeds']) <= set(seeds)
        keys = {(slot['policy'], seed) for seed in slot['seeds']}
        assert not assigned.intersection(keys), 'Overlapping shard seeds'
        assigned.update(keys)
    assert set(pending) <= assigned, 'Pending episodes have no shard owner'


def split_remaining(seeds, completed, block_size=2):
    """Balance pending episodes without splitting a manifest block across slots."""
    assert len(seeds) % block_size == 0
    result = [[], []]
    for start in range(0, len(seeds), block_size):
        block = [s for s in seeds[start:start + block_size] if s not in completed]
        if block:
            index = min(range(2), key=lambda i: len(result[i]))
            result[index].extend(block)
    return result


def select_shard(original, args, assigned):
    seeds, manifest, split = original(args)
    assert set(assigned) <= set(seeds)
    return [s for s in seeds if s in set(assigned)], manifest, split


def load_config(path):
    cfg = formal.read(path)
    assert formal.digest(Path(__file__)) == cfg['controller_sha256']
    for name, sha in formal.read(path.parent / 'source-hashes.json').items():
        assert formal.digest(ROOT / name) == sha, ('Shard deployment changed', name)
    base = Path(cfg['run_dir'])
    parallel.check_sources(base)
    for slot in cfg['slots']:
        path = Path(slot['config'])
        assert formal.digest(path) == slot['config_sha256']
        child = remote.load_config(path)
        assert child['run_dir'] == str(base)
        assert remote.task_name(child) == cfg['task']
    return cfg


def worker(cfg, slot, output):
    child = remote.load_config(Path(slot['config']))
    base = Path(cfg['run_dir'])
    spec = next(s for s in formal.read(base / 'plan.json')['tasks'] if s['task'] == cfg['task'])
    module = importlib.import_module('policies.' + slot['policy'] + '.eval')
    select, episode, setup = module.select_seeds, module.run_episode, module.setup_episode
    from if_benchmark.seed_contracts import contract_for_seeds
    block_size = contract_for_seeds(spec['task'], spec['seeds']).block_size
    assigned = set(slot['seeds'])

    def selected(args):
        return select_shard(select, args, slot['seeds'])

    def canonical_episode(env, config, client, args, seed, split, directory, block=None):
        assert seed in assigned, ('Seed belongs to another shard', seed)
        return episode(env, config, client, args, seed, split, directory,
                       block=spec['seeds'].index(seed) // block_size)

    def recorded_setup(env, config, args, seed, split, record, path):
        result = setup(env, config, args, seed, split, record, path)
        formal.write(path('_execution_shard.json'), dict(slot=slot['id'], seeds=slot['seeds'],
            controller_sha256=cfg['controller_sha256'], slot_config_sha256=slot['config_sha256'],
            original_manifest_unchanged=True, formal_block=spec['seeds'].index(seed) // block_size))
        return result

    module.select_seeds, module.run_episode, module.setup_episode = selected, canonical_episode, recorded_setup
    try:
        return remote.worker(child, slot['lane'], slot['policy'], output)
    finally:
        module.select_seeds, module.run_episode, module.setup_episode = select, episode, setup


def run(cfg, config_path):
    base, task = Path(cfg['run_dir']), cfg['task']
    lock = (base / 'scheduler.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    plan = formal.read(base / 'plan.json')
    formal.check_active_tasks(plan['tasks'])
    spec = next(s for s in plan['tasks'] if s['task'] == task)
    for other in plan['tasks']:
        if other['task'] != task:
            assert all(formal.completed_record(base, p, other, seed)
                       for p in formal.POLICIES for seed in other['seeds'])
    for batch in (base / 'batches').glob('*'):
        for policy in formal.POLICIES:
            formal.ingest_batch(base, policy, spec, batch / policy / task)
    missing = {(p, s) for p in formal.POLICIES for s in spec['seeds']
               if formal.completed_record(base, p, spec, s) is None}
    validate_partition(cfg['slots'], spec['seeds'], missing)
    children = {s['id']: remote.load_config(Path(s['config'])) for s in cfg['slots']}
    endpoints = [(c['remote']['address'], c['remote_ports'][s['policy']])
                 for s in cfg['slots'] for c in [children[s['id']]]]
    ports = [children[s['id']]['local_ports'][s['policy']] for s in cfg['slots']]
    assert len(set(endpoints)) == len(endpoints), 'Model clients must have independent servers'
    assert len(set(ports)) == len(ports)
    lanes = [None] * 3
    for s in cfg['slots']:
        lanes[s['lane']] = children[s['id']]['lanes'][s['lane']]
    remote.validate_lanes(dict(lanes=[lane for lane in lanes if lane], max_simulators_per_gpu=2))
    jobs, paused = {}, []
    pending = [s for s in cfg['slots'] if any((s['policy'], seed) in missing for seed in s['seeds'])]
    session = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S-sharded')
    last_check = 0

    def interrupted(signum, frame):
        raise RuntimeError(f'Shard scheduler received signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)

    def launch(job):
        slot = job['slot']
        parallel.check_sources(base)
        formal.check_oracle_budget(base, slot['policy'], spec)
        batch = base / 'batches' / f"{session}-{slot['id']}-{job['attempt']:03d}" / slot['policy']
        batch.mkdir(parents=True, exist_ok=False)
        output = batch / task
        command = [formal.PYTHON, '-u', str(Path(__file__).resolve()), 'worker',
                   '--config', str(config_path), '--slot', slot['id'], '--output', str(output)]
        with (batch / (task + '-launch.log')).open('x') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=dict(os.environ, PYTHONNOUSERSITE='1'),
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        job.update(sim=process, output=output, started=time.time(), last_completed=time.time(),
                   count=-1, phase='evaluating')
        formal.write(batch / (task + '-launch.json'), dict(argv=command, sim_pid=process.pid,
            slot=slot, server=job['server'], controller_sha256=cfg['controller_sha256']))

    def public(job):
        slot, server = job['slot'], job['server']['state']
        return dict(policy=slot['policy'], task=task, shard=slot['id'], assigned_seeds=slot['seeds'],
            phase=job['phase'], lane=slot['lane'], sim_pid=job['sim'].pid if job.get('sim') else None,
            sim_gpu=lanes[slot['lane']]['sim_gpu'], server_host=children[slot['id']]['remote']['host'],
            server_pid=server['pid'], model_gpu=server['gpu'], output=str(job.get('output', '')))

    try:
        while pending or jobs:
            rows = remote.gpu_rows()
            assert formal.shutil.disk_usage(base).free > 100 * 1024**3
            for index, lane in enumerate(lanes):
                if lane is None:
                    continue
                gpu = remote.selected_gpu(rows, lane['sim_gpu'])
                if gpu['temperature'] >= lane.get('pause_temperature_c', 83) and index not in paused:
                    paused.append(index)
                elif gpu['temperature'] <= lane.get('resume_temperature_c', 78) and index in paused:
                    paused.remove(index)
            formal.write(base / 'support/remote-concurrency-gate.json', dict(paused_lanes=paused))
            with (base / 'support/remote-gpu-observations.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(time=time.time(), local=rows, paused_lanes=paused,
                    controller_sha256=cfg['controller_sha256'], topology='policy-shards')) + '\n')
            if time.time() - last_check > 60:
                load_config(config_path)
                last_check = time.time()
            for sid, job in list(jobs.items()):
                slot, child = job['slot'], children[sid]
                health = remote.remote_call(child, 'status', slot['lane'], slot['policy'])
                assert health['running'], ('Remote server exited', sid, health)
                job['server'] = health
                if job['phase'] == 'loading_server':
                    assert time.time() - job['started'] < 1200, ('Model load timeout', sid)
                    if health['ready']:
                        if not formal.port_open(child['local_ports'][slot['policy']]):
                            remote.forward(child, slot['policy'], 'forward')
                        else:
                            assert slot.get('adopt_forward'), ('Unexpected occupied local port', sid)
                        job['forward'] = True
                        formal.write(base / 'servers' / session / sid / 'remote-service.json', health)
                        launch(job)
                    continue
                assert health['ready'], ('Model endpoint disappeared', sid)
                formal.ingest_batch(base, slot['policy'], spec, job['output'])
                count = sum(formal.completed_record(base, slot['policy'], spec, s) is not None for s in slot['seeds'])
                if count != job['count'] or slot['lane'] in paused:
                    job.update(count=count, last_completed=time.time())
                if job['sim'].poll() is None:
                    assert time.time() - job['last_completed'] < 7200, ('No completed episode', sid)
                    heartbeat = max([job['started']] + [p.stat().st_mtime for p in job['output'].glob('*.log')])
                    assert slot['lane'] in paused or time.time() - heartbeat < 1200, ('Simulator stalled', sid)
                    continue
                summary_path = job['output'] / 'summary.json'
                summary = formal.read(summary_path) if summary_path.exists() else {}
                seed = formal.retryable_batch_failure(job['output'], job['sim'].returncode, summary)
                if seed is not None:
                    assert seed in slot['seeds']
                    formal.check_oracle_budget(base, slot['policy'], spec)
                    failures = formal.oracle_failure_history(base, slot['policy'], spec)[seed]
                    formal.write(job['output'].parent / (task + '-oracle-retry.json'), dict(seed=seed,
                        prior_failed_attempts=len(failures), max_attempts=formal.MAX_ORACLE_ATTEMPTS,
                        failed_records=failures, policy_results_retried=False,
                        reason='Pre-inference oracle negative; same seed, fresh simulator, same shard'))
                    job['attempt'] += 1
                    launch(job)
                    continue
                assert job['sim'].returncode in (0, 1) and summary.get('complete'), (sid, summary)
                assert summary['recorded_episodes'] == len(slot['seeds'])
                assert count == len(slot['seeds'])
                remote.remote_call(child, 'stop', slot['lane'], slot['policy'])
                remote.forward(child, slot['policy'], 'cancel')
                del jobs[sid]
                print('COMPLETE SHARD', sid, count, flush=True)
            if not any(j['phase'] == 'loading_server' for j in jobs.values()):
                for slot in list(pending):
                    index, child = slot['lane'], children[slot['id']]
                    gpu = remote.selected_gpu(remote.gpu_rows(), lanes[index]['sim_gpu'])
                    peers = [j for j in jobs.values() if lanes[j['slot']['lane']]['sim_gpu'] == gpu['uuid']]
                    if not peers:
                        remote.selected_gpu(remote.gpu_rows(), gpu['uuid'], idle=True)
                    if len(peers) >= 2 or gpu['temperature'] >= 78 or gpu['used'] + 8192 > 20480:
                        continue
                    health = remote.remote_call(child, 'start', index, slot['policy'], session)
                    if not health['running']:
                        continue
                    pending.remove(slot)
                    jobs[slot['id']] = dict(slot=slot, server=health, phase='loading_server',
                        started=time.time(), attempt=0, forward=False, sim=None)
                    break
            formal.report(base, state='running', current=dict(workers=[public(j) for j in jobs.values()],
                queued_shards=[s['id'] for s in pending], paused_lanes=paused,
                max_servers=3, max_simulators=3, model_host='msrait-03', sim_host=socket.gethostname()))
            if jobs or pending:
                time.sleep(10)
        formal.report(base, state='validating', current={})
        formal.verify(base, require_complete=True)
        load_config(config_path)
        formal.report(base, state='complete', current={})
    except BaseException as exc:
        traceback.print_exc()
        for sid, job in jobs.items():
            formal.stop(job.get('sim'))
            try:
                slot, child = job['slot'], children[sid]
                remote.remote_call(child, 'stop', slot['lane'], slot['policy'])
                if job['forward']:
                    remote.forward(child, slot['policy'], 'cancel')
            except Exception:
                traceback.print_exc()
        formal.report(base, state='incomplete', current=dict(workers=[public(j) for j in jobs.values()]), error=str(exc))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run', 'worker'])
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--slot')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command == 'worker':
        sys.exit(worker(config, next(s for s in config['slots'] if s['id'] == args.slot), args.output))
    run(config, args.config)
