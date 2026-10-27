#!/usr/bin/env python3
"""Build and verify the randomized stapler replacement's six-task seed release."""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_contracts import CURRENT_SUITE_TASKS
from if_benchmark.seed_generation import validate_generation_evidence
from if_benchmark.seed_manifest import load_manifest, manifest_sha256, validate_manifest
from if_benchmark.seed_modes import check_seed_modes, export_texts
from tasks.envs._press_lift_bell import CONTEXT_LAYOUT_VERSION
from tasks.envs._press_lift_stapler import (
    INSTRUCTIONS, ROTATION_VERSION, YAW_LIMITS_DEGREES, StaplerMonitor, sample_rotations, stapler_rules,
)
from tools.release_press_lift_bell_v1 import digest, read, write

TASK = 'press_lift_stapler'
NAME = 'robotwin-if-press-lift-stapler-v1-20-per-mode'
RELEASE = ROOT / 'seed-manifests' / NAME
BELL_NAME = 'robotwin-if-press-lift-bell-v1-20-per-mode'


def build(run, base=RELEASE, reference=RELEASE):
    run, base, reference = Path(run).resolve(), Path(base), Path(reference)
    # The current qualified release contains the five inherited manifests and
    # their original evidence; rebuilding does not require retired releases.
    verify(reference)
    parent = yaml.safe_load((reference / 'qualification/parent-suite.yml').read_text())
    manifest = load_manifest(run / 'generated' / f'{TASK}.json')
    evidence = read(run / 'generated' / f'{TASK}.generation.json')
    validate_generation_evidence(manifest, evidence)
    assert len(manifest['seeds']) == 40
    for name, sha in read(run / 'source-hashes.json').items():
        assert digest(ROOT / name) == digest(run / 'source-snapshot' / name) == sha, name
    base.mkdir(parents=True, exist_ok=False)
    for suffix in ('.json', '.generation.json'):
        shutil.copyfile(run / 'generated' / (TASK + suffix), base / (TASK + suffix))
    shutil.copytree(run / 'source-snapshot', base / 'qualification/source-snapshot')
    for name in ('source-hashes.json', 'run.json', 'robotwin-runtime.patch'):
        shutil.copyfile(run / name, base / 'qualification' / name)
    setup_check = run / 'standard-setup/validation.json'
    assert setup_check.is_file(), 'Standard evaluator setup must be checked before publishing'
    shutil.copyfile(setup_check, base / 'qualification/standard-setup-validation.json')
    shutil.copyfile(reference / 'qualification/parent-suite.yml', base / 'qualification/parent-suite.yml')
    shutil.copytree(reference / 'qualification/inherited', base / 'qualification/inherited')
    shutil.copyfile(reference / 'qualification/inherited-files.json', base / 'qualification/inherited-files.json')
    specs = [dict(task=TASK, task_config=manifest['task_config'], manifest=f'{TASK}.json',
        manifest_sha256=manifest_sha256(manifest), blocks=20, episodes_per_policy=40,
        modes={'press': 20, 'lift': 20}, instructions=INSTRUCTIONS, action_limit=250,
        qualification=dict(type='new_paired_expert_generation', evidence=f'{TASK}.generation.json', **evidence['summary']),
        context_sampling_version=CONTEXT_LAYOUT_VERSION, rotation_sampling_version=ROTATION_VERSION,
        yaw_limits_degrees=YAW_LIMITS_DEGREES, success_checker_version=StaplerMonitor.VERSION,
        success_checker_parameters=StaplerMonitor(stapler_rules()).signals()['thresholds'])]
    for original in parent['tasks'][1:]:
        spec = {k: deepcopy(v) for k, v in original.items()
                if k not in ('reusable_seeds_per_policy', 'pending_seeds_per_policy')}
        spec['qualification'] = dict(type='unchanged_parent_manifest', parent_release=parent['release'],
            parent_manifest_sha256=spec['manifest_sha256'],
            original_qualification=original['qualification'], requalified=False)
        specs.append(spec)
        shutil.copyfile(reference / spec['manifest'], base / spec['manifest'])
    suite = dict(schema_version=1, release=base.name, purpose='fixed_seed_evaluation',
        created_at=datetime.now(timezone.utc).isoformat(), parent_release=parent['release'],
        supersedes_release=BELL_NAME, replaced_task='bottle_verb', replacement_task=TASK,
        instruction_type='unseen', blocks_per_task=20, tasks=specs, policies=parent['policies'],
        episodes_per_policy=460, episodes_all_six_policies=2760,
        model_evaluation='not started; pilot scores are not this release',
        evaluation_entrypoint='scripts/eval.sh',
        qualification_note='Only stapler newly qualified; other five manifests and original evidence unchanged. No model outcomes select seeds.')
    (base / 'suite.yml').write_text(yaml.safe_dump(suite, sort_keys=False, allow_unicode=True))
    for name, contents in export_texts(base).items():
        (base / name).write_text(contents)
    accepted = [b for b in evidence['blocks'] if b['accepted']]
    coverage = Counter((b['episodes'][0]['diagnostics']['stapler_id'],
                        'left' if b['block_index'] % 2 == 0 else 'right') for b in accepted)
    write(base / 'qualification-summary.json', dict(**evidence['summary'],
        press_episodes=20, lift_episodes=20, paired_initial_arrays_and_poses_equal=20,
        rotation_sampling_version=ROTATION_VERSION,
        coverage=[dict(stapler_id=model, side=side, blocks=count) for (model, side), count in sorted(coverage.items())],
        inherited_tasks=list(CURRENT_SUITE_TASKS[1:]), inherited_episodes_per_policy=420,
        fresh_model_episodes=0))
    (base / 'verify.py').write_text('''#!/usr/bin/env python3
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.release_press_lift_stapler_v1 import verify
verify(Path(__file__).resolve().parent)
print("OK: six tasks, 20 blocks/task, 460 episodes; qualification and checksums verified")
''')
    rejected = evidence['summary']['rejected_blocks']
    (base / 'README.md').write_text(f'''# Press/Lift Stapler v1 · 六任务 × 20 blocks

当前 Verb 为 `press_lift_stapler`；不包含 Bell 或 Bottle。
其余五个任务的 seeds 与 Arm-only-v2、Bell-v1 完全相同。
共 460 回合/model；六个模型合计 2760 回合。

订书器从 seed 110000 开始顺序筛选，接受 20 组，拒绝 {rejected} 组。
每组 Press/Lift 各一次，expert 均成功，初始图像、机器人状态及位姿相同。
订书器 yaw ±15°，鼠标和玩具车各自 yaw ±180°，由 scene seed 固定。
指令：`Press down on the stapler.` / `Lift the stapler.`；各 250 actions。
没有根据模型表现筛 seed；本版尚未进行模型 eval。

- [六任务清单](suite.yml) · [seed/mode JSON](seed-modes.json) · [CSV](seed-modes.csv)
- [资格汇总](qualification-summary.json) · [订书器筛选记录]({TASK}.generation.json)
- 验证：`python seed-manifests/{NAME}/verify.py`
- 默认评测入口：`scripts/eval.sh`
''')
    files = sorted(p for p in base.rglob('*') if p.is_file())
    (base / 'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.relative_to(base)}\n' for p in files))
    verify(base)


def verify(base=RELEASE):
    base = Path(base)
    for line in (base / 'SHA256SUMS').read_text().splitlines():
        sha, name = line.split(maxsplit=1)
        path = base / name
        assert path.resolve().is_relative_to(base.resolve()) and digest(path) == sha, name
    suite = yaml.safe_load((base / 'suite.yml').read_text())
    parent = yaml.safe_load((base / 'qualification/parent-suite.yml').read_text())
    assert tuple(s['task'] for s in suite['tasks']) == CURRENT_SUITE_TASKS
    assert not any((base / f'{t}.json').exists() for t in ('bottle_verb', 'press_lift_bell'))
    check_seed_modes(base)
    total = 0
    for spec in suite['tasks']:
        manifest = load_manifest(base / spec['manifest'])
        checked = validate_manifest(manifest)
        assert (manifest['task'], manifest['task_config']) == (spec['task'], spec['task_config'])
        assert len(checked['block_ids']) == spec['blocks'] == 20
        assert checked['mode_denominators'] == spec['modes']
        assert manifest_sha256(manifest) == spec['manifest_sha256']
        assert len(manifest['seeds']) == spec['episodes_per_policy']
        total += len(manifest['seeds'])
        if spec['task'] == TASK:
            evidence = read(base / f'{TASK}.generation.json')
            validate_generation_evidence(manifest, evidence)
            assert spec['instructions'] == INSTRUCTIONS and spec['rotation_sampling_version'] == ROTATION_VERSION
            assert spec['yaw_limits_degrees'] == YAW_LIMITS_DEGREES
            assert spec['success_checker_parameters'] == StaplerMonitor(stapler_rules()).signals()['thresholds']
            for block in evidence['blocks']:
                if not block['accepted']:
                    continue
                a, b = [e['diagnostics'] for e in block['episodes']]
                for key in ('initial_arrays', 'initial_position', 'initial_quaternion',
                            'context_initial_positions', 'context_initial_quaternions', 'rotations'):
                    assert a[key] == b[key], (block['block_index'], key)
                assert len(a['initial_arrays']) == 4 and a['rotations'] == sample_rotations(block['block_index'])
                for e in block['episodes']:
                    d = e['diagnostics']; signals = d['signals']
                    assert d['instruction'] == INSTRUCTIONS[e['expected_mode']]
                    assert d['action_limit'] == 250 and d['scene_seed'] == block['block_index']
                    assert d['context_sampling_version'] == CONTEXT_LAYOUT_VERSION
                    assert d['rotation_sampling_version'] == signals['rotation_sampling_version'] == ROTATION_VERSION
                    assert signals['checker_version'] == spec['success_checker_version'] == StaplerMonitor.VERSION
                    assert signals['thresholds'] == spec['success_checker_parameters']
                    assert signals['first_action'] == e['expected_mode']
                    assert signals['target_is_static'] is False and signals['target_mass_kg'] == .05
        else:
            old = next(s for s in parent['tasks'] if s['task'] == spec['task'])
            assert spec['manifest_sha256'] == old['manifest_sha256']
            assert spec['qualification']['original_qualification'] == old['qualification']
            if spec['task'] == 'arm_select':
                q = read(base / 'qualification/inherited/arm-select-cube-v3-20-per-mode/qualification.json')
                assert q['complete'] and q['all_checks_passed']
                assert manifest['seeds'] == [s for b in q['blocks'] if b['accepted'] for s in b['seeds']]
            else:
                old_dir = base / 'qualification/inherited/if-ext-v1-100-per-mode'
                old_manifest = load_manifest(old_dir / spec['manifest'])
                validate_generation_evidence(old_manifest, read(old_dir / f"{spec['task']}.generation.json"))
                assert set(manifest['seeds']) <= set(old_manifest['seeds'])
    assert total == suite['episodes_per_policy'] == 460
    assert total * len(suite['policies']) == suite['episodes_all_six_policies'] == 2760
    for name, receipt in read(base / 'qualification/inherited-files.json').items():
        assert digest(base / name) == receipt['sha256']
    for name, sha in read(base / 'qualification/source-hashes.json').items():
        assert digest(base / 'qualification/source-snapshot' / name) == sha
    setup = read(base / 'qualification/standard-setup-validation.json')
    assert setup['complete'] and setup['model_requests'] == 0
    assert [r['seed'] for r in setup['records']] == read(base / f'{TASK}.json')['seeds'][:2]
    assert all(r['oracle_success'] and r['initial_arrays_match'] and r['step_limit'] == 250 for r in setup['records'])
    return suite


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-from', type=Path)
    args = parser.parse_args()
    if args.build_from:
        build(args.build_from)
    else:
        verify()
    print(f'OK: {RELEASE}')
