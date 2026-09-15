"""Validate the unchanged six-task subset and its complete result reuse index (CPU only)."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import yaml

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_contracts import IF_SEED_CONTRACTS, describe_seed
from if_benchmark.seed_manifest import load_manifest, manifest_sha256, validate_manifest
from if_benchmark.seed_modes import check_seed_modes


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    check_seed_modes(BASE)
    suite = yaml.safe_load((BASE / 'suite.yml').read_text())
    assert [s['task'] for s in suite['tasks']] == list(IF_SEED_CONTRACTS)
    assert suite['blocks_per_task'] == 20
    assert suite['retired_tasks'] == ['grasp_cube_approach']
    parent = BASE.parent / suite['parent_release']
    proofs = json.loads((BASE / 'qualification-files.json').read_text())
    for name, expected in proofs.items():
        assert sha(ROOT / name) == expected, ('Qualification evidence changed', name)
    parent_suite = yaml.safe_load((parent / 'suite.yml').read_text())
    assert suite['policies'] == parent_suite['policies'] and len(set(suite['policies'])) == 6
    assert suite['instruction_type'] == parent_suite['instruction_type'] == 'unseen'
    assert str((parent / 'suite.yml').relative_to(ROOT)) in proofs
    expected_rows = set()
    for spec in suite['tasks']:
        task = spec['task']
        path = BASE / spec['manifest']
        manifest = load_manifest(path)
        checked = validate_manifest(manifest)
        old = next(s for s in parent_suite['tasks'] if s['task'] == task)
        assert spec['task_config'] == manifest['task_config'] == old['task_config']
        assert manifest['task'] == task
        assert manifest_sha256(manifest) == spec['manifest_sha256'] == old['manifest_sha256']
        assert path.read_bytes() == (parent / path.name).read_bytes()
        assert len(checked['block_ids']) == spec['blocks'] == 20
        assert all(n == 20 for n in checked['mode_denominators'].values())
        assert spec['modes'] == checked['mode_denominators']
        assert spec['episodes_per_policy'] == len(manifest['seeds'])
        assert spec['reusable_seeds_per_policy'] == manifest['seeds']
        assert spec['pending_seeds_per_policy'] == []
        for name in (path.name, task + ('.probe.yml' if task == 'arm_select' else '.generation.json')):
            assert str((parent / name).relative_to(ROOT)) in proofs
        expected_rows.update((p, task, seed) for p in suite['policies'] for seed in manifest['seeds'])
    assert {p.name for p in BASE.glob('*.json')} == {s['manifest'] for s in suite['tasks']} | {'qualification-files.json', 'seed-modes.json'}
    reuse = yaml.safe_load((BASE / suite['reuse_index']).read_text())
    rows = reuse['episodes']
    assert len(rows) == reuse['count'] == suite['reusable_episodes'] == 3000
    assert {(r['policy'], r['task'], r['seed']) for r in rows} == expected_rows
    assert Counter(r['policy'] for r in rows) == {p: 500 for p in suite['policies']}
    assert sum(r['success'] for r in rows) == reuse['successes']
    for row in rows:
        assert isinstance(row['success'], bool)
        assert row['mode'] == describe_seed(row['task'], row['seed']).mode
        assert row['source_directory'] == str(Path(reuse['previous_run']) / row['policy'] / row['task'])
        assert row['files_sha256'] and len(row['source_provenance_sha256']) == 64
    assert suite['episodes_per_policy'] == 500
    assert suite['episodes_all_six_policies'] == 3000 and suite['pending_episodes'] == 0
    print('OK: 6 tasks, 20 blocks each, 3000 reusable episodes (successes and failures), 720 complete blocks')


if __name__ == '__main__':
    main()
