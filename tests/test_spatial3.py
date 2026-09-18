"""Spatial scope migration: preserve scene identity and reject retired execution."""
import ast
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from if_benchmark.seed_contracts import describe_seed, expand_block, first_block_at_or_above, validate_active_seeds
from if_benchmark.seed_generation import new_generation_state, run_generation, validate_generation_state, GenerationError
from if_benchmark.seed_manifest import validate_manifest, ManifestError, load_manifest
from policies.xvla.eval import select_seeds
import test_formal_result_scope as scope
from tools import summarize_formal_policy_results as report

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'seed-manifests/robotwin-if-arm-only-v2-20-per-mode'
RESULT = ROOT / 'result/robotwin-if-arm-only-v2-20blocks'


class SparseSpatialTest(unittest.TestCase):
    def test_sparse_seeds_keep_original_directions_and_scene_groups(self):
        manifest = load_manifest(RELEASE / 'place_relative.json')
        self.assertEqual(len(manifest['seeds']), 60)
        for i in range(0, 60, 3):
            seeds = manifest['seeds'][i:i+3]
            scene = seeds[0] // 5
            self.assertEqual(seeds, [5*scene, 5*scene+1, 5*scene+4])
            self.assertEqual([describe_seed('place_relative', s).mode for s in seeds], ['left', 'right', 'on_top'])
            self.assertEqual({describe_seed('place_relative', s).scene_index for s in seeds}, {scene})
            self.assertEqual(list(expand_block('place_relative', scene)), seeds)
        self.assertEqual(first_block_at_or_above('place_relative', 100001), 20001)
        self.assertEqual(first_block_at_or_above('place_relative', 100004), 20001)

    def test_schema_version_disambiguates_old_and_sparse_manifest(self):
        old = dict(schema_version=1, task='place_relative', task_config='demo_clean', seeds=[0,1,2,3,4])
        new = dict(old, schema_version=2, seeds=[0,1,4])
        self.assertEqual(len(validate_manifest(old)['mode_denominators']), 5)
        self.assertEqual(validate_manifest(new)['mode_denominators'], dict(left=1,right=1,on_top=1))
        for bad in (dict(old, schema_version=2), dict(new, schema_version=1), dict(new, seeds=[0,1,2])):
            with self.assertRaises(ManifestError): validate_manifest(bad)
        with self.assertRaisesRegex(ValueError, 'Retired'): validate_active_seeds('place_relative', old['seeds'])

    def test_all_policy_seed_entrypoint_rejects_old_manifest_even_for_one_block(self):
        args = SimpleNamespace(task='place_relative', task_config='demo_clean', blocks=1,
                               instruction_type='unseen')
        with tempfile.TemporaryDirectory() as temporary:
            args.seed_manifest = Path(temporary) / 'old.json'
            args.seed_manifest.write_text(json.dumps(dict(schema_version=1, task='place_relative',
                task_config='demo_clean', seeds=[0, 1, 2, 3, 4])))
            with self.assertRaisesRegex(ValueError, 'Retired'): select_seeds(args)
        args.seed_manifest=RELEASE/'place_relative.json'
        seeds, _, _ = select_seeds(args)
        self.assertEqual(seeds, load_manifest(args.seed_manifest)['seeds'][:3])

    def test_generation_probes_only_three_modes_and_old_state_is_read_only(self):
        state = new_generation_state(task='place_relative', task_config='demo_clean', accepted_blocks=2,
            max_candidate_blocks=2, candidate_floor=100000, provenance={})
        seen=[]
        def probe(seed):
            mode = describe_seed("place_relative", seed).mode
            seen.append((seed, mode))
            return dict(setup_ok=True,plan_success=True,check_success=True,observed_mode=mode)
        run_generation(state, probe)
        self.assertEqual([s for s,m in seen], [100000,100001,100004,100005,100006,100009])
        legacy = new_generation_state(task='place_relative',task_config='demo_clean',accepted_blocks=1,
            max_candidate_blocks=1,candidate_floor=100000,provenance={})
        legacy['contract_schema_version']=1
        validate_generation_state(legacy)
        with self.assertRaisesRegex(GenerationError, 'read-only'): run_generation(legacy, probe)

    def test_invalid_task_seed_and_override_fail_before_sim_initialization(self):
        tree=ast.parse((ROOT/'tasks/envs/place_relative.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        cls.body=[n for n in cls.body if (isinstance(n,ast.FunctionDef) and n.name=='setup_demo') or
                  (isinstance(n,ast.Assign) and n.targets[0].id in ('ORDER','SEED_MODES','DIRECTION'))]
        class Base:
            def _init_task_env_(self, **kwargs): self.initialized=True
        namespace=dict(Base_Task=Base, apply_if_eval_step_limit=lambda task: None)
        exec(compile(ast.Module(body=[cls],type_ignores=[]),'<task>','exec'),namespace)
        for seed in (2,3,100007,100008):
            task=namespace['place_relative']()
            with self.assertRaisesRegex(ValueError,'retired'):task.setup_demo(seed=seed)
            self.assertFalse(hasattr(task,'initialized'))
        task=namespace['place_relative']();task.DIRECTION='front'
        with self.assertRaisesRegex(ValueError,'only'):task.setup_demo(seed=4)
        self.assertFalse(hasattr(task,'initialized'))
        task.DIRECTION=None;task.setup_demo(seed=4);self.assertTrue(task.initialized)

    def test_current_frozen_result_has_only_active_modes_and_independent_counts(self):
        def read_csv(path):
            with path.open(newline='') as f:return list(csv.DictReader(f))
        kept=read_csv(RESULT/'episodes.csv')
        spatial=[r for r in kept if r['task']=='place_relative']
        self.assertEqual({r['mode'] for r in spatial}, {'left','right','on_top'})
        self.assertEqual(len(spatial),360)
        self.assertEqual(len(kept),2760)
        self.assertEqual(sum(int(r['success']) for r in kept),1097)
        data=json.loads((RESULT/'results.json').read_text())
        for policy,p in data['policies'].items():
            scores=[]
            for task in data['tasks']:
                rows=[r for r in kept if r['policy']==policy and r['task']==task]
                scores.append(100*sum(int(r['success']) for r in rows)/len(rows))
            self.assertAlmostEqual(p['overall_pct'],sum(scores)/6)
            self.assertEqual((p['recorded'],p['complete_blocks']),(460,120))
        for line in (RESULT/'SHA256SUMS').read_text().splitlines():
            sha,name=line.split(maxsplit=1)
            self.assertEqual(hashlib.sha256((RESULT/name).read_bytes()).hexdigest(),sha)


class PartialSpatialScopeTest(unittest.TestCase):
    setUp = scope.ResultScopeTest.setUp
    fixture = scope.ResultScopeTest.fixture
    def test_missing_retired_episode_does_not_block_current_but_missing_top_does(self):
        self.fixture()
        path=self.base/'summary.json';source=json.loads(path.read_text())
        row=next(r for r in source['tasks'] if r['policy']=='xvla' and r['task']=='place_relative')
        row.update(pending_seeds=[2],completed_blocks=0,recorded_episodes=4,complete=False,successes=4)
        row['per_mode']['front'].update(recorded=0,successes=0)
        source['completed_episodes']-=1;source['successes']-=1;source['completed_blocks']-=1
        path.write_text(json.dumps(source))
        current=report.snapshot(self.base)
        self.assertIsNotNone(current['policies']['xvla']['overall_pct'])
        self.assertIsNone(report.snapshot(self.base,include_archived_modes=True)['policies']['xvla']['overall_pct'])
        row['pending_seeds'].append(4);row['recorded_episodes']-=1;row['successes']-=1
        row['per_mode']['on_top'].update(recorded=0,successes=0)
        source['completed_episodes']-=1;source['successes']-=1;path.write_text(json.dumps(source))
        current=report.snapshot(self.base)
        self.assertIsNone(current['policies']['xvla']['overall_pct'])
        spatial=next(r for r in current['rows'] if r['policy']=='xvla' and r['task']=='place_relative')
        self.assertEqual((spatial['recorded_episodes'],spatial['included_episodes']),(2,0))
