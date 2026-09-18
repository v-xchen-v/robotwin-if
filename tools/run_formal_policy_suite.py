#!/usr/bin/env python3
"""Prepare, resume and monitor the frozen six-policy formal IF evaluation.

Run with the RoboTwin Python. Only one simulator and one model server are used.
Completed policy failures are immutable results. Pure pre-inference oracle
failures may retry the same seed twice, in fresh simulators after GPU checks.
Other infrastructure errors stop the queue. Retry limits survive restarts.
"""
import argparse
from collections import Counter
import datetime
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PYTHON = '/home/xichen6/miniconda3/envs/RoboTwin/bin/python'
POLICIES = ['xvla', 'lingbot_va', 'lingbot_vla', 'vlact', 'dm05', 'hy_vla']
PORTS = dict(zip(POLICIES, range(8010, 8016)))
ENVS = {p: Path('/home/xichen6/miniconda3/envs') / ('robotwin-if-' + p.replace('_', '-'))
        for p in POLICIES}
ENVS.update({p: Path('/Data/robotwin-if/envs') / ('robotwin-if-' + p.replace('_', '-'))
             for p in ('dm05', 'hy_vla')})
DEFAULT_RUN = Path('/Data/robotwin-if/evaluations/robotwin-if-cube-v3-20blocks-001')
MAX_ORACLE_ATTEMPTS = 3  # Initial attempt plus at most two retries; never policy retries.


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    tmp.replace(path)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024**2), b''):
            h.update(chunk)
    return h.hexdigest()


def block_count(spec):
    from if_benchmark.seed_contracts import contract_for_seeds
    count = len(spec["seeds"]) // contract_for_seeds(spec["task"], spec["seeds"]).block_size
    assert spec.get('blocks', count) == count, 'Task block count disagrees with manifest'
    return count


def prefix(task, seed):
    return f'{task}_ep{seed}'


def episode_files(directory, task, seed):
    pre = prefix(task, seed)
    return sorted(p for p in Path(directory).iterdir() if p.is_file()
                  and (p.name.startswith(pre + '_') or p.name == pre + '.log')
                  and not p.name.endswith('_provenance.json'))


def validate_episode(directory, task, seed, config):
    from if_benchmark.seed_contracts import describe_seed
    pre = Path(directory) / prefix(task, seed)
    record = read(str(pre) + '_result.json')
    summary = read(str(pre) + '_summary.json')
    status = read(str(pre) + '_status.json')
    assert record['status'] in ('success', 'failure') and record['oracle_success'], record
    assert record['success'] == (record['status'] == 'success')
    assert (record['task'], record['seed'], record['mode']) == (task, seed, describe_seed(task, seed).mode)
    assert record['instruction_type'] == summary['instruction_type'] == 'unseen'
    assert summary['config'] == config and summary['execution_runtime_error'] is None
    assert summary['success'] == record['success'] and status['status'] == 'policy_' + record['status']
    assert record['instruction'] == summary['instruction'] and record['instruction']
    assert summary['steps'] == record['action_calls'] > 0
    if record['status'] == 'failure':
        assert record['action_calls'] == record['step_limit']
    for suffix in ('_oracle.json', '_initial_observation.npz', '_actions.npz', '_timings.json',
                   '_diagnostics.json', '_action_logs.json', f"_{int(record['success'])}.mp4"):
        assert Path(str(pre) + suffix).stat().st_size > 0, (pre, suffix)
    return record


def current_success_checker(task):
    """Pin new plans to the checker actually used by the current task source."""
    from dataclasses import asdict
    from tasks.envs._if_bottle_verb import PickHoldMonitor, PickHoldRules
    from tasks.envs._if_grounding import AttributePickMonitor
    if task == 'bottle_verb':
        return dict(success_checker_version=PickHoldMonitor.VERSION,
                    success_checker_parameters=asdict(PickHoldRules()))
    if task == 'attribute_select':
        return dict(success_checker_version=AttributePickMonitor.VERSION,
                    success_checker_parameters={'lift_m': AttributePickMonitor.LIFT_THRESH})
    return dict(success_checker_version=None, success_checker_parameters=None)


def matches_success_checker(spec, record):
    expected = spec.get('success_checker_version')
    signals = record.get('signals') or {}
    if expected is None:
        return True  # Historical plan: validate using its original recorded contract.
    if not isinstance(signals, dict) or signals.get('checker_version') != expected:
        return False
    parameters = spec.get('success_checker_parameters')
    if parameters is not None and signals.get('thresholds') != parameters:
        return False
    if expected == 'relative-lift-hold-v6-terminal' and record.get('mode') == 'pick':
        # A physical hold / diagnostic replay is not a terminal policy verdict.
        return (signals.get('pick_verdict_protocol') == 'action-budget-end'
                and signals.get('pick_terminal_evaluation') is True
                and signals.get('pick_verdict_finalized') is True
                and signals.get('pick_final_success') is record.get('success')
                and record.get('action_calls') == record.get('step_limit') == 700
                and signals.get('policy_action_count') == signals.get('policy_action_limit') == 700)
    return True


def compatible_reuse(specs, episodes):
    """Old success labels cannot be reused under a changed task predicate."""
    by_task = {s['task']: s for s in specs}
    accepted, excluded = [], []
    for row in episodes:
        spec = by_task[row['task']]
        if spec.get('success_checker_version'):
            record = read(ROOT / row['source_directory'] / (prefix(row['task'], row['seed']) + '_result.json'))
            if not matches_success_checker(spec, record):
                excluded.append(dict(policy=row['policy'], task=row['task'], seed=row['seed'],
                    reason='success_checker_changed', expected=spec['success_checker_version']))
                continue
        accepted.append(row)
    return accepted, excluded


def import_episode(base, policy, spec, seed, source, origin, expected_hashes=None):
    """Commit the provenance marker last, so partial copies never count as results."""
    task = spec['task']
    target = base / policy / task
    marker = target / (prefix(task, seed) + '_provenance.json')
    if marker.exists():
        return False
    record = validate_episode(source, task, seed, spec['task_config'])
    assert matches_success_checker(spec, record), 'Result uses an incompatible success checker; rerun the exact seed'
    files = episode_files(source, task, seed)
    hashes = {p.name: digest(p) for p in files}
    for name, sha in (expected_hashes or {}).items():
        assert hashes.get(name) == sha, (source, name, 'reuse checksum mismatch')
    target.mkdir(parents=True, exist_ok=True)
    for file in files:
        destination = target / file.name
        if destination.exists():
            assert digest(destination) == hashes[file.name], ('conflicting result', destination)
        else:
            temporary = destination.with_name(destination.name + '.copying')
            shutil.copy2(file, temporary)
            assert digest(temporary) == hashes[file.name], ('copy checksum mismatch', file)
            temporary.replace(destination)
    from if_benchmark.seed_contracts import contract_for_seeds
    write(marker, dict(policy=policy, task=task, seed=seed, origin=origin,
                       source_directory=str(Path(source).resolve()), files_sha256=hashes,
                       success=record['success'], mode=record['mode'],
                       formal_block=spec['seeds'].index(seed) // contract_for_seeds(task, spec['seeds']).block_size))
    return True


def source_paths():
    paths = set()
    for folder in ('policies', 'if_benchmark', 'tasks', 'third_party/robotwin/envs',
                   'third_party/robotwin/task_config', 'third_party/robotwin/description'):
        paths.update(p for p in (ROOT / folder).rglob('*')
                     if p.is_file() and p.suffix in ('.py', '.json', '.yml', '.yaml'))
    paths.update((Path(__file__).resolve(), ROOT / 'tools/sim_device.py'))
    return sorted(paths)


def check_sources(base):
    for name, sha in read(base / 'support/source-hashes.json').items():
        assert digest(ROOT / name) == sha, f'Source changed; stop before continuing: {name}'
    for name, sha in read(base / 'support/release-hashes.json').items():
        assert digest(base / name) == sha, f'Frozen manifest changed: {name}'


def prior_metadata_directory(old, policy, task):
    """Accept direct evaluator runs and formal archives that retain run metadata."""
    for source in (old / policy / task, old / 'provenance/reused' / policy / task):
        if all((source / name).is_file() for name in ('run.json', 'resolved_config.json', 'summary.json')):
            return source
    raise FileNotFoundError(f'Missing complete prior run metadata for {policy}/{task} in {old}')


def prepare(base, release, old):
    import yaml
    subprocess.run([PYTHON, str(release / 'verify.py')], cwd=ROOT, check=True)
    suite = yaml.safe_load((release / 'suite.yml').read_text())
    reuse = yaml.safe_load((release / 'reusable-results.yml').read_text())
    assert suite['policies'] == POLICIES
    check_active_tasks(suite['tasks'])
    metadata = {(p, s['task']): prior_metadata_directory(old, p, s['task'])
                for p in POLICIES for s in suite['tasks']}
    base.mkdir(parents=True, exist_ok=False)
    shutil.copytree(release, base / 'manifests')
    specs = [dict(s, seeds=read(release / s['manifest'])['seeds'],
                  **current_success_checker(s['task']))
             for s in suite['tasks']]
    compatible, excluded = compatible_reuse(specs, reuse['episodes'])
    for spec in specs:
        shared = set(spec['seeds'])
        for policy in POLICIES:
            shared &= {r['seed'] for r in compatible if r['policy'] == policy and r['task'] == spec['task']}
        spec['reusable_seeds_per_policy'] = [s for s in spec['seeds'] if s in shared]
        spec['pending_seeds_per_policy'] = [s for s in spec['seeds'] if s not in shared]
    assert all(block_count(s) == suite['blocks_per_task'] for s in specs)
    plan = dict(repo_root=str(ROOT), policies=POLICIES, tasks=specs,
                expected_episodes=len(POLICIES) * sum(len(s['seeds']) for s in specs),
                blocks_per_task=suite['blocks_per_task'], instruction_type='unseen', old_run=str(old),
                sim_gpu=0, model_gpu=1, parallel_simulators=1, parallel_model_servers=1,
                created_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    write(base / 'plan.json', plan)
    (base / 'support').mkdir()
    write(base / 'support/excluded-checker-reuse.json', excluded)
    for s in specs:
        write(base / 'pending-manifests' / s['manifest'],
              dict(schema_version=read(release / s['manifest'])['schema_version'], task=s['task'], task_config=s['task_config'],
                   seeds=s['pending_seeds_per_policy']))
    for policy in POLICIES:
        for spec in specs:
            source = metadata[policy, spec['task']]
            dest = base / 'provenance/reused' / policy / spec['task']
            for name in ('run.json', 'resolved_config.json', 'summary.json'):
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / name, dest / name)
    shutil.copy2(old / 'support/services-before-recovery.json', base / 'support/services-before-recovery.json')
    hashes = {}
    for file in source_paths():
        relative = file.relative_to(ROOT)
        hashes[str(relative)] = digest(file)
        snapshot = base / 'support/source-snapshot' / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, snapshot)
    write(base / 'support/source-hashes.json', hashes)
    write(base / 'support/release-hashes.json', {str(p.relative_to(base)): digest(p)
          for folder in ('manifests', 'pending-manifests') for p in (base / folder).iterdir() if p.is_file()})
    for directory, name in ((ROOT, 'robotwin-if'), (ROOT / 'third_party/robotwin', 'robotwin')):
        patch = subprocess.check_output(['git', '-C', str(directory), 'diff', 'HEAD'])
        (base / 'support' / (name + '-source.patch')).write_bytes(patch)
    by_task = {s['task']: s for s in specs}
    for i, row in enumerate(compatible, 1):
        import_episode(base, row['policy'], by_task[row['task']], row['seed'],
                       ROOT / row['source_directory'], 'reused', row['files_sha256'])
        if i % 46 == 0:
            print(f'Copied and checksum-verified {i}/{len(compatible)} compatible episodes', flush=True)
    alias = ROOT / 'outputs/policy-eval' / base.name
    if alias != base and not alias.exists():
        alias.symlink_to(base, target_is_directory=True)
    report(base, state='prepared')


def report(base, state=None, current=None, error=None):
    from if_benchmark.seed_contracts import contract_for_seeds
    plan = read(base / 'plan.json')
    previous = read(base / 'status.json') if (base / 'status.json').exists() else {}
    totals = Counter()
    rows = []
    for policy in plan['policies']:
        for spec in plan['tasks']:
            task = spec['task']
            directory = base / policy / task
            records = [read(p) for p in sorted(directory.glob('*_provenance.json'))]
            assert len({r['seed'] for r in records}) == len(records)
            assert all(r['seed'] in spec['seeds'] for r in records)
            done = {r['seed'] for r in records}
            size = contract_for_seeds(task, spec['seeds']).block_size
            blocks = [spec['seeds'][i:i + size] for i in range(0, len(spec['seeds']), size)]
            complete_blocks = sum(all(seed in done for seed in block) for block in blocks)
            row = dict(policy=policy, task=task, expected_episodes=len(spec['seeds']),
                       recorded_episodes=len(records), successes=sum(r['success'] for r in records),
                       reused=sum(r['origin'] == 'reused' for r in records),
                       new=sum(r['origin'] == 'new' for r in records),
                       complete=len(records) == len(spec['seeds']),
                       completed_blocks=complete_blocks, expected_blocks=len(blocks),
                       partial_blocks=sum(any(seed in done for seed in block) and
                                          not all(seed in done for seed in block) for block in blocks),
                       pending_seeds=[s for s in spec['seeds'] if s not in done], per_mode={})
            for mode in contract_for_seeds(task, spec['seeds']).modes:
                selected = [r for r in records if r['mode'] == mode]
                row['per_mode'][mode] = dict(expected=block_count(spec), recorded=len(selected),
                                             successes=sum(r['success'] for r in selected))
            for key in ('recorded_episodes', 'successes', 'reused', 'new', 'completed_blocks', 'expected_blocks'):
                totals[key] += row[key]
            write(directory / 'summary.json', row)
            rows.append(row)
    status = dict(status=state or previous.get('status', 'prepared'),
                  updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  expected_episodes=plan['expected_episodes'], completed_episodes=totals['recorded_episodes'],
                  pending_episodes=plan['expected_episodes'] - totals['recorded_episodes'],
                  reused_episodes=totals['reused'], new_episodes=totals['new'],
                  successes=totals['successes'], policy_failures=totals['recorded_episodes'] - totals['successes'],
                  complete_task_policy_runs=sum(r['complete'] for r in rows),
                  completed_blocks=totals['completed_blocks'], expected_blocks=totals['expected_blocks'],
                  current=current if current is not None else previous.get('current'),
                  error=error, sim_gpu=plan.get('sim_gpu'), model_gpu=plan.get('model_gpu'),
                  execution_topology=plan.get('execution_topology'))
    write(base / 'summary.json', dict(**status, tasks=rows))
    write(base / 'status.json', status)
    targets = ', '.join(str(n) for n in sorted({block_count(s) for s in plan['tasks']}))
    text = [f'# Formal IF v2: {targets} blocks', '',
            f"State: {status['status']}; completed {status['completed_episodes']}/{status['expected_episodes']}; reused {totals['reused']}; new {totals['new']}.",
            '', 'Policy failures count as completed. Missing/error episodes remain pending.',
            'Runtime measurements from different evaluator versions must be reported separately.', '',
            '| Policy | Task | Complete blocks | Episodes | Success | Reused | New |', '|---|---|---:|---:|---:|---:|---:|']
    text.extend(f"| {r['policy']} | {r['task']} | {r['completed_blocks']}/{r['expected_blocks']} | {r['recorded_episodes']}/{r['expected_episodes']} | {r['successes']} | {r['reused']} | {r['new']} |" for r in rows)
    (base / 'report.md').write_text('\n'.join(text) + '\n')
    return status


def completed_record(base, policy, spec, seed):
    directory = base / policy / spec['task']
    marker = directory / (prefix(spec['task'], seed) + '_provenance.json')
    if not marker.exists():
        return None
    provenance = read(marker)
    name = prefix(spec['task'], seed) + '_result.json'
    assert digest(directory / name) == provenance['files_sha256'][name]
    record = validate_episode(directory, spec['task'], seed, spec['task_config'])
    assert matches_success_checker(spec, record), 'Committed result uses an incompatible success checker'
    return record


def check_scene(base, policy, spec, seed, instruction, obs, env, path):
    """X-VLA establishes each scene; subsequent policies must match it exactly."""
    if policy == 'xvla':
        return
    import numpy as np
    from policies.xvla.client import encode_proprio
    task = spec['task']
    reference = completed_record(base, 'xvla', spec, seed)
    assert reference is not None, ('Missing canonical X-VLA scene', task, seed)
    pre = base / 'xvla' / task / prefix(task, seed)
    marker = read(str(pre) + '_provenance.json')
    initial_path = Path(str(pre) + '_initial_observation.npz')
    expected_sha = marker['files_sha256'][initial_path.name]
    assert digest(initial_path) == expected_sha, 'Reference checksum changed'
    assert instruction == reference['instruction'] and env.step_lim == reference['step_limit']
    with np.load(initial_path) as expected:
        for camera in ('head_camera', 'left_camera', 'right_camera'):
            assert np.array_equal(obs['observation'][camera]['rgb'], expected[camera]), (task, seed, camera, 'Initial RGB mismatch')
        np.testing.assert_allclose(encode_proprio(obs), expected['proprio'], atol=1e-6, rtol=0, equal_nan=False)
    write(path('_same_host_scene.json'), dict(reference=str(pre), host=socket.gethostname(),
                initial_sha256=expected_sha, exact_rgb=True, instruction=True, state_atol=1e-6))


def check_active_tasks(specs):
    from if_benchmark.seed_contracts import IF_SEED_CONTRACTS
    assert [s['task'] for s in specs] == list(IF_SEED_CONTRACTS), 'Formal runs require the current six-task inventory'
    from if_benchmark.seed_contracts import validate_active_seeds
    for spec in specs:
        if 'modes' in spec:
            assert set(spec['modes']) == set(IF_SEED_CONTRACTS[spec['task']].modes), 'Retired modes; use the spatial3 release'
        if 'seeds' in spec:
            validate_active_seeds(spec['task'], spec['seeds'])


def worker(base, policy, task, output):
    """Use the complete formal manifest while skipping committed episode records.

    This keeps block ordinals stable, including a resume in the middle of a
    block. Raw files from skipped episodes remain in the canonical directory;
    resume.json explicitly identifies them in each batch's provenance.
    """
    plan = read(base / 'plan.json')
    spec = next(s for s in plan['tasks'] if s['task'] == task)
    old_args = read(base / 'provenance/reused' / policy / task / 'run.json')['arguments']
    module = importlib.import_module('policies.' + policy + '.eval')
    original = module.run_episode
    retained = {s: r for s in spec['seeds'] if (r := completed_record(base, policy, spec, s)) is not None}
    def resume_episode(env, config, client, args, seed, split, directory, block=None):
        if seed in retained:
            print(f'REUSE committed seed={seed} status={retained[seed]["status"]}', flush=True)
            return retained[seed].copy()
        return original(env, config, client, args, seed, split, directory, block=block)
    original_setup = module.setup_episode
    def checked_setup(env, config, args, seed, split, record, path):
        instruction, obs = original_setup(env, config, args, seed, split, record, path)
        check_scene(base, policy, spec, seed, instruction, obs, env, path)
        return instruction, obs
    argv = [str(module.__file__), '--task', task, '--task-config', spec['task_config'],
            '--seed-manifest', str(base / 'manifests' / spec['manifest']), '--blocks', str(block_count(spec)),
            '--instruction-type', 'unseen', '--sim-gpu', '0', '--output-dir', str(output),
            '--server-url', old_args['server_url'], '--request-timeout', str(old_args['request_timeout'])]
    for option in ('checkpoint', 'checkpoint_revision', 'feedback', 'gripper_threshold', 'denoising_steps'):
        if option in old_args:
            argv += ['--' + option.replace('_', '-'), str(old_args[option])]
    write(output.parent / (task + '-resume.json'), dict(skipped_seeds=list(retained),
          canonical_directory=str(base / policy / task), argv=argv,
          note='Batch summary/results.jsonl include retained records; only new episodes have files in this batch.'))
    os.environ['CUDA_VISIBLE_DEVICES'] = '0'
    from tools.sim_device import pin_renderer
    previous_argv = sys.argv
    try:
        pin_renderer()
        module.run_episode = resume_episode
        module.setup_episode = checked_setup
        sys.argv = argv
        return module.main()
    finally:
        module.run_episode = original
        module.setup_episode = original_setup
        sys.argv = previous_argv


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            return True
    except OSError:
        return False


def gpu_check(base, label, idle=False):
    result = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.used,memory.total,temperature.gpu,utilization.gpu',
                             '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=8, check=True)
    rows = [[int(x.strip()) for x in line.split(',')] for line in result.stdout.strip().splitlines()]
    assert len(rows) == 2
    for index, used, total, temp, utilization in rows:
        assert temp < 87 and used < total * .96, ('GPU threshold', rows)
        if index == 0:
            assert used < 24576, ('Simulator memory limit', rows)
        if idle:
            assert used < 2048 and utilization < 10, ('GPU not idle; do not overlap jobs', rows)
    assert shutil.disk_usage(base).free > 100 * 1024**3, 'Less than 100 GiB free in output volume'
    with (base / 'support/gpu-observations.jsonl').open('a') as log:
        log.write(json.dumps(dict(time=time.time(), label=label, rows=rows)) + '\n')


def stop(proc):
    if proc is None:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    assert proc.poll() is not None, f'Own process group failed to exit: {proc.pid}'


def server_identity(base, policy, directory):
    if policy == 'xvla':
        return  # Pinned local snapshot in recorded argv; official /act cannot attest identity.
    expected = read(base / 'provenance/reused' / policy / 'bottle_verb/run.json')['server_metadata']
    actual = read(directory / 'server.json')
    volatile = {'created_at', 'gpu', 'source_sha256'}
    for key, value in expected.items():
        if key not in volatile:
            assert actual.get(key) == value, (policy, 'server identity/options changed', key)


def ingest_batch(base, policy, spec, output):
    path = output / 'results.jsonl'
    if not path.exists():
        return
    for line in path.read_text().splitlines(keepends=True):
        if not line.endswith('\n'):
            continue  # Evaluator may be in the middle of a write.
        record = json.loads(line)
        if record['status'] in ('success', 'failure'):
            import_episode(base, policy, spec, record['seed'], output, 'new')


def is_oracle_setup_failure(record):
    """Allow only an ordinary oracle negative before any policy inference.

    Timeout, CUDA, cache identity, video, close, or other errors never qualify.
    An exception from the watchdog never reaches this classification path.
    """
    return (record.get('status') == 'error' and record.get('oracle_success') is False
            and record.get('action_calls') == 0 and record.get('chunks') == 0
            and record.get('instruction') is None
            and not any(record.get(k) for k in ('video_error', 'close_error'))
            and record.get('error') == dict(stage='episode_setup', type='RuntimeError',
                message='Exact seed failed oracle qualification; no seed substitution'))


def oracle_failure_history(base, policy, spec):
    failures = {}
    for path in (base / 'batches').glob(f'*/{policy}/{spec["task"]}/*_result.json'):
        record = read(path)
        if is_oracle_setup_failure(record) and record['seed'] in spec['seeds']:
            failures.setdefault(record['seed'], []).append(str(path))
    return failures


def check_oracle_budget(base, policy, spec):
    for seed, failures in oracle_failure_history(base, policy, spec).items():
        if completed_record(base, policy, spec, seed) is None:
            assert len(failures) < MAX_ORACLE_ATTEMPTS, (
                f'Oracle failed {len(failures)} times for {policy}/{spec["task"]}/{seed}; '
                'keep block incomplete and review shared qualification; do not replace its seed')


def retryable_batch_failure(output, rc, summary):
    if rc != 2 or summary.get('complete') is not False or summary.get('error') is not None:
        return None
    path = output / 'results.jsonl'
    if not path.exists():
        return None
    lines = path.read_text().splitlines(keepends=True)
    if not lines or not lines[-1].endswith('\n'):
        return None
    records = [json.loads(line) for line in lines]
    errors = [r for r in records if r.get('status') == 'error']
    if len(errors) == 1 and errors[0] == records[-1] and is_oracle_setup_failure(errors[0]):
        return errors[0]['seed']
    return None


def run(base):
    lock = (base / 'scheduler.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    plan = read(base / 'plan.json')
    check_active_tasks(plan['tasks'])
    check_sources(base)
    session = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')
    session_dir = base / 'batches' / session
    session_dir.mkdir(parents=True, exist_ok=False)
    server = sim = None
    def interrupted(signum, frame):
        raise RuntimeError(f'Scheduler received signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    def launch(cmd, cwd, env, log):
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open('x') as stream:
            return subprocess.Popen(cmd, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                    start_new_session=True)
    current = {}
    try:
        # Recover complete episodes written before a prior supervisor stopped.
        for previous in (base / 'batches').glob('*'):
            for policy in POLICIES:
                for spec in plan['tasks']:
                    ingest_batch(base, policy, spec, previous / policy / spec['task'])
        for policy in POLICIES:
            todo = [s for s in plan['tasks'] if any(completed_record(base, policy, s, seed) is None for seed in s['seeds'])]
            if not todo:
                continue
            for spec in todo:
                check_oracle_budget(base, policy, spec)
            assert not any(port_open(p) for p in PORTS.values()), 'Another policy server is active'
            gpu_check(base, 'before ' + policy, idle=True)
            check_sources(base)
            server_dir = base / 'servers' / session / policy
            old = read(base / 'support/services-before-recovery.json')[policy]
            tail = old['argv'][1:]
            if tail[0] == '-u':
                tail = tail[1:]
            cmd = [str(ENVS[policy] / 'bin/python'), '-u'] + tail
            if '--gpu' in cmd:
                cmd[cmd.index('--gpu') + 1] = '1'
            flag = '--output_dir' if policy == 'xvla' else '--output-dir'
            cmd[cmd.index(flag) + 1] = str(server_dir)
            cmd = [str(ROOT / a) if a.startswith('policies/') else a for a in cmd]
            env = dict(os.environ, CUDA_VISIBLE_DEVICES='1', PYTHONNOUSERSITE='1',
                       HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
            env['PATH'] = str(ENVS[policy] / 'bin') + os.pathsep + env.get('PATH', '')
            server = launch(cmd, ROOT / 'third_party/xvla' if policy == 'xvla' else ROOT,
                            env, session_dir / policy / 'server.log')
            current = dict(policy=policy, phase='loading_server', server_pid=server.pid, argv=cmd, session=session)
            write(session_dir / policy / 'server-launch.json', current)
            report(base, state='running', current=current)
            deadline = time.monotonic() + 1200
            while not port_open(PORTS[policy]):
                assert server.poll() is None, f'{policy} server exited {server.returncode}'
                assert time.monotonic() < deadline, f'{policy} server load timeout'
                gpu_check(base, 'loading ' + policy)
                time.sleep(15)
            server_identity(base, policy, server_dir)
            for task_index, spec in enumerate(todo):
                check_sources(base)
                check_oracle_budget(base, policy, spec)
                task = spec['task']
                # Every retry has an immutable batch directory of the same shape,
                # so ingestion/resumption can find it after a supervisor restart.
                batch_dir = (base / 'batches' / f'{session}-retry-{task_index:03d}'
                             if (session_dir / policy / task).exists() else session_dir)
                output = batch_dir / policy / task
                cmd = [PYTHON, '-u', str(Path(__file__).resolve()), 'worker', '--run-dir', str(base),
                       '--policy', policy, '--task', task, '--output', str(output)]
                sim = launch(cmd, ROOT, dict(os.environ, CUDA_VISIBLE_DEVICES='0', PYTHONNOUSERSITE='1'),
                             batch_dir / policy / (task + '-launch.log'))
                current = dict(policy=policy, task=task, phase='evaluating', session=batch_dir.name,
                               sim_pid=sim.pid, server_pid=server.pid, output=str(output), argv=cmd)
                write(batch_dir / policy / (task + '-launch.json'), current)
                started = time.time()
                last_completed = started
                previous_count = 0
                while sim.poll() is None:
                    assert server.poll() is None, f'{policy} server exited during evaluation'
                    gpu_check(base, policy + '/' + task)
                    ingest_batch(base, policy, spec, output)
                    state = report(base, state='running', current=current)
                    if state['completed_episodes'] != previous_count:
                        previous_count = state['completed_episodes']
                        last_completed = time.time()
                    logs = list(output.glob('*.log')) + [batch_dir / policy / (task + '-launch.log')]
                    heartbeat = max([started] + [p.stat().st_mtime for p in logs if p.exists()])
                    assert time.time() - heartbeat < 1200, 'Simulator log has not advanced for 20 minutes'
                    assert time.time() - last_completed < 7200, 'No episode completed for 2 hours'
                    time.sleep(15)
                rc = sim.returncode
                stop(sim)  # Also clear any child processes before creating another simulator.
                sim = None
                ingest_batch(base, policy, spec, output)
                summary = read(output / 'summary.json') if (output / 'summary.json').exists() else {}
                failed_seed = retryable_batch_failure(output, rc, summary)
                if failed_seed is not None:
                    assert failed_seed in spec['seeds']
                    check_oracle_budget(base, policy, spec)
                    # Driver failure or resource pressure still stops immediately.
                    gpu_check(base, f'before oracle retry {policy}/{task}/{failed_seed}')
                    check_sources(base)
                    failures = oracle_failure_history(base, policy, spec)[failed_seed]
                    write(batch_dir / policy / (task + '-oracle-retry.json'), dict(
                        seed=failed_seed, prior_failed_attempts=len(failures),
                        max_attempts=MAX_ORACLE_ATTEMPTS, failed_records=failures,
                        reason='Pre-inference oracle negative; GPU healthy; rerun exact seed in a fresh simulator',
                        policy_results_retried=False))
                    current.update(phase='retrying_oracle_setup', seed=failed_seed)
                    report(base, state='running', current=current)
                    print(f'ORACLE RETRY {policy}/{task}/{failed_seed}: next attempt {len(failures) + 1}/{MAX_ORACLE_ATTEMPTS}', flush=True)
                    todo.insert(task_index + 1, spec)
                    continue
                assert rc in (0, 1) and summary.get('complete'), (policy, task, rc, summary)
                assert summary['recorded_episodes'] == len(spec['seeds'])
                assert all(completed_record(base, policy, spec, s) is not None for s in spec['seeds'])
                report(base, state='running', current=current)
                print(f'COMPLETE {policy}/{task}: {summary["successes"]}/{len(spec["seeds"])}', flush=True)
            stop(server)
            server = None
            time.sleep(5)
            gpu_check(base, 'stopped ' + policy, idle=True)
        status = report(base, state='validating', current={})
        assert status['completed_episodes'] == plan['expected_episodes']
        assert status['complete_task_policy_runs'] == len(plan['policies']) * len(plan['tasks'])
        assert status['completed_blocks'] == status['expected_blocks']
        verify(base, require_complete=True)
        check_sources(base)
        report(base, state='complete', current={})
    except BaseException as exc:
        traceback.print_exc()
        for proc in (sim, server):
            try:
                stop(proc)
            except Exception:
                traceback.print_exc()
        report(base, state='incomplete', current=current, error=f'{type(exc).__name__}: {exc}')
        raise


def verify(base, require_complete=False):
    import numpy as np
    import imageio.v2 as imageio
    from policies.xvla.client import decode_actions as decode_xvla
    from policies.lingbot_va.client import decode_actions as decode_lingbot_va
    plan = read(base / 'plan.json')
    counts = Counter()
    shared = {}
    for policy in POLICIES:
        for spec in plan['tasks']:
            directory = base / policy / spec['task']
            for seed in spec['seeds']:
                record = completed_record(base, policy, spec, seed)
                if record is None:
                    assert not require_complete, (policy, spec['task'], seed, 'missing')
                    continue
                marker = read(directory / (prefix(spec['task'], seed) + '_provenance.json'))
                for name, sha in marker['files_sha256'].items():
                    assert digest(directory / name) == sha, (directory, name, 'checksum mismatch')
                pre = directory / prefix(spec['task'], seed)
                with np.load(str(pre) + '_actions.npz') as trace, np.load(str(pre) + '_initial_observation.npz') as initial:
                    assert all(np.isfinite(trace[k]).all() for k in trace.files)
                    raw, executed, n = trace['raw_actions'], trace['executed_actions'], record['action_calls']
                    assert len(executed) == n
                    if policy == 'xvla':
                        assert trace['chunk_lengths'].sum() == len(raw)
                        decoded = decode_xvla(raw)
                    elif policy == 'lingbot_va':
                        decoded = np.concatenate([decode_lingbot_va(
                            chunk[:, int(skip):, :].transpose(1, 2, 0).reshape(-1, 16), initial['proprio'])
                            for chunk, skip in zip(raw, trace['skipped_frames'])])
                    elif policy == 'hy_vla':
                        assert raw.shape == (record['chunks'], 20, 16)
                        assert trace['model_actions'].shape == (record['chunks'], 40, 20)
                        decoded = raw[:, :7].reshape(-1, 16)
                    else:
                        decoded = raw.reshape(-1, 14)
                    np.testing.assert_allclose(executed, decoded[:n], atol=1e-12, rtol=0)
                    signature = dict(instruction=record['instruction'], step_limit=record['step_limit'],
                        rgb={k: hashlib.sha256(initial[k].tobytes()).hexdigest()
                             for k in ('head_camera', 'left_camera', 'right_camera')})
                    poses = trace['measured_poses'][0]
                    poses = poses if poses.shape == (14,) else poses[np.r_[0:7, 8:15]]
                    key = (spec['task'], seed)
                    if key in shared:
                        expected, expected_poses = shared[key]
                        assert signature == expected, (policy, key, 'initial RGB/instruction mismatch')
                        np.testing.assert_allclose(poses, expected_poses, rtol=0, atol=1e-6)
                    else:
                        shared[key] = signature, poses.copy()
                # Prior copied videos were already deeply validated; only decode new videos.
                if marker['origin'] == 'new':
                    with imageio.get_reader(str(pre) + f"_{int(record['success'])}.mp4") as video:
                        assert video.count_frames() == record['action_calls'] + 1
                counts[marker['origin']] += 1
    write(base / 'validation.json', dict(complete=sum(counts.values()) == plan['expected_episodes'],
          validated_episodes=sum(counts.values()), counts=dict(counts), artifacts_sha256_verified=True,
          action_traces_verified=True, cross_policy_initial_rgb_and_instructions_verified=True,
          new_video_frame_counts_verified=True))
    print(json.dumps(dict(validated=sum(counts.values()), counts=dict(counts))), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'status', 'verify', 'worker'))
    parser.add_argument('--run-dir', type=Path, default=DEFAULT_RUN)
    parser.add_argument('--release', type=Path, default=ROOT / 'seed-manifests/robotwin-if-cube-v3-20-per-mode')
    parser.add_argument('--old-run', type=Path,
                        help='Prepare: prior run with matching checkpoint and inference metadata')
    parser.add_argument('--policy', choices=POLICIES)
    parser.add_argument('--task')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    base = args.run_dir.resolve()
    if args.command == 'prepare':
        if args.old_run is None:
            parser.error('prepare requires --old-run with matching checkpoint and inference metadata')
        prepare(base, args.release.resolve(), args.old_run.resolve())
    elif args.command == 'run':
        run(base)
    elif args.command == 'status':
        print(json.dumps(read(base / 'status.json'), indent=2, ensure_ascii=False))
    elif args.command == 'verify':
        verify(base)
    else:
        return worker(base, args.policy, args.task, args.output.resolve())
    return 0


if __name__ == '__main__':
    sys.exit(main())
