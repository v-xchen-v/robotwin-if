#!/usr/bin/env python3
"""Verify the frozen current release, reading its parent evidence from Git history."""
import argparse
import ast
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_contracts import IF_SEED_CONTRACTS
from if_benchmark.seed_manifest import load_manifest, manifest_sha256, validate_manifest
from if_benchmark.seed_modes import check_seed_modes
from tools.release_history import historical_evidence
from tools.run_formal_policy_suite import (
    POLICIES, digest,
    current_success_checker, matches_success_checker, validate_episode,
)

PARENT = ROOT / 'seed-manifests/robotwin-if-attribute-v2-20-per-mode'
PARENT_RESULT = ROOT / 'result/robotwin-if-attribute-v2-20blocks'
RELEASE = ROOT / 'seed-manifests/robotwin-if-arm-only-v2-20-per-mode'


def read(path):
    return json.loads(path.read_text())


def prior_rows(parent_result):
    with (parent_result / 'episodes.csv').open(newline='') as stream:
        return {(r['policy'], r['task'], int(r['seed'])): r for r in csv.DictReader(stream)}


def source_audit(old):
    prior_hashes = read(old / 'support/source-hashes.json')
    differences = [name for name, sha in prior_hashes.items()
                   if not (ROOT / name).exists() or digest(ROOT / name) != sha]
    allowed = {'tasks/envs/_if_grounding.py', 'tasks/envs/arm_select.py',
               'third_party/robotwin/envs/_if_grounding.py',
               'third_party/robotwin/envs/arm_select.py', 'tools/run_formal_policy_suite.py'}
    assert set(differences) <= allowed, differences
    for prefix in ('tasks/envs', 'third_party/robotwin/envs'):
        name = prefix + '/_if_grounding.py'
        before = ast.parse((old / 'support/source-snapshot' / name).read_text())
        after = ast.parse((ROOT / name).read_text())
        added = after.body.pop()
        assert isinstance(added, ast.ClassDef) and added.name == 'ArmPickMonitor'
        assert ast.dump(before) == ast.dump(after), 'Existing shared grounding code changed'
    return dict(previous_run=str(old), reused_episodes=2520, new_arm_select_episodes=240,
        source_differences=differences,
        source_difference_sha256={name: digest(ROOT / name) for name in differences},
        unchanged_five_task_sources=True, unchanged_all_six_task_manifests=True,
        shared_grounding_audit='AST unchanged after removing the added ArmPickMonitor class.',
        runner_change='Pin Arm checker contract; inference logic unchanged.',
        checkpoint_metadata='Retain prior run metadata and services-before-recovery.json through formal prepare.')


def verify_source_audit(old, recorded):
    observed = source_audit(old)
    if observed == recorded:
        return
    # Moving the default entry to this release must not rewrite its frozen audit.
    # Permit only this exact CLI-default edit: every other runner byte and every
    # task/config/source-audit field still have to match the published evidence.
    name = 'tools/run_formal_policy_suite.py'
    before = b"parser.add_argument('--release', type=Path, default=ROOT / 'seed-manifests/robotwin-if-attribute-v2-20-per-mode')"
    after = before.replace(b'robotwin-if-attribute-v2', b'robotwin-if-arm-only-v2')
    runner = (ROOT / name).read_bytes()
    assert runner.count(after) == 1, 'Unexpected formal runner release default'
    original = runner.replace(after, before, 1)
    assert hashlib.sha256(original).hexdigest() == recorded['source_difference_sha256'][name], \
        'Formal runner changed beyond its release default'
    observed['source_difference_sha256'][name] = recorded['source_difference_sha256'][name]
    assert observed == recorded, 'Source reuse audit changed beyond the release default'


def verify(base=RELEASE):
    with historical_evidence() as history:
        _verify(base, history)


def _verify(base, history):
    suite = yaml.safe_load((base / 'suite.yml').read_text())
    assert suite['policies'] == POLICIES
    assert [s['task'] for s in suite['tasks']] == list(IF_SEED_CONTRACTS)
    assert suite['blocks_per_task'] == 20
    check_seed_modes(base)
    for filename, expected in read(base / 'qualification-files.json').items():
        assert digest(history / filename) == expected, filename
    specs = {s['task']: s for s in suite['tasks']}
    expected_keys = set()
    for task, spec in specs.items():
        source = history / 'seed-manifests' / PARENT.name
        path = base / spec['manifest']
        assert path.read_bytes() == (source / spec['manifest']).read_bytes(), task
        manifest = load_manifest(path)
        checked = validate_manifest(manifest)
        assert manifest['task_config'] == spec['task_config']
        assert manifest_sha256(manifest) == spec['manifest_sha256']
        assert len(checked['block_ids']) == spec['blocks'] == 20
        assert checked['mode_denominators'] == spec['modes']
        assert spec['episodes_per_policy'] == len(manifest['seeds'])
        reusable = [] if task == 'arm_select' else manifest['seeds']
        pending = manifest['seeds'] if task == 'arm_select' else []
        assert spec['reusable_seeds_per_policy'] == reusable
        assert spec['pending_seeds_per_policy'] == pending
        expected_keys.update((p, task, seed) for p in POLICIES for seed in reusable)
    assert specs['arm_select']['task_config'] == 'demo_clean_arm_select_v3'
    assert {k: specs['arm_select'][k] for k in current_success_checker('arm_select')} == current_success_checker('arm_select')
    verify_source_audit(Path(suite['previous_formal_run']), read(base / 'reuse-audit.json'))
    reuse = yaml.safe_load((base / suite['reuse_index']).read_text())
    rows = reuse['episodes']
    keys = [(r['policy'], r['task'], r['seed']) for r in rows]
    assert len(keys) == len(set(keys)) == len(expected_keys) == 2520
    assert set(keys) == expected_keys
    old = prior_rows(history / 'result' / PARENT_RESULT.name)
    for index, row in enumerate(rows, 1):
        key = row['policy'], row['task'], row['seed']
        directory = Path(row['source_directory'])
        assert directory == Path(suite['previous_formal_run']) / row['policy'] / row['task']
        stem = f"{row['task']}_ep{row['seed']}"
        marker = directory / (stem + '_provenance.json')
        assert digest(marker) == row['source_provenance_sha256']
        assert read(marker)['files_sha256'] == row['files_sha256']
        for name, expected in row['files_sha256'].items():
            assert Path(name).name == name
            assert digest(directory / name) == expected, (key, name)
        record = validate_episode(directory, row['task'], row['seed'], specs[row['task']]['task_config'])
        assert matches_success_checker(specs[row['task']], record), key
        assert record['success'] == row['success'] == bool(int(old[key]['success']))
        assert record['mode'] == row['mode'] == old[key]['mode']
        assert row['files_sha256'][stem + '_result.json'] == old[key]['record_sha256']
        if index % 300 == 0:
            print(f'Verified source artifacts for {index}/2520 reused episodes', flush=True)
    assert Counter(r['policy'] for r in rows) == {p: 420 for p in POLICIES}
    assert reuse['count'] == suite['reusable_episodes'] == 2520
    assert reuse['successes'] == sum(r['success'] for r in rows)
    assert suite['pending_episodes'] == 240
    assert suite['episodes_per_policy'] == 460 and suite['episodes_all_six_policies'] == 2760
    print('OK: frozen release provenance; 6 tasks x 20 blocks; 2520 unchanged reusable episodes; 240 Arm rerun seeds', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('verify',))
    parser.add_argument('--release', type=Path, default=RELEASE)
    args = parser.parse_args()
    verify(args.release.resolve())
