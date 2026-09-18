#!/usr/bin/env python3
"""Up to three local task simulators with isolated servers on msrait-03.

The frozen evaluators, exact scene checks and final release validation are reused.
Deployment paths, transport, GPU assignments and wall-clock cooling waits differ.
"""
import argparse
import datetime
import fcntl
import importlib
import json
import os
from pathlib import Path
import shlex
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

def task_name(cfg):
    task = cfg.get('task', 'attribute_select')
    assert task in ('attribute_select', 'arm_select'), ('Unsupported rerun task', task)
    return task


class ActionCooling:
    """Cool between complete actions; never advance physics or reset a policy."""
    def __init__(self, gpu, options, path):
        self.gpu, self.path = gpu, path
        self.pause = options.get('pause_temperature_c', 80)
        self.resume = options.get('resume_temperature_c', 74)
        self.interval = options.get('check_interval_seconds', 3)
        assert 0 < self.interval <= 5
        assert self.resume < self.pause <= 81
        self.next_check = 0
        self.events = []
        self.cooling_seconds = 0.0

    def record(self, phase):
        formal.write(self.path, dict(gpu=self.gpu, phase=phase, pause_temperature_c=self.pause,
            resume_temperature_c=self.resume, cooling_seconds=self.cooling_seconds, events=self.events,
            physics_steps_during_wait=0, actions_changed=False))

    def before_action(self):
        if time.monotonic() < self.next_check:
            return
        row = selected_gpu(gpu_rows(), self.gpu)
        if row['temperature'] >= self.pause:
            started = time.monotonic()
            event = dict(started_at=time.time(), start_temperature_c=row['temperature'])
            self.events.append(event)
            self.record('cooling')
            while row['temperature'] > self.resume:
                assert time.monotonic() - started < 600, ('GPU did not cool within ten minutes', row)
                time.sleep(1)
                row = selected_gpu(gpu_rows(), self.gpu)
            elapsed = time.monotonic() - started
            self.cooling_seconds += elapsed
            event.update(finished_at=time.time(), seconds=elapsed, end_temperature_c=row['temperature'])
            self.record('running')
        self.next_check = time.monotonic() + self.interval


def cooled_episode(env, run_episode, cooling, *args, **kwargs):
    original_action = env.take_action

    def paced_action(*action_args, **action_kwargs):
        cooling.before_action()
        return original_action(*action_args, **action_kwargs)

    env.take_action = paced_action
    try:
        return run_episode(env, *args, **kwargs)
    finally:
        env.take_action = original_action
        cooling.record('episode_finished')


def validate_lanes(cfg):
    lanes = cfg['lanes']
    assert 1 <= len(lanes) <= 3, 'At most three simulator lanes'
    limit = cfg.get('max_simulators_per_gpu', 1)
    assert limit in (1, 2)
    for lane in lanes:
        peers = [other for other in lanes if other['sim_gpu'] == lane['sim_gpu']]
        assert len(peers) <= limit, 'Overlapping simulator GPUs exceed configured limit'
        assert len({other.get('sim_pci') for other in peers}) == 1, 'Inconsistent simulator PCI identity'


def model_gpu(cfg, lane_index, policy):
    return cfg.get('policy_model_gpus', {}).get(policy, cfg['lanes'][lane_index]['model_gpu'])


def model_admitted(cfg, policy, active, row):
    reserve = sum(parallel.MODEL_MIB[p] for p in active + [policy])
    shared = row['uuid'] in cfg.get('shared_model_gpus', [])
    return (policy not in active and len(active) < 2
            and reserve <= parallel.MODEL_ADMISSION_MIB
            and row['used'] + parallel.MODEL_MIB[policy] <= parallel.MODEL_ADMISSION_MIB
            and row['temperature'] < 83
            and (bool(active) or shared or (row['used'] < 2048 and row['utilization'] < 10)))


def simulator_admitted(cfg, index, jobs, rows):
    lane = cfg['lanes'][index]
    gpu = selected_gpu(rows, lane['sim_gpu'])
    peers = [j for i, j in jobs.items() if cfg['lanes'][i]['sim_gpu'] == lane['sim_gpu']]
    if not peers:
        selected_gpu(rows, lane['sim_gpu'], idle=True)
    return (len(peers) < cfg.get('max_simulators_per_gpu', 1)
            and gpu['temperature'] < lane.get('admit_temperature_c', 83)
            and gpu['used'] + 8192 <= cfg.get('sim_admission_mib', 20 * 1024))


def gpu_rows():
    result = subprocess.run(['nvidia-smi', '--query-gpu=index,uuid,pci.bus_id,memory.used,memory.total,temperature.gpu,utilization.gpu',
                             '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True, timeout=10)
    rows = []
    for line in result.stdout.splitlines():
        index, uuid, pci, used, total, temp, utilization = map(str.strip, line.split(','))
        rows.append(dict(index=int(index), uuid=uuid, pci=pci.lower(), used=int(used), total=int(total),
                         temperature=int(temp), utilization=int(utilization)))
    return rows


def selected_gpu(rows, uuid, idle=False):
    matches = [r for r in rows if r['uuid'] == uuid]
    assert len(matches) == 1, ('GPU identity missing', uuid)
    row = matches[0]
    assert row['temperature'] < 86 and row['used'] < row['total'] * .96, ('GPU limit', row)
    if idle:
        assert row['used'] < 2048 and row['utilization'] < 10, ('GPU is occupied', row)
    return row


def metadata_matches(expected, actual):
    for key, value in expected.items():
        if key not in {'created_at', 'gpu', 'source_sha256'}:
            observed = actual.get(key)
            if key == 'checkpoint' and isinstance(value, dict) and isinstance(observed, dict):
                # Independent downloads retain their timestamps in the audit.
                value = {k: v for k, v in value.items() if k != 'downloaded_at'}
                observed = {k: v for k, v in observed.items() if k != 'downloaded_at'}
            assert observed == value, ('Remote model metadata differs', key)


def load_config(path, remote=False):
    cfg = formal.read(path)
    assert socket.gethostname() == cfg['remote']['host' if remote else 'local_host']
    validate_lanes(cfg)
    assert formal.digest(Path(__file__)) == cfg['controller_sha256'], 'Controller changed'
    if not remote:
        parallel.check_sources(Path(cfg['run_dir']))
    else:
        for name, sha in cfg['remote_sources'].items():
            assert formal.digest(ROOT / name) == sha, ('Remote source changed', name)
    return cfg


def ssh_args(cfg):
    return ['ssh', '-S', cfg['remote']['socket'], '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10']


def remote_call(cfg, action, lane, policy, session=''):
    args = [cfg['remote']['python'], str(Path(cfg['remote']['repo_root']) / 'tools/run_remote_attribute_suite.py'),
            'service', '--config', cfg['remote']['config'], '--action', action, '--lane', str(lane),
            '--policy', policy, '--session', session]
    result = subprocess.run(ssh_args(cfg) + [cfg['remote']['address'], shlex.join(args)],
                            capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, ('Remote control failed', action, result.stderr[-3000:], result.stdout[-3000:])
    return json.loads(result.stdout)


def service(cfg, action, lane_index, policy, session):
    """Control only isolated processes whose saved start ticks still match."""
    with (Path(cfg['remote']['base']) / 'support/services.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return service_locked(cfg, action, lane_index, policy, session)


def service_locked(cfg, action, lane_index, policy, session):
    base = Path(cfg['remote']['base'])
    assigned_gpu = model_gpu(cfg, lane_index, policy)
    rows = gpu_rows()
    row = next(r for r in rows if r['uuid'] == assigned_gpu)
    if action != 'stop':
        selected_gpu(rows, assigned_gpu)
    path = base / 'support' / (policy + '-service.json')
    state = formal.read(path) if path.exists() else None
    identity = parallel.proc_identity(state['pid']) if state else None
    running = bool(identity and identity['start_ticks'] == state['start_ticks'])
    if running:
        assert state['policy'] == policy and state['gpu'] == assigned_gpu
    if action == 'stop':
        if running:
            parallel.stop_process(parallel.AdoptedProcess(state['pid'], state['start_ticks']))
        return dict(stopped=True, state=state)
    if action == 'start' and not running:
        active = []
        for marker in (base / 'support').glob('*-service.json'):
            other = formal.read(marker)
            live = parallel.proc_identity(other['pid'])
            if (live and live['start_ticks'] == other['start_ticks']
                    and other['gpu'] == assigned_gpu):
                active.append(other['policy'])
        row = selected_gpu(gpu_rows(), assigned_gpu)
        if not model_admitted(cfg, policy, active, row):
            return dict(running=False, ready=False, admitted=False, gpu=row, active_policies=active)
        port = cfg['remote_ports'][policy]
        assert not formal.port_open(port), ('Remote port already occupied', port)
        out = base / 'servers' / session / policy
        log = out.parent / (policy + '-server.log')
        log.parent.mkdir(parents=True, exist_ok=True)
        command = list(cfg['remote_commands'][policy])
        flag = '--output_dir' if policy == 'xvla' else '--output-dir'
        command += [flag, str(out)]
        command += ['--port', str(port)]
        if policy != 'xvla':
            command += ['--gpu', assigned_gpu]
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=assigned_gpu, PYTHONNOUSERSITE='1',
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        env['PATH'] = str(Path(command[0]).parent) + os.pathsep + env.get('PATH', '')
        with log.open('x') as stream:
            process = subprocess.Popen(command, cwd=cfg['remote_cwds'][policy], env=env,
                stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        identity = parallel.proc_identity(process.pid)
        assert identity
        state = dict(policy=policy, pid=process.pid, start_ticks=identity['start_ticks'], argv=command,
                     gpu=assigned_gpu, port=port, output=str(out), log=str(log), started=time.time(), session=session)
        formal.write(path, state)
        running = True
    assert action in ('start', 'status')
    ready = bool(running and formal.port_open(state['port']))
    metadata = None
    if ready and policy != 'xvla':
        metadata = formal.read(Path(state['output']) / 'server.json')
        metadata_matches(cfg['expected_metadata'][policy], metadata)
    return dict(running=running, ready=ready, state=state, gpu=row, metadata=metadata)


def forward(cfg, policy, action):
    value = f"127.0.0.1:{cfg['local_ports'][policy]}:127.0.0.1:{cfg['remote_ports'][policy]}"
    subprocess.run(ssh_args(cfg) + ['-o', 'ExitOnForwardFailure=yes', '-O', action, '-L', value,
                   cfg['remote']['address']], capture_output=True, text=True, check=True, timeout=15)


def worker(cfg, lane_index, policy, output):
    task = task_name(cfg)
    base = Path(cfg['run_dir'])
    lane = cfg['lanes'][lane_index]
    spec = next(s for s in formal.read(base / 'plan.json')['tasks'] if s['task'] == task)
    old = formal.read(base / 'provenance/reused' / policy / task / 'run.json')['arguments']
    module = importlib.import_module('policies.' + policy + '.eval')
    original, setup = module.run_episode, module.setup_episode
    retained = {s: r for s in spec['seeds'] if (r := formal.completed_record(base, policy, spec, s)) is not None}
    heartbeat = output.parent / (task + '-worker-state.json')

    def resumed(env, config, client, args, seed, split, directory, block=None):
        if seed in retained:
            return retained[seed].copy()
        formal.write(heartbeat, dict(phase='between_episodes', seed=seed, time=time.time()))
        gate = base / 'support/remote-concurrency-gate.json'
        while gate.exists() and lane_index in formal.read(gate).get('paused_lanes', []):
            time.sleep(3)
        formal.write(heartbeat, dict(phase='episode', seed=seed, time=time.time()))
        if cfg.get('action_cooling'):
            cooling = ActionCooling(lane['sim_gpu'], cfg['action_cooling'],
                directory / (formal.prefix(task, seed) + '_thermal_pacing.json'))
            return cooled_episode(env, original, cooling, config, client, args, seed, split, directory, block=block)
        return original(env, config, client, args, seed, split, directory, block=block)

    def checked_setup(env, config, args, seed, split, record, path):
        instruction, obs = setup(env, config, args, seed, split, record, path)
        parallel.check_parent_scene(base, policy, spec, seed, instruction, obs, env, path)
        formal.write(path('_execution_host.json'), dict(sim_host=socket.gethostname(), sim_gpu=lane['sim_gpu'],
            model_host=cfg['remote']['host'], model_gpu=model_gpu(cfg, lane_index, policy), transport='SSH loopback forward',
            controller_sha256=cfg['controller_sha256'], action_cooling=cfg.get('action_cooling')))
        return instruction, obs

    argv = [str(module.__file__), '--task', task, '--task-config', spec['task_config'],
            '--seed-manifest', str(base / 'manifests' / spec['manifest']), '--blocks', str(formal.block_count(spec)),
            '--instruction-type', 'unseen', '--sim-gpu', lane['sim_gpu'], '--output-dir', str(output),
            '--server-url', old['server_url'].rsplit(':', 1)[0] + ':' + str(cfg['local_ports'][policy]),
            '--request-timeout', str(old['request_timeout'])]
    for option in ('checkpoint', 'checkpoint_revision', 'feedback', 'gripper_threshold', 'denoising_steps'):
        if option in old:
            argv += ['--' + option.replace('_', '-'), str(old[option])]
    formal.write(output.parent / (task + '-resume.json'), dict(skipped_seeds=list(retained), argv=argv,
        canonical_directory=str(base / policy / task), lane=lane))
    os.environ['CUDA_VISIBLE_DEVICES'] = lane['sim_gpu']
    from tools.sim_device import pin_renderer
    device = pin_renderer()
    assert device.lower() == lane['sim_pci'].lower(), ('Renderer on wrong device', device)
    module.run_episode, module.setup_episode = resumed, checked_setup
    sys.argv = argv
    return module.main()


def scene_probe(cfg, lane_index, output):
    """Run setup only on a selected local GPU, retaining exact scene evidence."""
    task = task_name(cfg)
    from types import SimpleNamespace
    base, lane = Path(cfg['run_dir']), cfg['lanes'][lane_index]
    selected_gpu(gpu_rows(), lane['sim_gpu'], idle=True)
    os.environ['CUDA_VISIBLE_DEVICES'] = lane['sim_gpu']
    from tools.sim_device import pin_renderer
    assert pin_renderer().lower() == lane['sim_pci'].lower()
    from policies.xvla.eval import load_task
    from policies.evaluation import setup_episode
    from if_benchmark.seed_contracts import describe_seed
    spec = next(s for s in formal.read(base / 'plan.json')['tasks'] if s['task'] == task)
    output.mkdir(parents=True, exist_ok=False)
    env, config = load_task(ROOT / 'third_party/robotwin', task, spec['task_config'])
    args = SimpleNamespace(task=task, task_config=spec['task_config'], robotwin_dir=ROOT / 'third_party/robotwin')
    rows = []
    for seed in spec['seeds'][:8]:
        def path(suffix):
            return output / (formal.prefix(task, seed) + suffix)
        try:
            record = dict(mode=describe_seed(task, seed).mode)
            instruction, obs = setup_episode(env, config, args, seed, 'unseen', record, path)
            parallel.check_parent_scene(base, 'xvla', spec, seed, instruction, obs, env, path)
            rows.append(dict(seed=seed, exact_rgb=True, state_atol=1e-6, instruction_equal=True))
            formal.write(output / 'progress.json', rows)
            print('SCENE_MATCH', seed, flush=True)
        finally:
            env.close_env()
    formal.write(output / 'validation.json', dict(complete=True, rows=rows, lane=lane,
        source_hashes_sha256=formal.digest(base / 'support/source-hashes.json')))


def run(cfg, config_path):
    task = task_name(cfg)
    base = Path(cfg['run_dir'])
    lock = (base / 'scheduler.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    proof = formal.read(cfg['scene_probe'])
    assert proof['complete'] and proof['lane'] == cfg['lanes'][1]
    assert proof['source_hashes_sha256'] == formal.digest(base / 'support/source-hashes.json')
    plan = formal.read(base / 'plan.json')
    formal.check_active_tasks(plan['tasks'])
    spec = next(s for s in plan['tasks'] if s['task'] == task)
    for other in plan['tasks']:
        if other['task'] != task:
            assert all(formal.completed_record(base, p, other, seed)
                       for p in formal.POLICIES for seed in other['seeds']), ('Missing reused task', other['task'])
    for batch in (base / 'batches').glob('*'):
        for policy in formal.POLICIES:
            formal.ingest_batch(base, policy, spec, batch / policy / task)
    pending = [p for p in formal.POLICIES if any(not formal.completed_record(base, p, spec, s) for s in spec['seeds'])]
    session = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S-remote03')
    jobs, paused = {}, []
    last_source_check = 0

    def interrupted(signum, frame):
        raise RuntimeError(f'Remote scheduler received signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)

    def launch_worker(job):
        policy, index = job['policy'], job['lane']
        formal.check_oracle_budget(base, policy, spec)
        parallel.check_sources(base)
        batch = base / 'batches' / f"{session}-lane{index}-{job['attempt']:03d}" / policy
        output, log = batch / task, batch / (task + '-launch.log')
        batch.mkdir(parents=True, exist_ok=True)
        command = [formal.PYTHON, '-u', str(Path(__file__)), 'worker', '--config', str(config_path),
                   '--lane', str(index), '--policy', policy, '--output', str(output)]
        with log.open('x') as stream:
            process = subprocess.Popen(command, cwd=ROOT, env=dict(os.environ, PYTHONNOUSERSITE='1'),
                stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        job.update(sim=process, output=output, phase='evaluating', started=time.time(), last_completed=time.time(), count=-1)
        formal.write(batch / (task + '-launch.json'), dict(argv=command, sim_pid=process.pid, lane=index,
                     server_host=cfg['remote']['host'], server=job['server']))

    def public(job):
        return dict(policy=job['policy'], task=task, phase=job['phase'], lane=job['lane'],
            sim_pid=job['sim'].pid if job.get('sim') else None, sim_gpu=cfg['lanes'][job['lane']]['sim_gpu'],
            server_host=cfg['remote']['host'], server_pid=job['server']['state']['pid'],
            model_gpu=job['server']['state']['gpu'],
            output=str(job.get('output', '')))

    try:
        while pending or jobs:
            rows = gpu_rows()
            assert formal.shutil.disk_usage(base).free > 100 * 1024**3
            for index, lane in enumerate(cfg['lanes']):
                gpu = selected_gpu(rows, lane['sim_gpu'])
                if gpu['temperature'] >= lane.get('pause_temperature_c', 83) and index not in paused:
                    paused.append(index)
                elif gpu['temperature'] <= lane.get('resume_temperature_c', 78) and index in paused:
                    paused.remove(index)
            formal.write(base / 'support/remote-concurrency-gate.json', dict(paused_lanes=paused))
            with (base / 'support/remote-gpu-observations.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(time=time.time(), local=rows, paused_lanes=paused,
                    controller_sha256=cfg['controller_sha256'])) + '\n')
            if time.time() - last_source_check > 60:
                load_config(config_path)
                last_source_check = time.time()
            for index, job in list(jobs.items()):
                policy = job['policy']
                health = remote_call(cfg, 'status', index, policy)
                assert health['running'], ('Remote server exited', policy, health)
                job['server'] = health
                if job['phase'] == 'loading_server':
                    assert time.time() - job['started'] < 1200, ('Remote model load timeout', policy)
                    if health['ready']:
                        forward(cfg, policy, 'forward')
                        job['forward'] = True
                        formal.write(base / 'servers' / session / policy / 'remote-service.json', health)
                        launch_worker(job)
                    continue
                assert health['ready'], ('Model endpoint disappeared', policy)
                formal.ingest_batch(base, policy, spec, job['output'])
                count = len(list((base / policy / task).glob('*_provenance.json')))
                if count != job['count'] or index in paused:
                    job.update(count=count, last_completed=time.time())
                if job['sim'].poll() is None:
                    assert time.time() - job['last_completed'] < 7200, ('No completed episode', policy)
                    logs = list(job['output'].glob('*.log'))
                    heartbeat = max([job['started']] + [p.stat().st_mtime for p in logs])
                    assert index in paused or time.time() - heartbeat < 1200, ('Simulator stalled', policy)
                    continue
                summary = formal.read(job['output'] / 'summary.json') if (job['output'] / 'summary.json').exists() else {}
                seed = formal.retryable_batch_failure(job['output'], job['sim'].returncode, summary)
                if seed is not None:
                    formal.check_oracle_budget(base, policy, spec)
                    failures = formal.oracle_failure_history(base, policy, spec)[seed]
                    formal.write(job['output'].parent / (task + '-oracle-retry.json'), dict(seed=seed,
                        prior_failed_attempts=len(failures), max_attempts=formal.MAX_ORACLE_ATTEMPTS,
                        failed_records=failures, policy_results_retried=False,
                        reason='Pre-inference oracle negative; retry the same seed in a fresh simulator'))
                    job['attempt'] += 1
                    launch_worker(job)
                    continue
                assert job['sim'].returncode in (0, 1) and summary.get('complete'), (policy, job['sim'].returncode, summary)
                assert summary['recorded_episodes'] == len(spec['seeds'])
                assert all(formal.completed_record(base, policy, spec, s) for s in spec['seeds'])
                remote_call(cfg, 'stop', index, policy)
                forward(cfg, policy, 'cancel')
                del jobs[index]
                print('COMPLETE', policy, summary['successes'], flush=True)
            if not any(j['phase'] == 'loading_server' for j in jobs.values()):
                for index in range(len(cfg['lanes'])):
                    if index not in jobs and index not in paused and pending:
                        if not simulator_admitted(cfg, index, jobs, gpu_rows()):
                            continue
                        for policy in list(pending):
                            health = remote_call(cfg, 'start', index, policy, session)
                            if not health['running']:
                                continue
                            pending.remove(policy)
                            jobs[index] = dict(policy=policy, lane=index, server=health, phase='loading_server',
                                               started=time.time(), attempt=0, forward=False, sim=None)
                            break
                        if index in jobs:
                            break
            formal.report(base, state='running', current=dict(workers=[public(j) for j in jobs.values()],
                queued_policies=pending, paused_lanes=paused, max_servers=len(cfg['lanes']), max_simulators=len(cfg['lanes']),
                model_host=cfg['remote']['host'], sim_host=socket.gethostname()))
            if jobs or pending:
                time.sleep(10)
        formal.report(base, state='validating', current={})
        formal.verify(base, require_complete=True)
        load_config(config_path)
        formal.report(base, state='complete', current={})
    except BaseException as exc:
        traceback.print_exc()
        for index, job in jobs.items():
            formal.stop(job.get('sim'))
            try:
                remote_call(cfg, 'stop', index, job['policy'])
                if job['forward']:
                    forward(cfg, job['policy'], 'cancel')
            except Exception:
                traceback.print_exc()
        formal.report(base, state='incomplete', current=dict(workers=[public(j) for j in jobs.values()]), error=str(exc))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['service', 'worker', 'probe', 'run'])
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--lane', type=int, choices=[0, 1, 2])
    parser.add_argument('--policy', choices=formal.POLICIES)
    parser.add_argument('--action', choices=['start', 'status', 'stop'])
    parser.add_argument('--session', default='')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    cfg = load_config(args.config, remote=args.command == 'service')
    if args.command == 'service':
        print(json.dumps(service(cfg, args.action, args.lane, args.policy, args.session)))
    elif args.command == 'worker':
        sys.exit(worker(cfg, args.lane, args.policy, args.output))
    elif args.command == 'probe':
        scene_probe(cfg, args.lane, args.output)
    else:
        run(cfg, args.config)
