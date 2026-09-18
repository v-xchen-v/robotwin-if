"""Validate the spatial3 projection and its unchanged source evidence (CPU only)."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import yaml

# This file is also shipped as <release>/verify.py.
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'if_benchmark').is_dir())
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_contracts import IF_SEED_CONTRACTS, describe_seed, validate_active_seeds
from if_benchmark.seed_manifest import load_manifest, manifest_sha256, validate_manifest
from if_benchmark.seed_modes import build_seed_modes, check_seed_modes
BASE = Path(__file__).resolve().parent
if BASE.name == 'tools':
    BASE = ROOT / 'seed-manifests/if-ext-v2-six-tasks-spatial3-20-per-mode'


def main():
    check_seed_modes(BASE)
    assert build_seed_modes(BASE)['episodes_per_policy'] == 460
    suite = yaml.safe_load((BASE / 'suite.yml').read_text())
    parent = BASE.parent / suite['parent_release']
    proofs = json.loads((BASE / 'qualification-files.json').read_text())
    for name, expected in proofs.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    assert [s['task'] for s in suite['tasks']] == list(IF_SEED_CONTRACTS)
    assert suite['blocks_per_task'] == 20
    keys = set()
    for spec in suite['tasks']:
        task = spec['task']; manifest = load_manifest(BASE / spec['manifest'])
        old = load_manifest(parent / spec['manifest'])
        expected = [s for s in old['seeds'] if describe_seed(task, s).mode in IF_SEED_CONTRACTS[task].modes]
        assert manifest['seeds'] == expected and manifest['task_config'] == old['task_config']
        if task != 'place_relative':
            assert (BASE / spec['manifest']).read_bytes() == (parent / spec['manifest']).read_bytes()
        else:
            assert manifest['schema_version'] == 2
        assert len(validate_active_seeds(task, expected)) == spec['blocks'] == 20
        assert manifest_sha256(manifest) == spec['manifest_sha256']
        assert validate_manifest(manifest)['mode_denominators'] == spec['modes']
        assert spec['episodes_per_policy'] == len(expected)
        assert spec['reusable_seeds_per_policy'] == expected and spec['pending_seeds_per_policy'] == []
        keys.update((p, task, s) for p in suite['policies'] for s in expected)
    reuse = yaml.safe_load((BASE / suite['reuse_index']).read_text())
    source = yaml.safe_load((parent / 'reusable-results.yml').read_text())
    selected = [r for r in source['episodes'] if (r['policy'], r['task'], r['seed']) in keys]
    assert reuse['episodes'] == selected  # Every outcome and artifact digest preserved.
    assert len(selected) == len(keys) == reuse['count'] == suite['reusable_episodes'] == 2760
    assert sum(r['success'] for r in selected) == reuse['successes'] == 1259
    assert Counter(r['policy'] for r in selected) == {p: 460 for p in suite['policies']}
    assert suite['episodes_per_policy'] == 460 and suite['episodes_all_six_policies'] == 2760
    assert suite['pending_episodes'] == 0
    print('OK: 6 tasks, 20 blocks each, 2760 reusable episodes, Spatial left/right/on_top')


if __name__ == '__main__':
    main()
