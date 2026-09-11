"""Validate this release's flat manifests, qualification evidence and reuse index.

CPU only; run from any directory with the RoboTwin Python environment.
"""
from collections import Counter
import json
from pathlib import Path
import sys

import yaml

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_contracts import IF_SEED_CONTRACTS
from if_benchmark.seed_manifest import load_manifest, validate_manifest, manifest_sha256
from if_benchmark.seed_generation import load_generation_state, validate_generation_evidence


def same_scene(a, b):
    key = 'initial_pose' if 'initial_pose' in a else 'initial_poses'
    return ('initial_rgb' in a and a['initial_rgb'] == b.get('initial_rgb')
            and key in a and a[key] == b.get(key))


suite = yaml.safe_load((BASE / 'suite.yml').read_text())
assert [t['task'] for t in suite['tasks']] == list(IF_SEED_CONTRACTS)
assert len(list(BASE.glob('*.json'))) == 12  # 7 flat manifests + 5 generation sidecars.
manifests = {}
for spec in suite['tasks']:
    task = spec['task']
    manifest = load_manifest(BASE / spec['manifest'])
    checked = validate_manifest(manifest)
    assert manifest['task'] == task and manifest['task_config'] == spec['task_config']
    assert manifest_sha256(manifest) == spec['manifest_sha256']
    assert len(checked['block_ids']) == 12 and all(v == 12 for v in checked['mode_denominators'].values())
    assert spec['modes'] == checked['mode_denominators']
    assert spec['episodes_per_policy'] == len(manifest['seeds'])
    manifests[task] = manifest
    if task in ('arm_select', 'grasp_cube_approach'):
        evidence = yaml.safe_load((BASE / f'{task}.probe.yml').read_text())
        assert evidence['task'] == task and evidence['task_config'] == manifest['task_config']
        assert evidence['manifest_sha256'] == manifest_sha256(manifest)
        runs = {r['directory']: r for r in evidence['runs']}
        selected = [d for d in evidence['decisions'] if d['selected']]
        assert sorted(s for d in selected for s in d['seeds']) == manifest['seeds']
        assert len(selected) == 12 and Counter(d['region'] for d in selected) == dict(left=4, center=4, right=4)
        signatures = set()
        for decision in selected:
            run = runs[decision['probe_directory']]
            report = run['report']
            assert report['complete'] and run['supervisor']['complete']
            assert run['supervisor']['exit_code'] in (0, 2)
            rows = report['episodes']
            pair = [r for r in rows if r['phase'] == 'candidate' and r['seed'] in decision['seeds']]
            assert len(pair) == 2 and [r['mode'] for r in pair] == list(IF_SEED_CONTRACTS[task].modes)
            assert all(r['passed'] and r['success'] and r['plan_success'] and not r['initial_success'] for r in pair)
            assert same_scene(*pair)
            block = next(b for b in report['blocks'] if b['seeds'] == decision['seeds'])
            assert block['same_template'] and block['region'] == decision['region']
            controls = [r for r in rows if r['seed'] in decision['seeds'] and r['phase'] in
                        ('repeat', 'wrong-arm', 'wrong-direction')]
            assert len(controls) == decision['controls_count']
            for row in controls:
                assert row['passed'] and same_scene(row, next(r for r in pair if r['seed'] == row['seed']))
                if row['phase'].startswith('wrong-'):
                    assert row['plan_success'] and row['signals']['lifted'] and not row['success']
            signatures.add(tuple(pair[0]['initial_rgb'][c] for c in ('head_camera', 'left_camera', 'right_camera')))
        assert len(signatures) == 12
        assert all(r['passed'] and r['matches_archived_v1'] for run in runs.values()
                   for r in run['report']['episodes'] if r['phase'] == 'fixed')
        dev = load_manifest(ROOT / f'seed-manifests/if-ext-v2-dev-12-per-mode/{task}.json')
        assert set(manifest['seeds']).isdisjoint(dev['seeds']) and min(manifest['seeds']) >= 200000
    else:
        validate_generation_evidence(manifest, load_generation_state(BASE / f'{task}.generation.json'))
    reused = spec['reusable_seeds_per_policy']
    pending = spec['pending_seeds_per_policy']
    assert not set(reused).intersection(pending) and sorted(reused + pending) == manifest['seeds']
    print(f'OK {task}: blocks=12 episodes={len(manifest["seeds"])} qualification=verified')

reuse = yaml.safe_load((BASE / suite['reuse_index']).read_text())
assert len(reuse['episodes']) == reuse['count'] == suite['reusable_episodes'] == 276
assert sum(r['success'] for r in reuse['episodes']) == reuse['successes'] == 105
assert Counter(r['policy'] for r in reuse['episodes']) == {p: 46 for p in suite['policies']}
assert len({(r['policy'], r['task'], r['seed']) for r in reuse['episodes']}) == 276
for row in reuse['episodes']:
    assert row['task'] not in ('arm_select', 'grasp_cube_approach')
    spec = next(t for t in suite['tasks'] if t['task'] == row['task'])
    assert row['seed'] in spec['reusable_seeds_per_policy']
    assert row['status'] == ('policy_success' if row['success'] else 'policy_failure')
assert sum(len(m['seeds']) for m in manifests.values()) == suite['episodes_per_policy'] == 324
assert suite['episodes_all_six_policies'] == 6 * 324 == 1944
assert 6 * sum(len(s['pending_seeds_per_policy']) for s in suite['tasks']) == suite['pending_episodes'] == 1668
print('OK release: 7 tasks, 324 episodes/policy, 276 reusable, 1668 pending across six policies')

# Bind the new qualification to its archived wide geometry and config.
import hashlib
for name, expected in suite['scene_snapshot_sha256'].items():
    assert hashlib.sha256((BASE / name).read_bytes()).hexdigest() == expected
e = yaml.safe_load((BASE / 'grasp_cube_approach.probe.yml').read_text())
assert e['translation_profile'] == 'wide-r1'
for run in e['runs']:
    for row in run['report']['episodes']:
        if row['phase'] == 'candidate':
            assert row['scene']['translation_profile'] == 'wide-r1'
assert set(manifests['grasp_cube_approach']['seeds']).isdisjoint(load_manifest(ROOT / 'seed-manifests/if-ext-v2-12-per-mode/grasp_cube_approach.json')['seeds'])
