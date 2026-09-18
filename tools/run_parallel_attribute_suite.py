#!/usr/bin/env python3
"""Resume frozen Attribute-v2 with at most two model servers and two simulators.

The original evaluator, manifests and task sources remain frozen. One scheduler
owns ingestion. Model admission reserves VRAM from measured historical peaks.
"""
import argparse
import datetime
import fcntl
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import run_formal_policy_suite as formal

TASK = 'attribute_select'
MAX_PAIRS = 2
# Rounded above the historical peaks, in MiB. Four GiB remain unreserved.
MODEL_MIB = dict(xvla=4608, lingbot_va=34816, lingbot_vla=9728,
                 vlact=10240, dm05=12800, hy_vla=10240)
MODEL_ADMISSION_MIB = 44 * 1024
SIM_ADMISSION_MIB = 16 * 1024
HARD_TEMPERATURE = 86
PAUSE_TEMPERATURE = 83
RESUME_TEMPERATURE = 80


def proc_identity(pid):
    try:
        value = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if value[0] == 'Z':
            return None
        return dict(pid=pid, start_ticks=value[19],
                    argv=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[:-1])
    except FileNotFoundError:
        return None


class AdoptedProcess:
    """A verified live child retained when only its serial supervisors exit."""
    def __init__(self, pid, start_ticks):
        identity = proc_identity(pid)
        assert identity and identity['start_ticks'] == start_ticks, ('PID identity changed', pid)
        assert os.getpgid(pid) == pid, ('Not an isolated job process group', pid)
        self.pid, self.start_ticks = pid, start_ticks

    def poll(self):
        identity = proc_identity(self.pid)
        return None if identity and identity['start_ticks'] == self.start_ticks else 0

    def wait(self, timeout):
        deadline = time.monotonic() + timeout
        while self.poll() is None:
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(str(self.pid), timeout)
            time.sleep(.1)
        return 0


def stop_process(process):
    if isinstance(process, AdoptedProcess) and process.poll() is not None:
        return  # Never signal a PID that has exited or been reused.
    formal.stop(process)


def admission(policy, active_policies, gpu_rows, host_available):
    """Do not overlap model loading or admit an unsafe pair of checkpoints."""
    if len(active_policies) >= MAX_PAIRS or policy in active_policies:
        return False
    reserved = sum(MODEL_MIB[p] for p in [*active_policies, policy])
    return (reserved <= MODEL_ADMISSION_MIB
            and gpu_rows[0][1] < SIM_ADMISSION_MIB
            and gpu_rows[1][1] + MODEL_MIB[policy] <= MODEL_ADMISSION_MIB
            and max(row[3] for row in gpu_rows) < PAUSE_TEMPERATURE
            and host_available >= 12 * 1024**3)


def hardware(base, label):
    result = subprocess.run(['nvidia-smi',
        '--query-gpu=index,memory.used,memory.total,temperature.gpu,utilization.gpu',
        '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=8, check=True)
    rows = [[int(x.strip()) for x in line.split(',')] for line in result.stdout.strip().splitlines()]
    assert [r[0] for r in rows] == [0, 1], rows
    assert all(r[3] < HARD_TEMPERATURE and r[1] < r[2] * .96 for r in rows), ('GPU safety limit', rows)
    assert rows[0][1] < 20 * 1024, ('Unexpected simulator VRAM usage', rows)
    mem = {line.split(':', 1)[0]: int(line.split()[1]) * 1024
           for line in Path('/proc/meminfo').read_text().splitlines()}
    available = mem['MemAvailable']
    assert available > 2 * 1024**3, 'Host memory safety limit'
    assert formal.shutil.disk_usage(base).free > 100 * 1024**3, 'Output volume low on space'
    with (base / 'support/gpu-observations.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(time=time.time(), label=label, rows=rows,
                                    host_available_bytes=available, topology='2-server-2-sim')) + '\n')
    return rows, available


def check_sources(base):
    formal.check_sources(base)
    for name, sha in formal.read(base / 'support/parallel-source-hashes.json').items():
        assert formal.digest(ROOT / name) == sha, ('Parallel source changed', name)


def check_parent_scene(base, policy, spec, seed, instruction, obs, env, path):
    """Parent RGB/state are already shared by all policies; verdicts are not reused."""
    import numpy as np
    from policies.xvla.client import encode_proprio
    parent = Path(formal.read(base / 'plan.json')['old_run'])
    # X-VLA stores the 20-D rot6d encoding used by encode_proprio here. Other
    # adapters store 16-D quaternion EE or 14-D joint states in their NPZs.
    task = spec.get('task', TASK)
    directory = parent / 'xvla' / task
    stem = formal.prefix(task, seed)
    marker = formal.read(directory / (stem + '_provenance.json'))
    result_path = directory / (stem + '_result.json')
    initial_path = directory / (stem + '_initial_observation.npz')
    for p in (result_path, initial_path):
        assert formal.digest(p) == marker['files_sha256'][p.name], ('Parent artifact changed', p)
    record = formal.read(result_path)
    assert instruction == record['instruction'] and env.step_lim == record['step_limit'] == 400
    with np.load(initial_path) as expected:
        for camera in ('head_camera', 'left_camera', 'right_camera'):
            np.testing.assert_array_equal(obs['observation'][camera]['rgb'], expected[camera])
        np.testing.assert_allclose(encode_proprio(obs), expected['proprio'], rtol=0, atol=1e-6)
    formal.write(path('_same_host_scene.json'), dict(reference=str(directory / stem), reference_policy='xvla',
        reference_verdict_reused=False, initial_sha256=formal.digest(initial_path),
        exact_rgb=True, instruction=True, state_atol=1e-6,
        checker_version=spec['success_checker_version']))


def worker(base, policy, output):
    check_sources(base)
    module = importlib.import_module('policies.' + policy + '.eval')
    original = module.run_episode
    def gated_episode(*args, **kwargs):
        gate = base / 'support/concurrency-gate.json'
        # Only wait before a new episode, never during physics or a model request.
        while gate.exists() and policy in formal.read(gate).get('paused_policies', []):
            time.sleep(5)
        return original(*args, **kwargs)
    module.run_episode = gated_episode
    formal.check_scene = check_parent_scene
    return formal.worker(base, policy, TASK, output)


def launch(cmd, cwd, env, log):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('x') as stream:
        return subprocess.Popen(cmd, cwd=cwd, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, start_new_session=True)


def start_server(base, policy, batch):
    directory = base / 'servers' / batch.name / policy
    tail = formal.read(base / 'support/services-before-recovery.json')[policy]['argv'][1:]
    if tail[0] == '-u':
        tail = tail[1:]
    cmd = [str(formal.ENVS[policy] / 'bin/python'), '-u'] + tail
    if '--gpu' in cmd:
        cmd[cmd.index('--gpu') + 1] = '1'
    flag = '--output_dir' if policy == 'xvla' else '--output-dir'
    cmd[cmd.index(flag) + 1] = str(directory)
    cmd = [str(ROOT / value) if value.startswith('policies/') else value for value in cmd]
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='1', PYTHONNOUSERSITE='1',
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    env['PATH'] = str(formal.ENVS[policy] / 'bin') + os.pathsep + env.get('PATH', '')
    proc = launch(cmd, ROOT / 'third_party/xvla' if policy == 'xvla' else ROOT,
                  env, batch / policy / 'server.log')
    job = dict(policy=policy, batch=batch, server=proc, sim=None, output=None,
               server_directory=directory, phase='loading_server', started=time.time(), count=0,
               last_completed=time.time(), attempt=0, adopted=False)
    formal.write(batch / policy / 'server-launch.json', dict(policy=policy, server_pid=proc.pid, argv=cmd))
    return job


def start_worker(base, job):
    check_sources(base)
    spec = next(s for s in formal.read(base / 'plan.json')['tasks'] if s['task'] == TASK)
    formal.check_oracle_budget(base, job['policy'], spec)
    if job['attempt']:
        job['batch'] = base / 'batches' / (job['batch'].name.split('-retry-')[0] + f"-retry-{job['attempt']:03d}")
    output = job['batch'] / job['policy'] / TASK
    cmd = [formal.PYTHON, '-u', str(Path(__file__).resolve()), 'worker', '--run-dir', str(base),
           '--policy', job['policy'], '--output', str(output)]
    proc = launch(cmd, ROOT, dict(os.environ, CUDA_VISIBLE_DEVICES='0', PYTHONNOUSERSITE='1'),
                  job['batch'] / job['policy'] / (TASK + '-launch.log'))
    job.update(sim=proc, output=output, phase='evaluating', started=time.time(), last_completed=time.time())
    formal.write(job['batch'] / job['policy'] / (TASK + '-launch.json'),
                 dict(policy=job['policy'], task=TASK, sim_pid=proc.pid, server_pid=job['server'].pid, argv=cmd))


def public_job(job):
    return dict(policy=job['policy'], task=TASK, phase=job['phase'], server_pid=job['server'].pid,
                sim_pid=job['sim'].pid if job['sim'] else None,
                output=str(job['output']) if job['output'] else None, adopted=job['adopted'])


def run(base, adoption=None):
    lock = (base / 'scheduler.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    check_sources(base)
    plan = formal.read(base / 'plan.json')
    formal.check_active_tasks(plan['tasks'])
    spec = next(s for s in plan['tasks'] if s['task'] == TASK)
    assert spec['success_checker_version'] == 'target-only-lift-v2'
    for s in plan['tasks']:
        if s['task'] != TASK:
            assert all(formal.completed_record(base, p, s, seed) for p in formal.POLICIES for seed in s['seeds'])
    for previous in (base / 'batches').glob('*'):
        for policy in formal.POLICIES:
            formal.ingest_batch(base, policy, spec, previous / policy / TASK)
    active = {}
    if adoption:
        old = formal.read(adoption)
        policy = old['policy']
        active[policy] = dict(policy=policy, batch=Path(old['output']).parents[1],
            server=AdoptedProcess(old['server_pid'], old['server_start_ticks']),
            sim=AdoptedProcess(old['sim_pid'], old['sim_start_ticks']), output=Path(old['output']),
            server_directory=None, phase='evaluating', started=time.time(), count=0,
            last_completed=time.time(), attempt=0, adopted=True)
    # This scheduler owns every active endpoint; no independent queue may collide.
    assert all(not formal.port_open(port) or p in active for p, port in formal.PORTS.items())
    def interrupted(signum, frame):
        raise RuntimeError(f'Parallel scheduler received signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    session = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S') + '-parallel2'
    counter = 0
    paused = []
    last_source_check = 0
    try:
        while True:
            gpu_rows, available = hardware(base, 'parallel2 ' + ','.join(active))
            temperature = max(row[3] for row in gpu_rows)
            if temperature >= PAUSE_TEMPERATURE and len(active) > 1:
                paused = [next(reversed(active))]
            elif temperature <= RESUME_TEMPERATURE or len(active) <= 1:
                paused = []
            formal.write(base / 'support/concurrency-gate.json', dict(paused_policies=paused,
                         reason='Pause before next episode while GPUs cool' if paused else None))
            if time.time() - last_source_check > 60:
                check_sources(base)
                last_source_check = time.time()
            for policy, job in list(active.items()):
                assert job['server'].poll() is None, (policy, 'model server exited')
                if job['phase'] == 'loading_server':
                    if formal.port_open(formal.PORTS[policy]):
                        formal.server_identity(base, policy, job['server_directory'])
                        start_worker(base, job)
                    else:
                        assert time.time() - job['started'] < 1200, (policy, 'model load timeout')
                    continue
                formal.ingest_batch(base, policy, spec, job['output'])
                count = len(list((base / policy / TASK).glob('*_provenance.json')))
                if count != job['count'] or policy in paused:
                    job.update(count=count, last_completed=time.time())
                if job['sim'].poll() is None:
                    assert time.time() - job['last_completed'] < 7200, (policy, 'no episode completed for 2 hours')
                    logs = list(job['output'].glob('*.log'))
                    heartbeat = max([job['started']] + [p.stat().st_mtime for p in logs])
                    assert policy in paused or time.time() - heartbeat < 1200, (policy, 'no simulator heartbeat')
                    continue
                stop_process(job['sim'])
                summary_path = job['output'] / 'summary.json'
                summary = formal.read(summary_path) if summary_path.exists() else {}
                rc = job['sim'].poll()
                if isinstance(job['sim'], AdoptedProcess) and summary.get('complete') is False:
                    rc = 2  # Reparented processes have no waitpid exit status; require full error evidence below.
                seed = formal.retryable_batch_failure(job['output'], rc, summary)
                if seed is not None:
                    formal.check_oracle_budget(base, policy, spec)
                    failures = formal.oracle_failure_history(base, policy, spec)[seed]
                    formal.write(job['batch'] / policy / (TASK + '-oracle-retry.json'), dict(
                        seed=seed, prior_failed_attempts=len(failures), max_attempts=formal.MAX_ORACLE_ATTEMPTS,
                        failed_records=failures, policy_results_retried=False,
                        reason='Pre-inference oracle negative; healthy GPUs; same seed in a fresh simulator'))
                    job['attempt'] += 1
                    start_worker(base, job)
                    continue
                assert rc in (0, 1) and summary.get('complete'), (policy, rc, summary)
                assert summary['recorded_episodes'] == len(spec['seeds'])
                assert all(formal.completed_record(base, policy, spec, seed) for seed in spec['seeds'])
                stop_process(job['server'])
                del active[policy]
                print(f'COMPLETE {policy}/{TASK}: {summary["successes"]}/{len(spec["seeds"])}', flush=True)
            pending = [p for p in formal.POLICIES if p not in active and any(
                not (base / p / TASK / (formal.prefix(TASK, s) + '_provenance.json')).exists() for s in spec['seeds'])]
            # Start one checkpoint at a time. Recheck real memory after any job exits.
            gpu_rows, available = hardware(base, 'parallel2 admission')
            if not any(job['phase'] == 'loading_server' for job in active.values()):
                for policy in pending:
                    if admission(policy, list(active), gpu_rows, available):
                        formal.check_oracle_budget(base, policy, spec)
                        assert not formal.port_open(formal.PORTS[policy])
                        counter += 1
                        active[policy] = start_server(base, policy, base / 'batches' / f'{session}-{counter:03d}')
                        pending.remove(policy)
                        break
            formal.report(base, state='running', current=dict(max_servers=MAX_PAIRS, max_simulators=MAX_PAIRS,
                workers=[public_job(j) for j in active.values()], queued_policies=pending,
                paused_policies=paused, sim_gpu=0, model_gpu=1))
            if not active and not pending:
                break
            time.sleep(10)
        formal.report(base, state='validating', current={})
        formal.verify(base, require_complete=True)
        check_sources(base)
        formal.report(base, state='complete', current={})
    except BaseException as exc:
        traceback.print_exc()
        for job in active.values():
            for process in (job['sim'], job['server']):
                try:
                    stop_process(process)
                except Exception:
                    traceback.print_exc()
        formal.report(base, state='incomplete', current=dict(workers=[public_job(j) for j in active.values()]),
                      error=f'{type(exc).__name__}: {exc}')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'worker'))
    parser.add_argument('--run-dir', type=Path, default=formal.DEFAULT_RUN)
    parser.add_argument('--adopt', type=Path)
    parser.add_argument('--policy', choices=formal.POLICIES)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'worker':
        sys.exit(worker(args.run_dir.resolve(), args.policy, args.output.resolve()))
    run(args.run_dir.resolve(), args.adopt)
