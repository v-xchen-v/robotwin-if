#!/usr/bin/env python3
"""Build/verify Attribute target-only-v2 and package its six-policy rerun."""
import argparse
import ast
from collections import Counter
from copy import deepcopy
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_contracts import IF_SEED_CONTRACTS
from if_benchmark.seed_manifest import load_manifest, manifest_sha256, validate_manifest
from if_benchmark.seed_modes import check_seed_modes, export_texts
from tools.run_formal_policy_suite import (
    MAX_ORACLE_ATTEMPTS, POLICIES, digest, is_oracle_setup_failure,
    current_success_checker, matches_success_checker, validate_episode,
)
from tools.summarize_formal_policy_results import generate, snapshot

PARENT = ROOT / 'seed-manifests/robotwin-if-cube-v3-20-per-mode'
PARENT_RESULT = ROOT / 'result/robotwin-if-cube-v3-20blocks'
RELEASE = ROOT / 'seed-manifests/robotwin-if-attribute-v2-20-per-mode'
OLD_RUN = Path('/Data/robotwin-if/evaluations/robotwin-if-cube-v3-20blocks-001')
RUN = Path('/Data/robotwin-if/evaluations/robotwin-if-attribute-v2-20blocks-001')
RESULT = ROOT / 'result/robotwin-if-attribute-v2-20blocks'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def prior_rows():
    with (PARENT_RESULT / 'episodes.csv').open(newline='') as stream:
        return {(r['policy'], r['task'], int(r['seed'])): r for r in csv.DictReader(stream)}


def source_audit(old):
    prior_hashes = read(old / 'support/source-hashes.json')
    differences = [name for name, sha in prior_hashes.items()
                   if not (ROOT / name).exists() or digest(ROOT / name) != sha]
    allowed = {'tasks/envs/_if_grounding.py', 'tasks/envs/attribute_select.py',
               'third_party/robotwin/envs/_if_grounding.py',
               'third_party/robotwin/envs/attribute_select.py', 'tools/run_formal_policy_suite.py'}
    assert set(differences) <= allowed, differences
    for prefix in ('tasks/envs', 'third_party/robotwin/envs'):
        name = prefix + '/_if_grounding.py'
        before = ast.parse((old / 'support/source-snapshot' / name).read_text())
        after = ast.parse((ROOT / name).read_text())
        added = after.body.pop()
        assert isinstance(added, ast.ClassDef) and added.name == 'AttributePickMonitor'
        assert ast.dump(before) == ast.dump(after), 'Existing shared grounding code changed'
    return dict(previous_run=str(old), reused_episodes=1800, new_attribute_select_episodes=960,
        source_differences=differences,
        source_difference_sha256={name: digest(ROOT / name) for name in differences},
        unchanged_five_task_sources=True, unchanged_all_six_task_manifests=True,
        shared_grounding_audit='AST unchanged after removing the added AttributePickMonitor class.',
        runner_change='Pin Attribute checker contract and default to this release; inference logic unchanged.',
        checkpoint_metadata='Retain prior run metadata and services-before-recovery.json through formal prepare.')


def verify(base=RELEASE):
    suite = yaml.safe_load((base / 'suite.yml').read_text())
    assert suite['policies'] == POLICIES
    assert [s['task'] for s in suite['tasks']] == list(IF_SEED_CONTRACTS)
    assert suite['blocks_per_task'] == 20
    check_seed_modes(base)
    for filename, expected in read(base / 'qualification-files.json').items():
        assert digest(ROOT / filename) == expected, filename
    specs = {s['task']: s for s in suite['tasks']}
    expected_keys = set()
    for task, spec in specs.items():
        source = PARENT
        path = base / spec['manifest']
        assert path.read_bytes() == (source / spec['manifest']).read_bytes(), task
        manifest = load_manifest(path)
        checked = validate_manifest(manifest)
        assert manifest['task_config'] == spec['task_config']
        assert manifest_sha256(manifest) == spec['manifest_sha256']
        assert len(checked['block_ids']) == spec['blocks'] == 20
        assert checked['mode_denominators'] == spec['modes']
        assert spec['episodes_per_policy'] == len(manifest['seeds'])
        reusable = [] if task == 'attribute_select' else manifest['seeds']
        pending = manifest['seeds'] if task == 'attribute_select' else []
        assert spec['reusable_seeds_per_policy'] == reusable
        assert spec['pending_seeds_per_policy'] == pending
        expected_keys.update((p, task, seed) for p in POLICIES for seed in reusable)
    assert specs['arm_select']['task_config'] == 'demo_clean_arm_select_v3'
    assert {k: specs['attribute_select'][k] for k in current_success_checker('attribute_select')} == current_success_checker('attribute_select')
    assert source_audit(Path(suite['previous_formal_run'])) == read(base / 'reuse-audit.json')
    reuse = yaml.safe_load((base / suite['reuse_index']).read_text())
    rows = reuse['episodes']
    keys = [(r['policy'], r['task'], r['seed']) for r in rows]
    assert len(keys) == len(set(keys)) == len(expected_keys) == 1800
    assert set(keys) == expected_keys
    old = prior_rows()
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
            print(f'Verified source artifacts for {index}/1800 reused episodes', flush=True)
    assert Counter(r['policy'] for r in rows) == {p: 300 for p in POLICIES}
    assert reuse['count'] == suite['reusable_episodes'] == 1800
    assert reuse['successes'] == sum(r['success'] for r in rows)
    assert suite['pending_episodes'] == 960
    assert suite['episodes_per_policy'] == 460 and suite['episodes_all_six_policies'] == 2760
    print('OK: 6 tasks x 20 blocks; 1800 unchanged reusable episodes; 960 Attribute target-only-v2 episodes pending', flush=True)


def build(base, old):
    assert not base.exists(), 'Refuse to overwrite a taskset'
    for line in (PARENT_RESULT / 'SHA256SUMS').read_text().splitlines():
        expected, filename = line.split(maxsplit=1)
        assert digest(PARENT_RESULT / filename.lstrip('*')) == expected, filename
    assert read(old / 'status.json')['status'] == 'complete'
    assert read(old / 'validation.json')['complete']
    suite = deepcopy(yaml.safe_load((PARENT / 'suite.yml').read_text()))
    suite.update(release=base.name, created_at=datetime.now(timezone.utc).isoformat(),
                 previous_formal_run=str(old), parent_release=PARENT.name, supersedes=PARENT.name,
                 reusable_episodes=1800, pending_episodes=960,
                 reuse_condition='Reuse every outcome of the other five tasks from the completed cube-v3 run.',
                 qualification_note='All six flat manifests are byte-identical to cube-v3. Attribute reruns all 160 seeds with target-only-lift-v2; both-target oracle feasibility remains required before policy inference.')
    base.mkdir(parents=True)
    for spec in suite['tasks']:
        task = spec['task']
        source = PARENT
        shutil.copy2(source / spec['manifest'], base / spec['manifest'])
        manifest = load_manifest(base / spec['manifest'])
        spec.update(task_config=manifest['task_config'], manifest_sha256=manifest_sha256(manifest),
                    reusable_seeds_per_policy=[] if task == 'attribute_select' else manifest['seeds'],
                    pending_seeds_per_policy=manifest['seeds'] if task == 'attribute_select' else [])
        spec.update(current_success_checker(task))
    rows = []
    for policy in POLICIES:
        for spec in suite['tasks']:
            for seed in spec['reusable_seeds_per_policy']:
                directory = old / policy / spec['task']
                marker = directory / f"{spec['task']}_ep{seed}_provenance.json"
                record = read(marker)
                rows.append(dict(policy=policy, task=spec['task'], seed=seed, success=record['success'],
                    mode=record['mode'], source_directory=str(directory), files_sha256=record['files_sha256'],
                    source_provenance_sha256=digest(marker)))
    reuse = dict(count=len(rows), successes=sum(r['success'] for r in rows), previous_run=str(old), episodes=rows)
    (base / 'suite.yml').write_text(yaml.safe_dump(suite, sort_keys=False))
    (base / 'reusable-results.yml').write_text(yaml.safe_dump(reuse, sort_keys=False))
    sources = [PARENT / 'suite.yml', PARENT / 'qualification-files.json',
               *[PARENT / f'{task}.json' for task in IF_SEED_CONTRACTS],
               *[PARENT_RESULT / name for name in ('SHA256SUMS', 'episodes.csv', 'plan.json', 'checkpoints.json', 'validation.json')],
               *[p for p in (ROOT / 'result/attribute-select-target-only-v2-review').iterdir() if p.is_file()]]
    write(base / 'qualification-files.json', {str(p.relative_to(ROOT)): digest(p) for p in sources})
    write(base / 'reuse-audit.json', source_audit(old))
    for name, content in export_texts(base).items():
        (base / name).write_text(content)
    (base / 'verify.py').write_text('''from pathlib import Path
import sys
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'if_benchmark').is_dir())
sys.path.insert(0, str(ROOT))
from tools.release_attribute_select_v2 import verify
verify(Path(__file__).resolve().parent)
''')
    (base / 'README.md').write_text('''# RoboTwin-IF Attribute-v2：六任务 × 20 blocks

每个 policy 460 回合；六个 policies 合计 2760 回合、720 blocks。
全部六份 flat manifest 与上一版 cube-v3 逐字节一致。
本轮重跑 Attribute-Select 的 960 回合；其他五任务的 1800 回合逐字节复用 cube-v3，包含成功和失败。
Arm 保留 5 cm cube-v3，Bottle 保留 v6 terminal 判据，Spatial 保留 left/right/on_top。

Attribute 使用 `target-only-lift-v2`：目标当前抬升严格超过 5 cm，且干扰物整回合从未越过该阈值。
位置、指令、400-action 预算、双目标 oracle gate、checkpoints 与推理参数均保持原版。
诊断回放不能替代本轮新的模型推理。

- [套件配置](suite.yml) · [seed/mode JSON](seed-modes.json) · [CSV](seed-modes.csv)
- [复用索引与 artifact SHA-256](reusable-results.yml) · [源码复用审计](reuse-audit.json)
- [判据修复与回放证据](../../docs/attribute-select-target-only.md)

校验：`python seed-manifests/robotwin-if-attribute-v2-20-per-mode/verify.py`。
正式入口：`tools/run_formal_policy_suite.py prepare/run`，prepare 指定本目录、独立 `--run-dir` 和上一版 cube-v3 的 `--old-run`。
''')
    verify(base)


def oracle_setup_audit(run):
    """Export pre-inference failures and their exact-seed recovery evidence."""
    decisions, attempts, affected = [], {}, set()
    for path in sorted((run / 'batches').glob('*/*/attribute_select-oracle-retry.json')):
        decision = read(path)
        policy, seed = path.parent.name, decision['seed']
        assert policy in POLICIES and seed in read(run / 'manifests/attribute_select.json')['seeds']
        assert decision['policy_results_retried'] is False
        assert decision['max_attempts'] == MAX_ORACLE_ATTEMPTS
        assert decision['prior_failed_attempts'] == len(decision['failed_records'])
        assert 0 < decision['prior_failed_attempts'] < MAX_ORACLE_ATTEMPTS
        final = run / policy / 'attribute_select' / f'attribute_select_ep{seed}_result.json'
        result = read(final)
        assert result['seed'] == seed and result['status'] in ('success', 'failure')
        affected.add((policy, seed))
        decisions.append(dict(path=str(path.relative_to(run)), sha256=digest(path),
            policy=policy, seed=seed, decision=decision,
            final_record=str(final.relative_to(run)), final_record_sha256=digest(final)))
        for filename in decision['failed_records']:
            failed = Path(filename).resolve()
            relative = str(failed.relative_to(run.resolve()))
            record = read(failed)
            assert is_oracle_setup_failure(record) and record['seed'] == seed
            assert failed.parent.name == 'attribute_select' and failed.parent.parent.name == policy
            attempts[relative] = dict(path=relative, sha256=digest(failed), record=record)
    observed = {str(p.relative_to(run)) for p in (run / 'batches').glob('*/*/attribute_select/*_result.json')
                if is_oracle_setup_failure(read(p))}
    assert set(attempts) == observed, 'Every oracle setup failure must have a retry decision'
    return dict(schema_version=1, failed_setup_attempts=len(attempts),
        affected_episodes=[dict(policy=p, seed=s) for p, s in sorted(affected)],
        policy_results_retried=False, seeds_substituted=False,
        scope='Only oracle negatives before any model inference; exact seed recovered in a fresh simulator.',
        decisions=decisions, failed_attempts=[attempts[p] for p in sorted(attempts)])


def package(base, run, target):
    import numpy as np
    validation = read(run / 'validation.json')
    status = read(run / 'status.json')
    assert status['status'] == 'complete' and validation['complete']
    assert validation['validated_episodes'] == 2760
    assert validation['counts'] == {'reused': 1800, 'new': 960}
    data = snapshot(run)
    old_data = read(PARENT_RESULT / 'results.json')
    assert [r for r in data['rows'] if r['task'] != 'attribute_select'] == [r for r in old_data['rows'] if r['task'] != 'attribute_select']
    assert data['summary']['completed_blocks'] == 720
    assert data['task_configs']['arm_select'] == 'demo_clean_arm_select_v3'
    retry_audit = oracle_setup_audit(run)
    assert not target.exists(), 'Refuse to overwrite a result package'
    plan = read(run / 'plan.json')
    old = prior_rows()
    rows = []
    comparison = []
    fields = ['policy','task','block_index','seed','mode','status','success','action_calls',
              'step_limit','termination','instruction','origin','record_path','record_sha256']
    for policy in POLICIES:
        for spec in plan['tasks']:
            task = spec['task']
            for seed in spec['seeds']:
                stem = run / policy / task / f'{task}_ep{seed}'
                marker = read(Path(str(stem) + '_provenance.json'))
                record_path = Path(str(stem) + '_result.json')
                record = read(record_path)
                row = {k: record[k] for k in ('seed','mode','status','action_calls','step_limit','termination','instruction')}
                row.update(policy=policy, task=task, block_index=marker['formal_block'], success=int(record['success']),
                           origin=marker['origin'], record_path=str(record_path.relative_to(run)), record_sha256=digest(record_path))
                assert row['record_sha256'] == marker['files_sha256'][record_path.name]
                assert row['origin'] == ('new' if task == 'attribute_select' else 'reused')
                if task != 'attribute_select':
                    assert all(str(row[k]) == old[policy, task, seed][k] for k in fields if k != 'origin')
                else:
                    assert record['step_limit'] == 400
                    assert matches_success_checker(spec, record)
                    signals = record['signals']
                    assert record['success'] == (signals['target_lifted'] and not signals['distractor_lifted_ever'])
                    old_initial = Path(plan['old_run']) / policy / task / f'{task}_ep{seed}_initial_observation.npz'
                    with np.load(str(stem) + '_initial_observation.npz') as new, np.load(old_initial) as prior:
                        assert set(new.files) == set(prior.files)
                        for key in new.files:
                            np.testing.assert_array_equal(new[key], prior[key], err_msg=f'{policy}/{seed}/{key}')
                    comparison.append(dict(policy=policy, seed=seed, mode=record['mode'],
                        previous_success=int(old[policy, task, seed]['success']), success=int(record['success']),
                        first_lifted=signals['first_lifted'],
                        distractor_lifted_ever=signals['distractor_lifted_ever'],
                        first_distractor_lift_action=signals['first_distractor_lift_action'],
                        target_lift_m=signals['lift_m']['target'],
                        distractor_lift_m=signals['lift_m']['distractor'],
                        distractor_peak_lift_m=signals['peak_lift_m']['distractor'],
                        video=str(record_path.with_name(record_path.name.replace('_result.json', f"_{int(record['success'])}.mp4")).relative_to(run))))
                rows.append(row)
    target.mkdir(parents=True)
    (target / 'manifests').mkdir()
    with (target / 'episodes.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    with (target / 'attribute-comparison.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(comparison[0]))
        writer.writeheader(); writer.writerows(comparison)
    generate(data, target / 'results.md')
    for task in IF_SEED_CONTRACTS:
        shutil.copy2(run / 'manifests' / f'{task}.json', target / 'manifests' / f'{task}.json')
    for name in ('plan.json', 'validation.json'):
        shutil.copy2(run / name, target / name)
    write(target / 'oracle-setup-retries.json', retry_audit)
    shutil.copy2(PARENT_RESULT / 'checkpoints.json', target / 'checkpoints.json')
    for policy, checkpoint in read(target / 'checkpoints.json').items():
        assert digest(run / checkpoint['evidence']) == checkpoint['evidence_sha256'], policy
    write(target / 'provenance.json', dict(source_run=str(run), taskset=str(base.relative_to(ROOT)),
        previous_package=str(PARENT_RESULT.relative_to(ROOT)), new_episodes=960, reused_episodes=1800,
        unchanged_five_task_rows_and_record_hashes=True, unchanged_checkpoint_metadata=True,
        new_attribute_initial_observations_equal_to_parent=True,
        attribute_success_checker=current_success_checker('attribute_select'),
        arm_select_config='demo_clean_arm_select_v3', arm_select_seeds=[500000,500039],
        formal_validation_sha256=digest(run / 'validation.json'),
        oracle_setup_failed_attempts=retry_audit['failed_setup_attempts'],
        oracle_setup_retry_audit_sha256=digest(target / 'oracle-setup-retries.json'),
        parent_results_sha256=digest(PARENT_RESULT / 'results.json'),
        previous_five_task_records='Byte-identical copies; origin reflects reuse in this run.'))
    successes = sum(r['success'] for r in rows)
    (target / 'README.md').write_text(f'''# RoboTwin-IF Attribute-v2：六任务、六 policies、20 blocks

已完成并校验 **2760/2760 回合、720/720 blocks**。共 {successes} 次成功、{2760-successes} 次 policy failure。
Attribute-Select 使用 `target-only-lift-v2` 全新运行 960 回合；其他五任务逐字节复用上一版 cube-v3 的 1800 回合。
各 policy 的 checkpoint、推理参数和所有 seeds 保持原版。Arm 使用 5 cm cube-v3，Bottle 保留 v6 terminal 判据。
共有 {retry_audit['failed_setup_attempts']} 次推理前 oracle 初始化失败，均在新 simulator 中用原 seed 恢复；
已完成的 policy 成功/失败回合没有重跑，详见[初始化重试记录](oracle-setup-retries.json)。

- [HTML 结果表](results.html) · [Markdown](results.md) · [分模式 CSV](results.csv) · [逐回合 CSV](episodes.csv)
- [来源](provenance.json) · [正式校验](validation.json) · [Checkpoint](checkpoints.json) · [运行计划](plan.json)
- [新 taskset](../../seed-manifests/{base.name}/README.md) · [新判据与回放](../../docs/attribute-select-target-only.md)
- [Attribute 新旧逐回合结果与错误抬升记录](attribute-comparison.csv)

新 Attribute 判据要求目标当前抬升严格超过 5 cm，且干扰物本回合从未越过该阈值，先抓错再抓对仍失败。
全部 960 个新回合的初始观测与上一版逐数组核对。动作预算仍为 400。
Overall 对六个 Task Avg. 等权平均；每项 Task Avg. 对 modes 等权。Spatial 仅含 left/right/on_top。
Attribute/Overall 的变化包含成功判据变化及重新推理的影响，不能视为模型能力变化。

原始视频与动作：`{run}/<policy>/<task>/`。
视频复核：`python tools/policy-video-review/server.py --run-dir {run}`。
在本目录执行 `sha256sum -c SHA256SUMS` 可核对发布文件。
''')
    (target / 'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.relative_to(target)}\n'
        for p in sorted(target.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'))
    print(json.dumps(dict(result=str(target), summary=data['summary'], policies=data['policies']), indent=2))


def update_docs(target, run):
    """Publish the completed package's numbers; never publish partial scores."""
    data = read(target / 'results.json')
    assert read(run / 'status.json')['status'] == 'complete'
    assert data['summary']['completed_episodes'] == data['summary']['expected_episodes'] == 2760
    assert read(target / 'provenance.json')['new_episodes'] == 960
    for line in (target / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split(maxsplit=1)
        assert digest(target / name.lstrip('*')) == expected
    rows = {(r['policy'], r['task']): r for r in data['rows']}
    labels = dict(zip(POLICIES, ['X-VLA', 'LingBot-VA', 'LingBot-VLA', 'VLAct All', 'DM05', 'Hy-VLA']))
    relative = str(target.relative_to(ROOT))
    finished = datetime.fromisoformat(data['updated_at']).strftime('%Y-%m-%d %H:%M UTC')
    retry_count = read(target / 'oracle-setup-retries.json')['failed_setup_attempts']
    root_path = ROOT / 'README.md'
    text = root_path.read_text()
    # The paths below are the currently published cube-v3 package, not archived files.
    text = text.replace('result/robotwin-if-cube-v3-20blocks/', relative + '/')
    text = text.replace('seed-manifests/robotwin-if-cube-v3-20-per-mode/',
                        'seed-manifests/robotwin-if-attribute-v2-20-per-mode/')
    start = text.index('当前 [RoboTwin-IF ')
    end = text.index('历史七任务 [IF-Ext', start)
    text = text[:start] + f"""当前 [RoboTwin-IF Attribute-v2 taskset](seed-manifests/robotwin-if-attribute-v2-20-per-mode/README.md)
已完成六个 policies × 六任务 × 每任务 20 blocks：460 回合/policy，共 2760 回合、720 blocks。
本轮按修正后的 `target-only-lift-v2` 重跑 Attribute-Select 960 回合，其余五任务逐字节复用上一版 cube-v3 的 1800 回合。
Arm 保留 5 cm cube-v3，Bottle 保留 v6 terminal 判据，Spatial 仅含 left/right/on_top。
详见[成功判据](docs/attribute-select-target-only.md)和[完整结果]({relative}/README.md)。
""" + text[end:]
    start = text.index('\n', text.index('## 六个 Policies 的评测结果')) + 1
    end = text.index('VLAct 使用 ', start)
    text = text[:start] + f"""
{finished} 完成并校验：**六任务 × 每任务 20 blocks × 六个 policies**，共 **2760/2760 回合、720/720 blocks**。
Attribute-Select 按新判据重新运行 **960 回合**；其余五任务的 **1800 回合**、记录哈希和统计与[上一版 cube-v3 结果](result/robotwin-if-cube-v3-20blocks/README.md)一致。
六份 seed manifest、checkpoint 和推理参数沿用上一版；新回合初始观测已逐数组核对。
共有 {retry_count} 次推理前 oracle 初始化失败，均用原 seed 恢复；已完成的 policy 结果没有重跑。
""" + text[end:]
    start = text.index('| Policy | Verb |')
    end = text.index('\n\n', start)
    table = ['| Policy | Verb | Noun | Attribute v2 | Arm cube-v3 | Sequence | Spatial | Overall (%) | 完成回合 | 完成 blocks |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for policy, label in labels.items():
        counts = [f"{rows[policy,t]['recorded_successes']}/{rows[policy,t]['recorded_episodes']}" for t in data['tasks']]
        table.append(f"| [{label}](policies/{policy}/README.md) | " + ' | '.join(counts) +
                     f" | {data['policies'][policy]['overall_pct']:.1f} | 460/460 | 120/120 |")
    text = text[:start] + '\n'.join(table) + text[end:]
    start = text.index('**Attribute-Select 判定修正')
    end = text.index('\n\n', start)
    text = text[:start] + """**Attribute-Select 判定修正（2026-09-17）：** 新规则要求目标当前抬升超过 5 cm，且干扰物在整回合中从未越过该阈值。
先抓错再抓对仍失败。上表 Attribute/Overall 已使用新判据重新评测；旧结果包保持原始计数。
新旧差异包含判据变化及重新推理的影响。见[修正与回放证据](docs/attribute-select-target-only.md)。""" + text[end:]
    start = text.index('| Policy | Color | Decal | Shape | Size |')
    end = text.index('\n\n', start)
    table = ['| Policy | Color | Decal | Shape | Size | Avg. (%) |', '|---|---:|---:|---:|---:|---:|']
    for policy, label in labels.items():
        row = rows[policy, 'attribute_select']
        counts = [f"{c['successes']}/{c['included']}" for c in row['columns']]
        table.append(f"| {label} | " + ' | '.join(counts) + f" | {row['avg_pct']:.1f} |")
    text = text[:start] + '\n'.join(table) + text[end:]
    text = text.replace('### Attribute — `attribute_select`', '### Attribute v2 — `attribute_select`')
    text = text.replace('outputs/policy-eval/robotwin-if-cube-v3-20blocks-001', 'outputs/policy-eval/' + run.name)
    text = text.replace('当前 cube-v3 的六个 policies、20-block 正式成绩', '当前 Attribute-v2 的六个 policies、20-block 正式成绩')
    old = '当前 cube-v3 taskset 的六个 policies × 20 blocks 结果已完成并校验，共 2760 回合、720 个完整 blocks；Arm-Select 重新运行 240 回合，其他五任务复用 2520 回合。'
    new = '当前 Attribute-v2 taskset 的六个 policies × 20 blocks 结果已完成并校验，共 2760 回合、720 个完整 blocks；Attribute 重新运行 960 回合，其他五任务复用 cube-v3 的 1800 回合。'
    text = text.replace(old, new)
    root_path.write_text(text)

    path = ROOT / 'result/README.md'
    text = path.read_text()
    start = text.index('最新结果保存在 ')
    end = text.index('| 版本 |', start)
    text = text[:start] + f"""最新结果保存在 [`{target.name}/`]({target.name}/README.md)：
Attribute-Select 按 `target-only-lift-v2` 重跑六个 policies 的 960 回合，其余五任务复用 cube-v3 的 1800 回合。
[HTML 报表]({target.name}/results.html) · [分模式 CSV]({target.name}/results.csv) ·
[逐回合 CSV]({target.name}/episodes.csv) · [结果 JSON]({target.name}/results.json) ·
[校验证据]({target.name}/validation.json) · [Attribute 新旧逐回合比较]({target.name}/attribute-comparison.csv)。

**2026-09-17 判据修正：** 新结果禁止“先抓错再抓对”的假成功。新 Attribute/Overall 已重新评测；
其余旧包中的 Attribute 使用历史判据，原始字节与计数保持不变。
见[新规则与回放证据](../docs/attribute-select-target-only.md)和[三个案例的回放核对包](attribute-select-target-only-v2-review/README.md)。

""" + text[end:]
    text = text.replace('| 当前：RoboTwin-IF cube-v3，', '| 上一版：RoboTwin-IF cube-v3，')
    text = text.replace('| 上一版：六任务，Spatial 三模式，Bottle v6', '| 历史：六任务，Spatial 三模式，Bottle v6')
    row = f'| 当前：RoboTwin-IF Attribute-v2，保留 Arm cube-v3 / Bottle v6 / Spatial 三模式 | 6 policies × 6 tasks × 20 blocks | 2760/2760 | [结果说明]({target.name}/README.md) · [HTML]({target.name}/results.html) · [Markdown]({target.name}/results.md) |\n'
    if row not in text:
        text = text.replace('|---|---|---:|---|\n', '|---|---|---:|---|\n' + row, 1)
    note = f'当前 Attribute-v2 于 **{finished}** 完成校验，**960 新回合 + 1800 复用回合，720/720 blocks**。\n'
    note += f'五个复用任务的原始记录哈希、逐回合字段与统计完全一致；新 Attribute 初始观测与 cube-v3 一致，checkpoint 和推理参数保持原版。\n'
    note += f'{retry_count} 次推理前 oracle 初始化失败均使用原 seed 恢复；[重试审计]({target.name}/oracle-setup-retries.json)随包保留。\n\n'
    text = text.replace('当前 cube-v3 结果于 ', note + '上一版 cube-v3 结果于 ', 1)
    text = text.replace('上一版结果于 **2026-09-15', '历史 Bottle-v6 结果于 **2026-09-15')
    path.write_text(text)

    path = ROOT / 'docs/attribute-select-target-only.md'
    text = path.read_text()
    old = '要得到修正后的完整成绩，需要重新评测 Attribute-Select；本次修复不改写历史汇总分数。'
    new = f'修正后的[完整成绩](../{relative}/README.md)已完成：六个 policies 重跑 Attribute 的 960 回合，其他五任务复用 cube-v3 的 1800 回合，共 2760 回合、720 blocks。历史汇总分数不改写。'
    text = text.replace(old, new)
    path.write_text(text)
    print(f'Published README tables from {target}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build', 'verify', 'package', 'docs'))
    parser.add_argument('--release', type=Path, default=RELEASE)
    parser.add_argument('--old-run', type=Path, default=OLD_RUN)
    parser.add_argument('--run-dir', type=Path, default=RUN)
    parser.add_argument('--result', type=Path, default=RESULT)
    args = parser.parse_args()
    if args.command == 'build':
        build(args.release.resolve(), args.old_run.resolve())
    elif args.command == 'verify':
        verify(args.release.resolve())
    elif args.command == 'package':
        package(args.release.resolve(), args.run_dir.resolve(), args.result.resolve())
    else:
        update_docs(args.result.resolve(), args.run_dir.resolve())
