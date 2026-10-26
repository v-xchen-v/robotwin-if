#!/usr/bin/env python3
"""Build/verify the 20-block bell replacement release without model inference."""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_contracts import CURRENT_SUITE_TASKS
from if_benchmark.seed_generation import validate_generation_evidence
from if_benchmark.seed_manifest import load_manifest, manifest_sha256, validate_manifest
from if_benchmark.seed_modes import check_seed_modes, export_texts
from tasks.envs._press_lift_bell import BellMonitor, BellRules, CONTEXT_LAYOUT_VERSION, INSTRUCTIONS
from tools.release_history import REVISION

NAME = 'robotwin-if-press-lift-bell-v1-20-per-mode'
RELEASE = ROOT / 'seed-manifests' / NAME
PARENT = ROOT / 'seed-manifests/robotwin-if-arm-only-v2-20-per-mode'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def qualification_instructions(base, spec):
    """Check an in-place text override while retaining the original expert evidence."""
    override = spec.get('instruction_override')
    if override is None:
        return spec['instructions']
    previous = override['previous_instructions']
    assert previous['press'] == spec['instructions']['press']
    assert previous['lift'] == 'Pick up the bell.' and spec['instructions']['lift'] == 'Lift the bell.'
    helper = 'tasks/envs/_press_lift_bell.py'
    description = 'tasks/task_instruction/press_lift_bell.json'
    assert set(override['source_sha256']) == {helper, description}
    original = base / 'qualification/source-snapshot'
    updated = base / 'qualification/instruction-override'
    for name, sha in override['source_sha256'].items():
        assert digest(updated / name) == sha
    # The physical scene, RNG and success checker must remain byte-identical.
    assert (updated / helper).read_text() == (original / helper).read_text().replace(
        previous['lift'], spec['instructions']['lift'])
    expected = read(original / description)
    expected['schema'] = expected['schema'].replace(previous['lift'], spec['instructions']['lift'])
    expected['full_description'] = expected['full_description'].replace('pick up', 'lift')
    assert read(updated / description) == expected
    return previous


def build(run, base=RELEASE):
    from dataclasses import asdict
    run = run.resolve()
    manifest = load_manifest(run / 'generated/press_lift_bell.json')
    evidence = read(run / 'generated/press_lift_bell.generation.json')
    validate_generation_evidence(manifest, evidence)
    assert len(manifest['seeds']) == 40
    # Do not publish a qualification produced while its sources changed.
    for name, sha in read(run / 'source-hashes.json').items():
        assert digest(ROOT / name) == digest(run / 'source-snapshot' / name) == sha, name
    base.mkdir(parents=True, exist_ok=False)
    for name in ('press_lift_bell.json', 'press_lift_bell.generation.json'):
        shutil.copyfile(run / 'generated' / name, base / name)
    shutil.copytree(run / 'source-snapshot', base / 'qualification/source-snapshot')
    for name in ('source-hashes.json', 'run.json', 'robotwin-runtime.patch'):
        shutil.copyfile(run / name, base / 'qualification' / name)
    if (run / 'standard-setup/validation.json').is_file():
        shutil.copyfile(run / 'standard-setup/validation.json', base / 'qualification/standard-setup-validation.json')
        shutil.copyfile(run / 'check_standard_setup.py', base / 'qualification/check_standard_setup.py')
    parent = yaml.safe_load((PARENT / 'suite.yml').read_text())
    shutil.copyfile(PARENT / 'suite.yml', base / 'qualification/parent-suite.yml')
    specs = [dict(task='press_lift_bell', task_config=manifest['task_config'],
        manifest='press_lift_bell.json', manifest_sha256=manifest_sha256(manifest),
        blocks=20, episodes_per_policy=40, modes={'press': 20, 'lift': 20},
        qualification=dict(type='new_paired_expert_generation', evidence='press_lift_bell.generation.json',
                           **evidence['summary']),
        instructions=INSTRUCTIONS, action_limit=250, context_sampling_version=CONTEXT_LAYOUT_VERSION,
        success_checker_version=BellMonitor.VERSION, success_checker_parameters=asdict(BellRules()))]
    inherited = {}
    for original in parent['tasks'][1:]:
        task = original['task']
        spec = {k: deepcopy(v) for k, v in original.items()
                if k not in ('reusable_seeds_per_policy', 'pending_seeds_per_policy')}
        spec['qualification'] = dict(type='unchanged_parent_manifest',
            parent_release=PARENT.name, parent_manifest_sha256=spec['manifest_sha256'],
            original_qualification=original['qualification'], requalified=False)
        specs.append(spec)
        shutil.copyfile(PARENT / spec['manifest'], base / spec['manifest'])
        # Keep the original qualification bytes with Git identity, including failures.
        if task == 'arm_select':
            names = ['arm-select-cube-v3-20-per-mode/qualification.json']
        else:
            names = [f'if-ext-v1-100-per-mode/{task}{suffix}' for suffix in ('.json', '.generation.json')]
        for name in names:
            git_path = 'seed-manifests-archive/' + name
            local = 'qualification/inherited/' + name
            payload = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{REVISION}:{git_path}'])
            dest = base / local
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(payload)
            inherited[local] = dict(git_commit=REVISION, git_path=git_path, sha256=digest(dest))
    write(base / 'qualification/inherited-files.json', inherited)
    suite = dict(schema_version=1, release=base.name, purpose='fixed_seed_evaluation',
        created_at=datetime.now(timezone.utc).isoformat(), parent_release=PARENT.name,
        replaced_task='bottle_verb', replacement_task='press_lift_bell',
        instruction_type='unseen', blocks_per_task=20, tasks=specs, policies=parent['policies'],
        episodes_per_policy=460, episodes_all_six_policies=2760,
        model_evaluation='paused; no scores generated or imported for this release',
        evaluation_entrypoint='scripts/eval.sh',
        qualification_note='Only bell is newly expert-qualified. The five other manifests and their qualification evidence are inherited unchanged; policy failures never select seeds.')
    (base / 'suite.yml').write_text(yaml.safe_dump(suite, sort_keys=False, allow_unicode=True))
    for name, contents in export_texts(base).items():
        (base / name).write_text(contents)
    accepted = [b for b in evidence['blocks'] if b['accepted']]
    coverage = Counter((b['episodes'][0]['diagnostics']['bell_id'],
                        'left' if b['block_index'] % 2 == 0 else 'right') for b in accepted)
    write(base / 'qualification-summary.json', dict(
        **evidence['summary'], press_episodes=20, lift_episodes=20, paired_initial_arrays_equal=20,
        coverage=[dict(bell_id=model, side=side, blocks=count) for (model, side), count in sorted(coverage.items())],
        inherited_tasks=list(CURRENT_SUITE_TASKS[1:]), inherited_episodes_per_policy=420,
        fresh_model_episodes=0))
    (base / 'verify.py').write_text('''#!/usr/bin/env python3
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.release_press_lift_bell_v1 import verify
verify(Path(__file__).resolve().parent)
print("OK: six tasks, 20 blocks/task, 460 episodes; qualification and checksums verified")
''')
    rejected = evidence['summary']['rejected_blocks']
    (base / 'README.md').write_text(f'''# Press/Lift Bell v1 · 六任务 × 20 blocks

旧版为 `{PARENT.name}`；本版只把 `bottle_verb` 替换为 `press_lift_bell`。
其余五份 flat manifest 与旧版逐字节相同，沿用原资格证据；旧目录保留。
每个任务 20 个完整 blocks，共 460 回合/model；六个模型合计 2760 回合。

铃铛为 20 个场景，每场景 Press/Lift 各一次：`2k` 是 Press，`2k+1` 是 Lift。
指令为 **{INSTRUCTIONS['press']}** / **{INSTRUCTIONS['lift']}**，均为 250 actions。
`seen`/`unseen` 返回这同一组固定指令，并非两个不同语言池。
使用 `random-back-region-v1` distractors 和 `{BellMonitor.VERSION}` 判据。
物理步长为 4 ms，每步采样，保留零冲量 contact；完整 Press 仍要求回撤和释放。

从 episode seed 100000 开始顺序筛选，接受 20 blocks，拒绝 {rejected} blocks。
只按 expert 的 setup/plan/success 及配对初始 RGB/proprio 一致性筛选，整组接受或拒绝。
没有启动模型评测，也没有导入旧版模型成绩。

- [suite](suite.yml) · [seed/mode JSON](seed-modes.json) · [CSV](seed-modes.csv)
- [筛选汇总](qualification-summary.json) · [完整筛选记录](press_lift_bell.generation.json)
- `qualification/` 保存旧资格原件、Git 路径和哈希、新源码快照、运行命令及 runtime patch。
- runtime patch 记录本机已有 UTF-8 IO / episode_num 设置；没有修改 RoboTwin gitlink。
- 跨机器复现需匹配源码、配置、资产与模拟器环境；保存的数组哈希来自本次运行主机。

```bash
python seed-manifests/{NAME}/verify.py
bash scripts/eval.sh --policy lingbot_va --manifest-dir seed-manifests/{NAME} --blocks 20 --output-dir outputs/policy-eval/bell-v1-lva --dry-run
```

后续评测使用 `scripts/eval.sh --manifest-dir`，继续保留每个固定 seed 的模型失败。
`tools/run_formal_policy_suite.py` 是旧成绩复用工作流，依赖旧模型元数据，不作为本版新任务入口。
''')
    (base / 'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.relative_to(base)}\n'
        for p in sorted(base.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'))
    verify(base)


def verify(base=RELEASE):
    from dataclasses import asdict
    base = Path(base)
    for line in (base / 'SHA256SUMS').read_text().splitlines():
        sha, name = line.split(maxsplit=1)
        path = base / name
        assert path.resolve().is_relative_to(base.resolve()) and digest(path) == sha, name
    suite = yaml.safe_load((base / 'suite.yml').read_text())
    parent = yaml.safe_load((base / 'qualification/parent-suite.yml').read_text())
    assert tuple(t['task'] for t in suite['tasks']) == CURRENT_SUITE_TASKS
    assert not (base / 'bottle_verb.json').exists()
    check_seed_modes(base)
    total = 0
    for spec in suite['tasks']:
        manifest = load_manifest(base / spec['manifest'])
        checked = validate_manifest(manifest)
        assert manifest['task'] == spec['task'] and manifest['task_config'] == spec['task_config']
        assert len(checked['block_ids']) == spec['blocks'] == 20
        assert checked['mode_denominators'] == spec['modes']
        assert manifest_sha256(manifest) == spec['manifest_sha256']
        assert len(manifest['seeds']) == spec['episodes_per_policy']
        total += len(manifest['seeds'])
        if spec['task'] == 'press_lift_bell':
            original_instructions = qualification_instructions(base, spec)
            evidence = read(base / 'press_lift_bell.generation.json')
            validate_generation_evidence(manifest, evidence)
            for block in evidence['blocks']:
                if not block['accepted']:
                    continue
                a, b = [e['diagnostics'] for e in block['episodes']]
                assert a['initial_arrays'] == b['initial_arrays'] and len(a['initial_arrays']) == 4
                assert a['initial_position'] == b['initial_position']
                assert a['context_initial_positions'] == b['context_initial_positions']
                for episode in block['episodes']:
                    d = episode['diagnostics']
                    assert d['instruction'] == original_instructions[episode['expected_mode']]
                    assert d['action_limit'] == 250 and d['scene_seed'] == block['block_index']
                    assert d['context_sampling_version'] == CONTEXT_LAYOUT_VERSION
                    assert d['signals']['checker_version'] == BellMonitor.VERSION
                    assert d['signals']['thresholds'] == asdict(BellRules())
                    assert d['signals']['first_action'] == episode['expected_mode']
        else:
            old = next(s for s in parent['tasks'] if s['task'] == spec['task'])
            assert spec['manifest_sha256'] == old['manifest_sha256']
            assert spec['qualification']['original_qualification'] == old['qualification']
            if spec['task'] == 'arm_select':
                q = read(base / 'qualification/inherited/arm-select-cube-v3-20-per-mode/qualification.json')
                assert q['complete'] and q['all_checks_passed']
                assert manifest['seeds'] == [s for b in q['blocks'] if b['accepted'] for s in b['seeds']]
            else:
                directory = base / 'qualification/inherited/if-ext-v1-100-per-mode'
                old_manifest = load_manifest(directory / spec['manifest'])
                old_evidence = read(directory / f"{spec['task']}.generation.json")
                validate_generation_evidence(old_manifest, old_evidence)
                assert set(manifest['seeds']) <= set(old_manifest['seeds'])
    assert total == suite['episodes_per_policy'] == 460
    assert total * len(suite['policies']) == suite['episodes_all_six_policies'] == 2760
    for name, receipt in read(base / 'qualification/inherited-files.json').items():
        assert digest(base / name) == receipt['sha256']
    for name, sha in read(base / 'qualification/source-hashes.json').items():
        assert digest(base / 'qualification/source-snapshot' / name) == sha
    setup_check = base / 'qualification/standard-setup-validation.json'
    if setup_check.exists():
        report = read(setup_check)
        assert report['complete'] and report['model_requests'] == 0
        assert [r['seed'] for r in report['records']] == read(base / 'press_lift_bell.json')['seeds'][:2]
        for row in report['records']:
            assert row['oracle_success'] and row['initial_arrays_match'] and row['step_limit'] == 250
    return suite


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-from', type=Path, help='completed bell generation run directory')
    args = parser.parse_args()
    if args.build_from:
        build(args.build_from)
    else:
        verify()
    print(f'OK: {RELEASE}')
