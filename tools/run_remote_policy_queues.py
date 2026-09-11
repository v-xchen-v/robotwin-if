#!/usr/bin/env python3
"""Two isolated local simulators, each connected to one remote model server.

Keeps the frozen evaluators and source contracts intact. One central scheduler
owns all remaining policy/task pairs, immutable result imports and retry budgets.
SSH forwards expose remote servers only on localhost. Inference/physics settings
and per-episode exact initial image checks are unchanged.
"""
import argparse
import copy
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
from tools import run_formal_policy_suite as suite
from tools import run_formal_policy_shard as shard


def config(path):
    cfg = suite.read(path)
    assert len(cfg['lanes']) == 2
    for role in ('sim_gpu', 'model_gpu'):
        assert len({lane[role]['uuid'] for lane in cfg['lanes']}) == 2
    assert len(cfg['policies']) == len(set(cfg['policies']))
    assert set(cfg['policies']) <= set(suite.POLICIES)
    assert cfg['policies'][0] == 'lingbot_va'
    assert 'grasp_cube_approach' not in cfg['tasks']
    return cfg


def check_sources(base, cfg):
    suite.check_sources(base)
    for name, sha in cfg['code_sha256'].items():
        assert suite.digest(ROOT / name) == sha, ('Queue code changed', name)


def gpu_rows():
    proc = subprocess.run(['nvidia-smi', '--query-gpu=index,uuid,pci.bus_id,memory.used,memory.total,temperature.gpu,utilization.gpu',
                           '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=8, check=True)
    return [list(map(str.strip, row.split(','))) for row in proc.stdout.splitlines()]


def check_gpu(rows, device, *, simulator=False, idle=False):
    matches = [r for r in rows if r[1] == device['uuid']]
    assert len(matches) == 1, ('GPU missing', device)
    row = matches[0]
    assert int(row[0]) == device['index'] and row[2].lower().endswith(device['pci'][4:].lower())
    used, total, temp, utilization = map(int, row[3:])
    assert temp < 87 and used < total * .96, ('GPU threshold', row)
    if simulator:
        assert used < 24576, ('Simulator memory threshold', row)
    if idle:
        assert used < 2048 and utilization < 10, ('GPU is not idle', row)
    return row


def alive(pid, start_ticks=None):
    try:
        stat = Path(f'/proc/{pid}/stat').read_text().split()
        return stat[2] != 'Z' and (start_ticks is None or stat[21] == start_ticks)
    except FileNotFoundError:
        return False


def service(cfg, request):
    """Short remote control command. Only stop the recorded owned process group."""
    assert socket.gethostname() == cfg['remote']['host']
    base = Path(cfg['remote']['run_dir'])
    lane = cfg['lanes'][request['lane']]
    state_path = base / 'remote-services' / (lane['id'] + '.json')
    state = suite.read(state_path) if state_path.exists() else None
    action = request['action']
    if action == 'start':
        assert not state or not alive(state['pid'], state['start_ticks']), 'Lane already has a server'
        check_sources(base, cfg)
        check_gpu(gpu_rows(), lane['model_gpu'], idle=True)
        policy = request['policy']
        assert policy in cfg['policies']
        assert not suite.port_open(suite.PORTS[policy]), 'Model port already occupied'
        deploy = suite.read(base / 'deployment/msrait-03.json')
        deploy['model_gpu'] = lane['model_gpu']
        directory = base / 'servers' / request['session'] / lane['id'] / policy
        cmd = shard.server_command(base, deploy, policy, directory)
        log = base / 'remote-services' / request['session'] / lane['id'] / (policy + '.log')
        log.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=lane['model_gpu']['uuid'], PYTHONNOUSERSITE='1',
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        env['PATH'] = str(Path(deploy['envs'][policy]) / 'bin') + os.pathsep + env.get('PATH', '')
        with log.open('x') as stream:
            proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                    stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        state = dict(pid=proc.pid, start_ticks=Path(f'/proc/{proc.pid}/stat').read_text().split()[21],
                     policy=policy, session=request['session'], directory=str(directory), log=str(log),
                     argv=cmd, model_gpu=lane['model_gpu'], created_at=time.time())
        suite.write(state_path, state)
    elif action == 'stop':
        if state and alive(state['pid'], state['start_ticks']):
            assert state['session'] == request['session'], 'Refuse to stop another session'
            cmdline = Path(f"/proc/{state['pid']}/cmdline").read_bytes().decode().split('\0')
            assert state['directory'] in cmdline and os.getpgid(state['pid']) == state['pid']
            for sig in (signal.SIGTERM, signal.SIGKILL):
                os.killpg(state['pid'], sig)
                deadline = time.monotonic() + 12
                while alive(state['pid'], state['start_ticks']) and time.monotonic() < deadline:
                    time.sleep(.2)
                if not alive(state['pid'], state['start_ticks']):
                    break
            assert not alive(state['pid'], state['start_ticks']), 'Server did not stop'
        return dict(stopped=True, state=state)
    else:
        assert action == 'status'
    running = bool(state and alive(state['pid'], state['start_ticks']))
    ready = bool(running and suite.port_open(suite.PORTS[state['policy']]))
    row = check_gpu(gpu_rows(), lane['model_gpu'])
    metadata = None
    if ready:
        deploy = suite.read(base / 'deployment/msrait-03.json')
        shard.server_identity(base, deploy, state['policy'], Path(state['directory']))
        metadata = suite.read(Path(state['directory']) / 'server.json')
    return dict(running=running, ready=ready, state=state, gpu=row, metadata=metadata)


def ssh_args(cfg):
    return ['ssh', '-S', cfg['remote']['socket'], '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10']


def remote(cfg, request):
    command = shlex.join([cfg['remote']['python'], str(Path(cfg['remote']['repo_root']) / 'tools/run_remote_policy_queues.py'),
                          'service', '--config', cfg['remote']['config']])
    proc = subprocess.run(ssh_args(cfg) + [cfg['remote']['address'], command],
                          input=json.dumps(request), capture_output=True, text=True, timeout=45)
    assert proc.returncode == 0, ('Remote control failed', proc.stderr[-4000:])
    return json.loads(proc.stdout)


def tunnel(cfg, policy, action):
    local = cfg['port_offset'] + suite.PORTS[policy]
    forward = f'127.0.0.1:{local}:127.0.0.1:{suite.PORTS[policy]}'
    subprocess.run(ssh_args(cfg) + ['-o', 'ExitOnForwardFailure=yes', '-O', action, '-L', forward,
                                   cfg['remote']['address']], check=True, capture_output=True, text=True, timeout=15)
    return local


def worker(cfg, lane_index, policy, task, output):
    assert socket.gethostname() == cfg['host']
    assert policy in cfg['policies'] and task in cfg['tasks']
    base = Path(cfg['run_dir']); lane = cfg['lanes'][lane_index]
    check_sources(base, cfg)
    spec = next(s for s in suite.read(base / 'plan.json')['tasks'] if s['task'] == task)
    old = suite.read(base / 'provenance/reused' / policy / task / 'run.json')['arguments']
    module = importlib.import_module('policies.' + policy + '.eval')
    original, setup = module.run_episode, module.setup_episode
    retained = {s: r for s in spec['seeds'] if (r := suite.completed_record(base, policy, spec, s)) is not None}

    def resume(env, config, client, args, seed, split, directory, block=None):
        if seed in retained:
            return retained[seed].copy()
        if (base / 'queues' / 'STOP_AFTER_EPISODE').exists():
            raise RuntimeError('Operator requested a stop at the episode boundary')
        return original(env, config, client, args, seed, split, directory, block=block)

    def guarded_setup(env, config, args, seed, split, record, path):
        instruction, obs = setup(env, config, args, seed, split, record, path)
        shard.check_scene(base, cfg, policy, spec, seed, instruction, obs, env, path)
        suite.write(path('_execution_host.json'), dict(sim_host=cfg['host'], sim_gpu=lane['sim_gpu'],
                    model_host=cfg['remote']['host'], model_gpu=lane['model_gpu'], lane=lane['id']))
        return instruction, obs

    module.run_episode, module.setup_episode = resume, guarded_setup
    port = cfg['port_offset'] + suite.PORTS[policy]
    server_url = old['server_url'].rsplit(':', 1)[0] + ':' + str(port)
    argv = [str(module.__file__), '--task', task, '--task-config', spec['task_config'],
            '--seed-manifest', str(base / 'manifests' / spec['manifest']), '--blocks', '12',
            '--instruction-type', 'unseen', '--sim-gpu', lane['sim_gpu']['uuid'], '--output-dir', str(output),
            '--server-url', server_url, '--request-timeout', str(old['request_timeout']),
            '--oracle-cache-dir', str(base / 'oracle-cache'), '--render-sync', 'observation']
    for option in ('checkpoint', 'checkpoint_revision', 'feedback', 'gripper_threshold', 'denoising_steps'):
        if option in old:
            argv += ['--' + option.replace('_', '-'), str(old[option])]
    suite.write(output.parent / (task + '-resume.json'), dict(skipped_seeds=list(retained), argv=argv,
                canonical_directory=str(base / policy / task), lane=lane))
    os.environ['CUDA_VISIBLE_DEVICES'] = lane['sim_gpu']['uuid']
    from tools.sim_device import pin_renderer
    assert pin_renderer().lower() == lane['sim_gpu']['pci'].lower()
    sys.argv = argv
    return module.main()


def scene_probe(cfg, output):
    """Preflight both modes of six tasks on GPU 1, against committed GPU 0 images."""
    assert socket.gethostname() == cfg['host']
    base = Path(cfg['run_dir']); lane = cfg['lanes'][1]
    check_sources(base, cfg)
    check_gpu(gpu_rows(), lane['sim_gpu'], simulator=True, idle=True)
    os.environ['CUDA_VISIBLE_DEVICES'] = lane['sim_gpu']['uuid']
    from tools.sim_device import pin_renderer
    assert pin_renderer().lower() == lane['sim_gpu']['pci'].lower()
    from types import SimpleNamespace
    from policies.xvla.eval import load_task
    from policies.evaluation import prepare_evaluation, setup_episode
    from if_benchmark.seed_contracts import describe_seed
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for spec in suite.read(base / 'plan.json')['tasks']:
        if spec['task'] not in cfg['tasks']:
            continue
        task = spec['task']
        env, config = load_task(ROOT / 'third_party/robotwin', task, spec['task_config'])
        args = SimpleNamespace(task=task, task_config=spec['task_config'], render_sync='observation',
                               no_oracle_cache=False, oracle_cache_dir=base/'oracle-cache',
                               robotwin_dir=ROOT/'third_party/robotwin')
        config['policy_name'] = 'vlact'
        prepare_evaluation(env, config, args)
        for seed in spec['seeds'][:2]:
            def path(suffix):
                return output / (suite.prefix(task, seed) + suffix)
            record = dict(mode=describe_seed(task, seed).mode)
            try:
                instruction, obs = setup_episode(env, config, args, seed, 'unseen', record, path)
                shard.check_scene(base, cfg, 'vlact', spec, seed, instruction, obs, env, path)
                rows.append(dict(task=task, seed=seed, exact_rgb=True, instruction_equal=True, state_atol=1e-6))
                suite.write(output/'progress.json', rows)
                print('SCENE_MATCH', task, seed, flush=True)
                check_gpu(gpu_rows(), lane['sim_gpu'], simulator=True)
            finally:
                env.close_env()
    assert len(rows) == 2 * len(cfg['tasks'])
    suite.write(output/'validation.json', dict(complete=True, rows=rows, sim_gpu=lane['sim_gpu'],
                source_sha256=suite.digest(base/'support/source-hashes.json'), code_sha256=cfg['code_sha256']))


def pending_specs(base, cfg, policy):
    return [s for s in suite.read(base/'plan.json')['tasks'] if s['task'] in cfg['tasks'] and
            any(suite.completed_record(base, policy, s, seed) is None for seed in s['seeds'])]


def run(cfg, config_path):
    assert socket.gethostname() == cfg['host']
    base = Path(cfg['run_dir'])
    (base/'queues').mkdir(exist_ok=True)
    lock = (base/'scheduler.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    check_sources(base, cfg)
    proof = suite.read(Path(cfg['scene_probe'])/'validation.json')
    assert proof['complete'] and proof['sim_gpu'] == cfg['lanes'][1]['sim_gpu']
    assert proof['source_sha256'] == suite.digest(base/'support/source-hashes.json')
    assert proof['code_sha256'] == cfg['code_sha256']
    plan = suite.read(base/'plan.json')
    for batch in (base/'batches').glob('*'):
        for policy in cfg['policies']:
            for spec in plan['tasks']:
                if spec['task'] in cfg['tasks']:
                    suite.ingest_batch(base, policy, spec, batch/policy/spec['task'])
    session = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S-dual')
    pending = [p for p in cfg['policies'] if pending_specs(base, cfg, p)]
    lanes = [dict(index=i, id=lane['id'], phase='idle', sim=None, policy=None, tunnel=False) for i,lane in enumerate(cfg['lanes'])]
    def interrupted(signum, frame):
        raise RuntimeError(f'Queue scheduler received signal {signum}')
    signal.signal(signal.SIGTERM, interrupted); signal.signal(signal.SIGINT, interrupted)

    def summary(state, error=None):
        view = [{k:v for k,v in lane.items() if k not in ('sim','specs')} for lane in lanes]
        status = suite.report(base, state=state, current=dict(queues=view, pending_policies=pending), error=error)
        suite.write(base/'queues/status.json', dict(status=status['status'], updated_at=status['updated_at'],
                    completed_episodes=status['completed_episodes'], expected_episodes=1944, lanes=view,
                    pending_policies=pending, error=error, session=session))

    def launch_sim(lane):
        spec = lane['specs'][0]; policy = lane['policy']; task = spec['task']
        suite.check_oracle_budget(base, policy, spec)
        check_sources(base, cfg)
        check_gpu(gpu_rows(), cfg['lanes'][lane['index']]['sim_gpu'], simulator=True, idle=True)
        batch = base/'batches'/f"{session}-{lane['id']}-{lane['attempt']:03d}"/policy
        output = batch/task; log = batch/(task+'-launch.log');log.parent.mkdir(parents=True, exist_ok=True)
        cmd = [cfg['python'], '-u', str(Path(__file__).resolve()), 'worker', '--config', str(config_path),
               '--lane', str(lane['index']), '--policy', policy, '--task', task, '--output', str(output)]
        with log.open('x') as stream:
            proc = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stream,
                                    stderr=subprocess.STDOUT, env=dict(os.environ,PYTHONNOUSERSITE='1'), start_new_session=True)
        lane.update(sim=proc,sim_pid=proc.pid,task=task,output=str(output),log=str(log),phase='evaluating',
                    started=time.time(),last_progress=time.time(),previous_count=-1)
        suite.write(batch/(task+'-launch.json'),dict(argv=cmd,pid=proc.pid,lane=lane['id'],session=session))

    try:
        while pending or any(l['phase']!='idle' for l in lanes):
            rows = gpu_rows()
            assert __import__('shutil').disk_usage(base).free > 100*1024**3
            gpu_log = []
            for lane in lanes:
                gpu_log.append(check_gpu(rows, cfg['lanes'][lane['index']]['sim_gpu'], simulator=True))
                if lane['phase']=='idle':
                    if not pending:
                        continue
                    policy = pending.pop(0)
                    lane.update(policy=policy,specs=pending_specs(base,cfg,policy),attempt=0,phase='loading_server',started=time.time())
                    remote(cfg,dict(action='start',lane=lane['index'],policy=policy,session=session))
                    continue
                health = remote(cfg,dict(action='status',lane=lane['index']))
                assert health['running'], ('Remote server exited',lane['policy'],health['state'])
                if lane['phase']=='loading_server':
                    assert time.time()-lane['started']<1200, 'Server startup timeout'
                    if health['ready']:
                        lane['server_pid']=health['state']['pid']
                        suite.write(base/'servers'/session/lane['id']/lane['policy']/'remote-service.json',health)
                        lane['tunnel']=True
                        tunnel(cfg,lane['policy'],'forward')
                        launch_sim(lane)
                    continue
                assert health['ready'], 'Remote server stopped listening'
                spec=lane['specs'][0];output=Path(lane['output']);policy=lane['policy'];proc=lane['sim']
                suite.ingest_batch(base,policy,spec,output)
                count=sum(suite.completed_record(base,policy,spec,s) is not None for s in spec['seeds'])
                if count!=lane['previous_count']:
                    lane.update(previous_count=count,last_progress=time.time())
                if proc.poll() is None:
                    logs=list(output.glob('*.log'))+[Path(lane['log'])]
                    assert time.time()-max([lane['started']]+[p.stat().st_mtime for p in logs if p.exists()])<1200
                    assert time.time()-lane['last_progress']<7200
                    continue
                rc=proc.returncode;suite.stop(proc);lane['sim']=None
                suite.ingest_batch(base,policy,spec,output)
                result=suite.read(output/'summary.json') if (output/'summary.json').exists() else {}
                retry=suite.retryable_batch_failure(output,rc,result)
                if retry is not None:
                    suite.check_oracle_budget(base,policy,spec)
                    suite.write(output.parent/(spec['task']+'-oracle-retry.json'),dict(seed=retry,
                        prior_failures=suite.oracle_failure_history(base,policy,spec)[retry],max_attempts=suite.MAX_ORACLE_ATTEMPTS))
                else:
                    assert rc in (0,1) and result.get('complete'), (policy,spec['task'],rc,result)
                    assert count==len(spec['seeds'])
                    print('COMPLETE',lane['id'],policy,spec['task'],flush=True)
                    lane['specs'].pop(0)
                lane['attempt']+=1
                if lane['specs']:
                    launch_sim(lane)
                else:
                    remote(cfg,dict(action='stop',lane=lane['index'],session=session))
                    tunnel(cfg,policy,'cancel');lane.update(phase='idle',policy=None,tunnel=False)
            with (base/'queues/gpu-observations.jsonl').open('a') as log:
                log.write(json.dumps(dict(time=time.time(),rows=gpu_log))+'\n')
            summary('running_dual_queues')
            time.sleep(15)
        summary('validating')
        suite.verify(base,require_complete=True)
        summary('complete')
    except BaseException as exc:
        traceback.print_exc()
        for lane in lanes:
            try:
                suite.stop(lane['sim'])
                if lane['policy']:
                    remote(cfg,dict(action='stop',lane=lane['index'],session=session))
                    if lane['tunnel']:
                        tunnel(cfg,lane['policy'],'cancel')
                if lane['policy'] and lane.get('output'):
                    spec=next(s for s in plan['tasks'] if s['task']==lane['task'])
                    suite.ingest_batch(base,lane['policy'],spec,Path(lane['output']))
            except Exception:
                traceback.print_exc()
        summary('incomplete',f'{type(exc).__name__}: {exc}')
        raise
    finally:
        lock.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['run','worker','service','scene-probe'])
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--lane',type=int,choices=[0,1]);parser.add_argument('--policy');parser.add_argument('--task')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();cfg=config(args.config)
    if args.command=='service':
        print(json.dumps(service(cfg,json.load(sys.stdin))))
    elif args.command=='worker':
        return worker(cfg,args.lane,args.policy,args.task,args.output.resolve())
    elif args.command=='scene-probe':
        scene_probe(cfg,args.output.resolve())
    else:
        run(cfg,args.config.resolve())


if __name__=='__main__':
    sys.exit(main())
