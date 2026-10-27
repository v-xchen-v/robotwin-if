#!/usr/bin/env python3
"""Publish the completed stapler suite and prove five-task result reuse."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import run_formal_policy_suite as formal
from tools import summarize_formal_policy_results as tables
from tools.prepare_stapler_policy_suite import RUN, PACKAGE
from tools.release_history import read_parent_result

OUTPUT = ROOT / 'result/robotwin-if-press-lift-stapler-v1-20blocks'
FIELDS = ['policy', 'task', 'block_index', 'seed', 'mode', 'status', 'success',
          'action_calls', 'step_limit', 'termination', 'instruction', 'origin',
          'record_path', 'record_sha256']


def publish(base=RUN, output=OUTPUT):
    task_name, task_label = 'press_lift_stapler', 'Press/Lift Stapler'
    asset = task_name.removeprefix('press_lift_')
    status = formal.read(base / 'status.json')
    validation = formal.read(base / 'validation.json')
    assert status['status'] == 'complete' and validation['complete']
    assert status['completed_episodes'] == validation['validated_episodes'] == 2760
    assert status['reused_episodes'] == validation['counts']['reused'] == 2520
    assert status['new_episodes'] == validation['counts']['new'] == 240
    formal.check_sources(base)
    data = tables.snapshot(base)
    parent_csv = read_parent_result('episodes.csv')
    parent_rows = {(r['policy'], r['task'], int(r['seed'])): r
                   for r in csv.DictReader(io.StringIO(parent_csv.decode(), newline=''))}
    plan = formal.read(base / 'plan.json')
    assert plan['tasks'][0]['task'] == task_name
    episodes, staplers, stapler_summary = [], [], {}
    for policy in plan['policies']:
        for spec in plan['tasks']:
            task = spec['task']
            for index, seed in enumerate(spec['seeds']):
                directory = base / policy / task
                stem = formal.prefix(task, seed)
                record_path = directory / (stem + '_result.json')
                record = formal.completed_record(base, policy, spec, seed)
                marker = formal.read(directory / (stem + '_provenance.json'))
                row = dict(policy=policy, task=task, block_index=index // (len(spec['seeds']) // 20),
                    seed=seed, mode=record['mode'], status=record['status'], success=int(record['success']),
                    action_calls=record['action_calls'], step_limit=record['step_limit'],
                    termination=record['termination'], instruction=record['instruction'],
                    origin=marker['origin'], record_path=str(record_path.relative_to(base)),
                    record_sha256=formal.digest(record_path))
                if task != task_name:
                    original = parent_rows[policy, task, seed]
                    assert all(str(row[k]) == original[k] for k in FIELDS if k != 'origin'), (policy, task, seed)
                    assert row['origin'] == 'reused'
                else:
                    assert row['origin'] == 'new' and record['step_limit'] == 250
                    staplers.append(dict(record, policy=policy))
                episodes.append(row)
        selected = [r for r in staplers if r['policy'] == policy]
        assert len(selected) == 40
        scenes = {s: [r for r in selected if r['seed'] // 2 == s] for s in sorted({r['seed'] // 2 for r in selected})}
        assert all(len(pair) == 2 and {r['mode'] for r in pair} == {'press', 'lift'} for pair in scenes.values())
        stapler_summary[policy] = dict(episodes=40,
            press_successes=sum(r['mode'] == 'press' and r['success'] for r in selected),
            lift_successes=sum(r['mode'] == 'lift' and r['success'] for r in selected),
            both_success_blocks=sum(all(r['success'] for r in pair) for pair in scenes.values()),
            blocks=20, successes=sum(r['success'] for r in selected),
            first_action_counts=dict(Counter(str(r['signals']['first_action']) for r in selected)))
    output.mkdir(parents=True, exist_ok=False)
    tables.generate(data, output / 'results.md')
    with (output / 'episodes.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(episodes)
    formal.write(output / f'{asset}-episodes.json', staplers)
    formal.write(output / f'{asset}-summary.json', stapler_summary)
    for name in ('plan.json', 'validation.json'):
        shutil.copyfile(base / name, output / name)
    execution_evidence = {}
    for name in ('execution-transition.json', 'parallel-source-hashes.json',
                 'execution-recoveries.json', 'parallel-startup-validation.json'):
        source = base / 'support' / name
        if source.exists():
            shutil.copyfile(source, output / name)
            execution_evidence[name] = formal.digest(source)
    shutil.copyfile(base / 'support/reuse-audit.json', output / 'reuse-audit.json')
    shutil.copytree(base / 'manifests', output / 'manifests')
    checkpoints = formal.read(base / 'support/checkpoint-reference.json')
    for policy in plan['policies']:
        runs = sorted((base / 'batches').glob(f'*/{policy}/{task_name}/run.json'))
        assert runs, policy
        metadata = formal.read(runs[-1])
        reference = formal.read(formal.inference_reference(base, policy, task_name) / 'run.json')
        if policy == 'xvla':
            for key in ('checkpoint', 'checkpoint_revision', 'feedback', 'gripper_threshold', 'denoising_steps'):
                assert metadata['arguments'][key] == reference['arguments'][key]
            assert metadata['arguments']['checkpoint_revision'] == checkpoints[policy]['revision']
        else:
            assert metadata['server_metadata']['checkpoint'] == reference['server_metadata']['checkpoint']
            assert metadata['server_metadata']['checkpoint']['revision'] == checkpoints[policy]['revision']
        path = output / 'checkpoint-evidence' / f'{policy}.json'
        formal.write(path, metadata)
        checkpoints[policy].update(evidence=str(path.relative_to(output)), evidence_sha256=formal.digest(path))
    formal.write(output / 'checkpoints.json', checkpoints)
    retry_records = [formal.read(p) for p in sorted((base / 'batches').glob('*/*/*-oracle-retry.json'))]
    formal.write(output / 'oracle-setup-retries.json', retry_records)
    formal.write(output / 'provenance.json', dict(source_run=str(base), taskset=plan['release'],
        parent_result=str(PACKAGE.relative_to(ROOT)), parent_episode_csv_sha256=hashlib.sha256(parent_csv).hexdigest(),
        new_episodes=240, reused_episodes=2520, replaced_task='bottle_verb', new_task=task_name,
        unchanged_five_task_rows_except_origin=True, unchanged_five_task_record_hashes=True,
        checkpoints_and_inference_options_retained=True,
        completed_policy_failures_are_final=True, oracle_setup_retry_records=len(retry_records),
        execution_topology=plan.get('execution_topology'), execution_evidence_sha256=execution_evidence,
        publication_source_sha256={name: formal.digest(ROOT / name) for name in
            ('tools/publish_stapler_policy_results.py', 'tools/summarize_formal_policy_results.py')},
        source_snapshot=str(base / 'support/source-snapshot'), source_hashes_sha256=formal.digest(base / 'support/source-hashes.json')))
    lines = [f'# {task_label} v1：六模型 × 六任务 × 20 blocks', '',
        '**2760/2760 回合、720/720 blocks 已完成并校验。**', '',
        '其余五个任务的 2520 回合全部复用 Arm-only-v2，包含成功和失败，逐回合记录哈希与已发布结果一致。',
        f'仅 {task_label} 的 240 回合是本次新跑；使用 manifest 中固定的 40 个 seeds、随机 distractors、固定指令与 250-action 预算。',
        '六个模型沿用各自原 checkpoint 和推理参数。小规模 pilot 未混入本结果。', '',
        '| 模型 | Press | Lift | 两种指令都成功 | Overall |', '|---|---:|---:|---:|---:|']
    for policy, row in stapler_summary.items():
        lines.append(f"| {tables.POLICIES[policy]} | {row['press_successes']}/20 | {row['lift_successes']}/20 | {row['both_success_blocks']}/20 | {data['policies'][policy]['overall_pct']:.1f}% |")
    lines += ['', 'Overall 是六个任务成功率的等权平均，每任务内部各 mode 等权；不是 460 回合的合并成功率。',
        '新旧 Verb 任务不同，因此 Overall 的变化不代表同一任务上的模型能力提升。',
        'X-VLA 使用公开 clean checkpoint，其余模型沿用旧报告对应的 clean + randomized checkpoints。', '',
        '旧报告中 Hy-VLA noun seed 100052 的视频复核疑问仍保留；本次按要求复用原自动标签，未重新判定该回合。', '',
        '- [六任务 HTML](results.html) · [Markdown](results.md) · [分模式 CSV](results.csv) · [逐回合 CSV](episodes.csv)',
        f'- [Verb 统计]({asset}-summary.json) · [Verb 逐回合诊断]({asset}-episodes.json)',
        '- [来源](provenance.json) · [复用审计](reuse-audit.json) · [校验](validation.json) · [checkpoints](checkpoints.json)', '',
        f'原始视频、动作及观测：`{base}/<policy>/<task>/`。',
        '原始数组、动作、逐回合哈希、新视频帧数及各模型初始观测已检查。',
        '在本目录执行 `sha256sum -c SHA256SUMS` 可校验发布文件。', '']
    (output / 'README.md').write_text('\n'.join(lines))
    (output / 'SHA256SUMS').write_text(''.join(f'{formal.digest(p)}  {p.relative_to(output)}\n'
        for p in sorted(output.rglob('*')) if p.is_file() and p != output / 'SHA256SUMS'))
    print(json.dumps(dict(output=str(output), task=task_name, task_summary=stapler_summary), indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, default=RUN)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    publish(args.run_dir.resolve(), args.output.resolve())
