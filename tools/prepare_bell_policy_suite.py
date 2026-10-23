#!/usr/bin/env python3
"""Reuse the five frozen task results; schedule only the new bell task."""
import argparse
import csv
import datetime
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_contracts import CURRENT_SUITE_TASKS
from tools import run_formal_policy_suite as formal
from tools.release_press_lift_bell_v1 import RELEASE, verify as verify_release

OLD = Path('/Data/robotwin-if/evaluations/robotwin-if-arm-only-v2-20blocks-001')
PACKAGE = ROOT / 'result/robotwin-if-arm-only-v2-20blocks'
RUN = Path('/Data/robotwin-if/evaluations/robotwin-if-press-lift-bell-v1-20blocks-001')


def reuse_inputs(old, suite, package=PACKAGE):
    """Validate seed/config/source/record identity before accepting any reused row."""
    assert formal.read(old / 'status.json')['status'] == 'complete'
    with (package / 'episodes.csv').open(newline='') as stream:
        published = {(r['policy'], r['task'], int(r['seed'])): r for r in csv.DictReader(stream)}
    old_sources = formal.read(old / 'support/source-hashes.json')
    source_audit = {}
    names = [f'tasks/envs/{t}.py' for t in CURRENT_SUITE_TASKS[1:]]
    names += [f'tasks/task_instruction/{t}.json' for t in CURRENT_SUITE_TASKS[1:]]
    names += [f'tasks/envs/{n}' for n in ('_if_grounding.py', '_if_relative.py', '_if_eval.py', '_pick_diverse_object_pool.py')]
    for name in names:
        sha = formal.digest(ROOT / name)
        assert sha == old_sources[name], ('Reused task source changed', name)
        source_audit[name] = sha
    rows = []
    for spec in suite['tasks'][1:]:
        task = spec['task']
        assert (RELEASE / spec['manifest']).read_bytes() == (old / 'manifests' / spec['manifest']).read_bytes()
        seeds = formal.read(RELEASE / spec['manifest'])['seeds']
        for policy in formal.POLICIES:
            for seed in seeds:
                source = old / policy / task
                stem = formal.prefix(task, seed)
                marker_path = source / (stem + '_provenance.json')
                marker = formal.read(marker_path)
                result = formal.validate_episode(source, task, seed, spec['task_config'])
                assert formal.matches_success_checker(spec, result)
                row = published[policy, task, seed]
                assert formal.digest(source / (stem + '_result.json')) == row['record_sha256']
                assert result['success'] == bool(int(row['success'])) == marker['success']
                rows.append(dict(policy=policy, task=task, seed=seed, success=result['success'],
                    source_directory=str(source), source_provenance_sha256=formal.digest(marker_path),
                    files_sha256=marker['files_sha256']))
    assert len(rows) == 2520
    return rows, source_audit


def prepare(base=RUN, old=OLD):
    suite = verify_release()
    rows, source_audit = reuse_inputs(old, suite)
    specs = [dict(s, seeds=formal.read(RELEASE / s['manifest'])['seeds']) for s in suite['tasks']]
    for spec in specs:
        for key, value in formal.current_success_checker(spec['task']).items():
            assert spec[key] == value
        spec['reusable_seeds_per_policy'] = [] if spec['task'] == 'press_lift_bell' else spec['seeds']
        spec['pending_seeds_per_policy'] = spec['seeds'] if spec['task'] == 'press_lift_bell' else []
    references = {p: formal.prior_metadata_directory(old, p, 'bottle_verb') for p in formal.POLICIES}
    base.mkdir(parents=True, exist_ok=False)
    shutil.copytree(RELEASE, base / 'manifests')
    plan = dict(repo_root=str(ROOT), release=RELEASE.name, policies=formal.POLICIES, tasks=specs,
        expected_episodes=2760, expected_reused_episodes=2520, expected_new_episodes=240,
        blocks_per_task=20, instruction_type='unseen', old_run=str(old),
        inference_reference_task='press_lift_bell', sim_gpu=0, model_gpu=1,
        execution_topology='one local simulator and one local model server, serial policies',
        parallel_simulators=1, parallel_model_servers=1,
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    formal.write(base / 'plan.json', plan)
    formal.write(base / 'support/reuse-index.json', rows)
    formal.write(base / 'support/reuse-audit.json', dict(parent_result=str(PACKAGE),
        parent_episode_csv_sha256=formal.digest(PACKAGE / 'episodes.csv'),
        unchanged_five_task_sources=source_audit, unchanged_five_manifests=True,
        reused_episodes=2520, new_bell_episodes=240, reuse_all_successes_and_failures=True))
    shutil.copyfile(PACKAGE / 'checkpoints.json', base / 'support/checkpoint-reference.json')
    shutil.copyfile(old / 'support/services-before-recovery.json', base / 'support/services-before-recovery.json')
    for policy, source in references.items():
        dest = base / 'provenance/inference-reference' / policy / 'press_lift_bell'
        dest.mkdir(parents=True)
        for name in ('run.json', 'resolved_config.json', 'summary.json'):
            shutil.copyfile(source / name, dest / name)
        formal.write(dest / 'reference.json', dict(source_directory=str(source),
            source_task='bottle_verb', purpose='checkpoint and inference options only; no bottle results reused',
            run_sha256=formal.digest(source / 'run.json')))
        for task in CURRENT_SUITE_TASKS[1:]:
            original = formal.prior_metadata_directory(old, policy, task)
            copied = base / 'provenance/reused' / policy / task
            copied.mkdir(parents=True)
            for name in ('run.json', 'resolved_config.json', 'summary.json'):
                shutil.copyfile(original / name, copied / name)
    hashes = {}
    for file in formal.source_paths():
        relative = file.relative_to(ROOT)
        hashes[str(relative)] = formal.digest(file)
        snapshot = base / 'support/source-snapshot' / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, snapshot)
    formal.write(base / 'support/source-hashes.json', hashes)
    formal.write(base / 'support/release-hashes.json', {str(p.relative_to(base)): formal.digest(p)
        for p in (base / 'manifests').rglob('*') if p.is_file()})
    for directory, name in ((ROOT, 'robotwin-if'), (ROOT / 'third_party/robotwin', 'robotwin')):
        (base / 'support' / (name + '-source.patch')).write_bytes(
            subprocess.check_output(['git', '-C', str(directory), 'diff', 'HEAD']))
    by_task = {s['task']: s for s in specs}
    for index, row in enumerate(rows, 1):
        formal.import_episode(base, row['policy'], by_task[row['task']], row['seed'],
                              Path(row['source_directory']), 'reused', row['files_sha256'])
        if index % 120 == 0:
            print(f'Copied and checksum-verified {index}/2520 reused episodes', flush=True)
    alias = ROOT / 'outputs/policy-eval' / base.name
    alias.symlink_to(base, target_is_directory=True)
    status = formal.report(base, state='prepared')
    assert status['reused_episodes'] == 2520 and status['new_episodes'] == 0 and status['pending_episodes'] == 240
    print(f'Prepared {base}: 2520 reused; 240 bell episodes pending', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, default=RUN)
    parser.add_argument('--old-run', type=Path, default=OLD)
    args = parser.parse_args()
    prepare(args.run_dir.resolve(), args.old_run.resolve())
