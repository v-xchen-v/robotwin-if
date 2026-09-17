#!/usr/bin/env python3
"""Build/verify the cube-v3 taskset and package its completed six-policy run."""
import argparse
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
    matches_success_checker, validate_episode,
)
from tools.summarize_formal_policy_results import generate, snapshot

PARENT = ROOT / 'seed-manifests/if-ext-v2-six-tasks-spatial3-20-per-mode'
PARENT_RESULT = ROOT / 'result/if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks'
CUBE = ROOT / 'seed-manifests/arm-select-cube-v3-20-per-mode'
RELEASE = ROOT / 'seed-manifests/robotwin-if-cube-v3-20-per-mode'
OLD_RUN = Path('/Data/robotwin-if/evaluations/if-six-tasks-spatial3-bottle-v6-terminal-20blocks-001')
RUN = Path('/Data/robotwin-if/evaluations/robotwin-if-cube-v3-20blocks-001')
RESULT = ROOT / 'result/robotwin-if-cube-v3-20blocks'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def prior_rows():
    with (PARENT_RESULT / 'episodes.csv').open(newline='') as stream:
        return {(r['policy'], r['task'], int(r['seed'])): r for r in csv.DictReader(stream)}


def verify(base=RELEASE):
    suite = yaml.safe_load((base / 'suite.yml').read_text())
    assert suite['policies'] == POLICIES
    assert [s['task'] for s in suite['tasks']] == list(IF_SEED_CONTRACTS)
    assert suite['blocks_per_task'] == 20
    check_seed_modes(base)
    for filename, expected in read(base / 'qualification-files.json').items():
        assert digest(ROOT / filename) == expected, filename
    qualified = read(CUBE / 'qualification.json')
    assert qualified['complete'] and qualified['all_checks_passed']
    assert qualified['unique_candidate_scenes'] == 20
    assert read(CUBE / 'supervisor.json')['exit_code'] == 0
    specs = {s['task']: s for s in suite['tasks']}
    expected_keys = set()
    for task, spec in specs.items():
        source = CUBE if task == 'arm_select' else PARENT
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
    reuse = yaml.safe_load((base / suite['reuse_index']).read_text())
    rows = reuse['episodes']
    keys = [(r['policy'], r['task'], r['seed']) for r in rows]
    assert len(keys) == len(set(keys)) == len(expected_keys) == 2520
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
        if index % 420 == 0:
            print(f'Verified source artifacts for {index}/2520 reused episodes', flush=True)
    assert Counter(r['policy'] for r in rows) == {p: 420 for p in POLICIES}
    assert reuse['count'] == suite['reusable_episodes'] == 2520
    assert reuse['successes'] == sum(r['success'] for r in rows)
    assert suite['pending_episodes'] == 240
    assert suite['episodes_per_policy'] == 460 and suite['episodes_all_six_policies'] == 2760
    print('OK: 6 tasks x 20 blocks; 2520 unchanged reusable episodes; 240 cube-v3 episodes pending', flush=True)


def build(base, old):
    assert not base.exists(), 'Refuse to overwrite a taskset'
    for line in (PARENT_RESULT / 'SHA256SUMS').read_text().splitlines():
        expected, filename = line.split(maxsplit=1)
        assert digest(PARENT_RESULT / filename.lstrip('*')) == expected, filename
    assert read(old / 'status.json')['status'] == 'complete'
    assert read(old / 'validation.json')['complete']
    previous = read(old / 'plan.json')
    suite = deepcopy(yaml.safe_load((PARENT / 'suite.yml').read_text()))
    suite.update(release=base.name, created_at=datetime.now(timezone.utc).isoformat(),
                 previous_formal_run=str(old), parent_release=PARENT.name, supersedes=PARENT.name,
                 reusable_episodes=2520, pending_episodes=240,
                 reuse_condition='Reuse every outcome of the five unchanged tasks from the completed Bottle v6 run.',
                 qualification_note='Arm-Select uses independently qualified cube-v3 seeds 500000..500039.')
    base.mkdir(parents=True)
    for spec in suite['tasks']:
        task = spec['task']
        source = CUBE if task == 'arm_select' else PARENT
        shutil.copy2(source / spec['manifest'], base / spec['manifest'])
        manifest = load_manifest(base / spec['manifest'])
        spec.update(task_config=manifest['task_config'], manifest_sha256=manifest_sha256(manifest),
                    reusable_seeds_per_policy=[] if task == 'arm_select' else manifest['seeds'],
                    pending_seeds_per_policy=manifest['seeds'] if task == 'arm_select' else [])
        if task == 'arm_select':
            spec['qualification'] = dict(type='cube_v3_paired_oracle', candidate_blocks=20, failed_blocks=0,
                regions=read(CUBE / 'verification.json')['scene_regions'],
                evidence=str(CUBE.relative_to(ROOT) / 'qualification.json'))
        if task == 'bottle_verb':
            prior = next(s for s in previous['tasks'] if s['task'] == task)
            for key in ('success_checker_version', 'success_checker_parameters'):
                spec[key] = prior[key]
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
               *[p for p in CUBE.iterdir() if p.suffix == '.json']]
    write(base / 'qualification-files.json', {str(p.relative_to(ROOT)): digest(p) for p in sources})
    prior_hashes = read(old / 'support/source-hashes.json')
    differences = [name for name, sha in prior_hashes.items() if not (ROOT / name).exists() or digest(ROOT / name) != sha]
    assert set(differences) <= {'policies/xvla/eval.py', 'tasks/envs/arm_select.py',
                               'third_party/robotwin/envs/arm_select.py', 'tools/run_formal_policy_suite.py'}, differences
    write(base / 'reuse-audit.json', dict(previous_run=str(old), reused_episodes=2520,
        new_arm_select_episodes=240, source_differences=differences,
        unchanged_five_task_sources=True, unchanged_five_task_manifests=True,
        shared_evaluator_change='instruction_for adds cube-v3 to paired arm_select template selection only',
        checkpoint_metadata='Retain prior run metadata and services-before-recovery.json through formal prepare.'))
    for name, content in export_texts(base).items():
        (base / name).write_text(content)
    (base / 'verify.py').write_text('''from pathlib import Path
import sys
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'if_benchmark').is_dir())
sys.path.insert(0, str(ROOT))
from tools.release_arm_select_cube_v3 import verify
verify(Path(__file__).resolve().parent)
''')
    (base / 'README.md').write_text('''# RoboTwin-IF cube-v3 taskset：六任务 × 20 blocks

每个 policy 460 回合；六个 policies 合计 2760 回合、720 blocks。
Arm-Select 使用 5 cm cube 与 `demo_clean_arm_select_v3`，seeds 500000–500039，左右臂各 20 回合。
其余五任务与上一版清单逐字节一致；Bottle-Verb 保留 v6 回合末判定，Spatial 保留 left/right/on_top。

本轮复用最新 Bottle v6 结果包中的五任务共 2520 回合，只重跑 Arm-Select 的 240 回合。
复用包含所有成功和 policy failure，逐回合来源及所有 artifact SHA-256 见 `reusable-results.yml`。
Cube 的 20 个场景已通过 54/54 oracle/对照回合检查；配对图像、位姿与句式一致。

- [套件与任务配置](suite.yml) · [seed/mode JSON](seed-modes.json) · [CSV](seed-modes.csv)
- [复用审计](reuse-audit.json) · [绑定的资格证据](qualification-files.json)
- [Cube 环境与验证](../../docs/recon/arm-select-cube-v3.md)

校验：`python seed-manifests/robotwin-if-cube-v3-20-per-mode/verify.py`。
运行：`bash scripts/eval.sh --policy <policy> --manifest-dir seed-manifests/robotwin-if-cube-v3-20-per-mode --output-dir <new-output>`。
复用并重跑的正式入口见 `tools/run_formal_policy_suite.py prepare/run`，须指定本目录与最新 Bottle v6 的 `--old-run`。
''')
    verify(base)


def oracle_setup_audit(run):
    """Export pre-inference failures and their exact-seed recovery evidence."""
    decisions, attempts, affected = [], {}, set()
    for path in sorted((run / 'batches').glob('*/*/arm_select-oracle-retry.json')):
        decision = read(path)
        policy, seed = path.parent.name, decision['seed']
        assert policy in POLICIES and 500000 <= seed <= 500039
        assert decision['policy_results_retried'] is False
        assert decision['max_attempts'] == MAX_ORACLE_ATTEMPTS
        assert decision['prior_failed_attempts'] == len(decision['failed_records'])
        assert 0 < decision['prior_failed_attempts'] < MAX_ORACLE_ATTEMPTS
        final = run / policy / 'arm_select' / f'arm_select_ep{seed}_result.json'
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
            assert failed.parent.name == 'arm_select' and failed.parent.parent.name == policy
            attempts[relative] = dict(path=relative, sha256=digest(failed), record=record)
    observed = {str(p.relative_to(run)) for p in (run / 'batches').glob('*/*/arm_select/*_result.json')
                if is_oracle_setup_failure(read(p))}
    assert set(attempts) == observed, 'Every oracle setup failure must have a retry decision'
    return dict(schema_version=1, failed_setup_attempts=len(attempts),
        affected_episodes=[dict(policy=p, seed=s) for p, s in sorted(affected)],
        policy_results_retried=False, seeds_substituted=False,
        scope='Only oracle negatives before any model inference; exact seed recovered in a fresh simulator.',
        decisions=decisions, failed_attempts=[attempts[p] for p in sorted(attempts)])


def package(base, run, target):
    validation = read(run / 'validation.json')
    status = read(run / 'status.json')
    assert status['status'] == 'complete' and validation['complete']
    assert validation['validated_episodes'] == 2760
    assert validation['counts'] == {'reused': 2520, 'new': 240}
    data = snapshot(run)
    old_data = read(PARENT_RESULT / 'results.json')
    assert [r for r in data['rows'] if r['task'] != 'arm_select'] == [r for r in old_data['rows'] if r['task'] != 'arm_select']
    assert data['summary']['completed_blocks'] == 720
    assert data['task_configs']['arm_select'] == 'demo_clean_arm_select_v3'
    retry_audit = oracle_setup_audit(run)
    assert not target.exists(), 'Refuse to overwrite a result package'
    target.mkdir(parents=True)
    (target / 'manifests').mkdir()
    plan = read(run / 'plan.json')
    old = prior_rows()
    rows = []
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
                assert row['origin'] == ('new' if task == 'arm_select' else 'reused')
                if task != 'arm_select':
                    assert all(str(row[k]) == old[policy, task, seed][k] for k in fields if k != 'origin')
                else:
                    assert record['step_limit'] == 400
                rows.append(row)
    with (target / 'episodes.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
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
        previous_package=str(PARENT_RESULT.relative_to(ROOT)), new_episodes=240, reused_episodes=2520,
        unchanged_five_task_rows_and_record_hashes=True, unchanged_checkpoint_metadata=True,
        arm_select_config='demo_clean_arm_select_v3', arm_select_seeds=[500000,500039],
        formal_validation_sha256=digest(run / 'validation.json'),
        oracle_setup_failed_attempts=retry_audit['failed_setup_attempts'],
        oracle_setup_retry_audit_sha256=digest(target / 'oracle-setup-retries.json'),
        parent_results_sha256=digest(PARENT_RESULT / 'results.json'),
        previous_five_task_records='Byte-identical copies; origin reflects reuse in this run.'))
    successes = sum(r['success'] for r in rows)
    (target / 'README.md').write_text(f'''# RoboTwin-IF cube-v3：六任务、六 policies、20 blocks

已完成并校验 **2760/2760 回合、720/720 blocks**。共 {successes} 次成功、{2760-successes} 次 policy failure。
Arm-Select 的 240 回合使用 5 cm cube 重新评测；其他五任务的 2520 回合逐字节复用最新 Bottle v6 结果。
各 policy 的 checkpoint 与推理参数沿用上一轮。
共有 {retry_audit['failed_setup_attempts']} 次推理前 oracle 初始化失败，均在新 simulator 中用原 seed 恢复；
已完成的 policy 成功/失败回合没有重跑，详见[初始化重试记录](oracle-setup-retries.json)。

- [HTML 结果表](results.html) · [Markdown](results.md) · [分模式 CSV](results.csv) · [逐回合 CSV](episodes.csv)
- [来源](provenance.json) · [正式校验](validation.json) · [Checkpoint](checkpoints.json) · [运行计划](plan.json)
- [新 taskset](../../seed-manifests/{base.name}/README.md) · [Cube 环境](../../docs/recon/arm-select-cube-v3.md)

Arm-Select 使用 `demo_clean_arm_select_v3`，20 个配对场景、左右臂各 20 回合/policy，动作预算 400。
Bottle-Verb 保留 v6 回合末判定；Spatial 仅含 left/right/on_top。
Overall 对六个 Task Avg. 等权平均；每项 Task Avg. 对 modes 等权。
此轮改变了 Arm-Select 任务环境，新旧 Arm/Overall 差异包含环境变化的影响。

原始视频与动作：`{run}/<policy>/<task>/`。
视频复核：`python tools/policy-video-review/server.py --run-dir {run}`。
在本目录执行 `sha256sum -c SHA256SUMS` 可核对发布文件。
''')
    (target / 'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.relative_to(target)}\n'
        for p in sorted(target.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'))
    print(json.dumps(dict(result=str(target), summary=data['summary'], policies=data['policies']), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build', 'verify', 'package'))
    parser.add_argument('--release', type=Path, default=RELEASE)
    parser.add_argument('--old-run', type=Path, default=OLD_RUN)
    parser.add_argument('--run-dir', type=Path, default=RUN)
    parser.add_argument('--result', type=Path, default=RESULT)
    args = parser.parse_args()
    if args.command == 'build':
        build(args.release.resolve(), args.old_run.resolve())
    elif args.command == 'verify':
        verify(args.release.resolve())
    else:
        package(args.release.resolve(), args.run_dir.resolve(), args.result.resolve())
