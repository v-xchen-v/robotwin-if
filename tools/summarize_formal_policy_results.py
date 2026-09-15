#!/usr/bin/env python3
"""Snapshot the formal IF run into balanced, fine-grained result tables."""
import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_contracts import contract_for, describe_seed  # noqa: E402

POLICIES = dict(xvla='X-VLA', lingbot_va='LingBot-VA', lingbot_vla='LingBot-VLA',
                vlact='VLAct', dm05='DM05', hy_vla='Hy-VLA')
TASKS = {
    'bottle_verb': ('Verb', [('Pick', ['pick']), ('Shake', ['shake'])]),
    'pick_diverse_object': ('Noun', [('Seen', ['seen']), ('Unseen', ['unseen'])]),
    'attribute_select': ('Attribute', [
        ('Color', ['color:red', 'color:blue']), ('Decal', ['decal:cat', 'decal:dog']),
        ('Shape', ['shape:block', 'shape:bar']), ('Size', ['size:big', 'size:small'])]),
    'arm_select': ('Arm v2', [('Left', ['left']), ('Right', ['right'])]),
    'stack_sequence': ('Sequence', [
        ('RGB', ['red>green>blue']), ('RBG', ['red>blue>green']),
        ('GRB', ['green>red>blue']), ('GBR', ['green>blue>red']),
        ('BRG', ['blue>red>green']), ('BGR', ['blue>green>red'])]),
    'place_relative': ('Spatial', [(x.title(), [x]) for x in ('left', 'right', 'front', 'back')]
                       + [('Top', ['on_top'])]),
}
ARCHIVED_TASKS = {
    'grasp_cube_approach': ('Grasp v2 wide-r1', [('Top', ['top']), ('Side', ['side'])]),
}
TASK_COLUMNS = TASKS | ARCHIVED_TASKS


def read(path):
    return json.loads(path.read_text())


def balanced_row(spec, source, records):
    """Exclude partial groups from scores, retaining all finished work in progress."""
    task = spec['task']
    contract = contract_for(task)
    size = contract.block_size
    blocks = [spec['seeds'][i:i + size] for i in range(0, len(spec['seeds']), size)]
    assert all(len(block) == size for block in blocks)
    complete = [i for i, block in enumerate(blocks) if all(seed in records for seed in block)]
    used = [seed for i in complete for seed in blocks[i]]
    assert len(complete) == source['completed_blocks']
    assert len(records) == source['recorded_episodes']
    assert sum(r['success'] for r in records.values()) == source['successes']
    assert bool(len(records) == len(spec['seeds'])) == source['complete']
    for i in complete:
        assert {records[seed]['mode'] for seed in blocks[i]} == set(contract.modes)
    modes = {}
    for mode in contract.modes:
        selected = [records[seed] for seed in used if records[seed]['mode'] == mode]
        raw = [r for r in records.values() if r['mode'] == mode]
        n, k = len(selected), sum(r['success'] for r in selected)
        assert n == len(complete)
        assert len(raw) == source['per_mode'][mode]['recorded']
        assert sum(r['success'] for r in raw) == source['per_mode'][mode]['successes']
        modes[mode] = dict(successes=k, included=n, sr_pct=100*k/n if n else None,
                           recorded=len(raw), recorded_successes=sum(r['success'] for r in raw))
    columns = []
    for label, keys in TASK_COLUMNS[task][1]:
        values = [modes[key] for key in keys]
        columns.append(dict(label=label, modes=keys, successes=sum(v['successes'] for v in values),
            included=sum(v['included'] for v in values),
            sr_pct=statistics.mean(v['sr_pct'] for v in values) if used else None))
    return dict(policy=source['policy'], task=task, complete=source['complete'],
        completed_blocks=len(complete), expected_blocks=len(blocks),
        recorded_episodes=len(records), expected_episodes=len(spec['seeds']),
        recorded_successes=sum(r['success'] for r in records.values()),
        included_episodes=len(used), partial_group_episodes=len(records)-len(used),
        included_seeds=used, complete_block_ids=complete, modes=modes, columns=columns,
        avg_pct=statistics.mean(v['sr_pct'] for v in modes.values()) if used else None)


def snapshot(base, include_archived_tasks=False):
    # summary.json is atomically replaced by the scheduler. Use only its recorded seeds.
    source = read(base/'summary.json')
    plan = read(base/'plan.json')
    assert plan['policies'] == list(POLICIES)
    planned = {r['task'] for r in plan['tasks']}
    assert set(TASKS) <= planned <= set(TASK_COLUMNS)
    task_names = [t for t in TASK_COLUMNS if t in planned and (t in TASKS or include_archived_tasks)]
    assert len(planned) == len(plan['tasks'])
    assert {(r['policy'], r['task']) for r in source['tasks']} == {(p, t) for p in POLICIES for t in planned}
    assert len(source['tasks']) == len(POLICIES) * len(planned)
    specs = {r['task']: r for r in plan['tasks']}
    rows = []
    for row in source['tasks']:
        spec = specs[row['task']]
        records = {}
        for seed in spec['seeds']:
            if seed in row['pending_seeds']:
                continue
            pre = base/row['policy']/row['task']/f"{row['task']}_ep{seed}"
            marker = read(Path(str(pre)+'_provenance.json'))
            result_path = Path(str(pre)+'_result.json')
            payload = result_path.read_bytes()
            assert hashlib.sha256(payload).hexdigest() == marker['files_sha256'][result_path.name]
            r = json.loads(payload)
            assert marker['policy'] == row['policy']
            assert marker['task'] == r['task'] == row['task']
            assert marker['seed'] == r['seed'] == seed
            assert r['status'] in ('success', 'failure') and r['oracle_success']
            assert marker['success'] == r['success'] == (r['status'] == 'success')
            assert marker['mode'] == r['mode'] == describe_seed(row['task'], seed).mode
            assert marker['formal_block'] == spec['seeds'].index(seed)//contract_for(row['task']).block_size
            records[seed] = r
        rows.append(balanced_row(spec, row, records))
    assert sum(r['recorded_episodes'] for r in rows) == source['completed_episodes']
    assert sum(r['recorded_successes'] for r in rows) == source['successes']
    assert sum(r['completed_blocks'] for r in rows) == source['completed_blocks']
    rows = [r for r in rows if r['task'] in task_names]
    totals = {}
    for policy in POLICIES:
        selected = [r for r in rows if r['policy'] == policy]
        assert len(selected) == len(task_names)
        totals[policy] = dict(recorded=sum(r['recorded_episodes'] for r in selected),
            expected=sum(r['expected_episodes'] for r in selected),
            complete_tasks=sum(r['complete'] for r in selected),
            complete_blocks=sum(r['completed_blocks'] for r in selected),
            expected_blocks=sum(r['expected_blocks'] for r in selected),
            overall_pct=statistics.mean(r['avg_pct'] for r in selected)
                if all(r['complete'] for r in selected) else None)
    summary = dict(completed_episodes=sum(r['recorded_episodes'] for r in rows),
                   expected_episodes=sum(r['expected_episodes'] for r in rows),
                   completed_blocks=sum(r['completed_blocks'] for r in rows),
                   expected_blocks=sum(r['expected_blocks'] for r in rows),
                   complete_task_policy_runs=sum(r['complete'] for r in rows))
    return dict(updated_at=source['updated_at'], run_dir=str(base),
                tasks=task_names, excluded_tasks=sorted(planned - set(task_names)), summary=summary,
                checkpoint_replacement=plan.get('checkpoint_replacement'),
                block_extension=plan.get('block_extension'),
                source_summary=source, rows=rows, policies=totals)


def cell(value):
    if value['sr_pct'] is None:
        return '—'
    return f"{value['sr_pct']:.1f} ({value['successes']}/{value['included']})"


def average(row):
    if row['avg_pct'] is None:
        return '—'
    return f"{row['avg_pct']:.1f}" + ('†' if not row['complete'] else '')


def progress(row):
    return (f"{row['completed_blocks']}/{row['expected_blocks']} B; "
            f"{row['recorded_episodes']}/{row['expected_episodes']} ep" +
            (f"; {row['partial_group_episodes']} 待成组" if row['partial_group_episodes'] else ''))


def generate(data, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = {(r['policy'], r['task']): r for r in data['rows']}
    source = data['summary']
    task_count = len(data['tasks'])
    panels_spec = [('Xa — Selection / Grounding', data['tasks'][:4]),
                   ('Xb — Structured Execution', data['tasks'][4:])]
    overview = (f"快照：{data['updated_at']}；完成 {source['completed_episodes']}/{source['expected_episodes']} 回合，"
                f"完整 blocks {source['completed_blocks']}/{source['expected_blocks']}，"
                f"跑齐任务组合 {source['complete_task_policy_runs']}/{len(POLICIES) * task_count}。")
    legend = [
        f'本报告采用 {task_count} 项任务；arm select 使用 v2。已下线任务只有显式选择历史范围时才纳入。',
        '模式单元格为 SR (%)（成功数/纳入统计回合数）；0.0 表示已评测但没有成功，— 表示尚无完整 block 可统计。',
        '每项进度为已完成/计划 blocks、全部有效已完成回合/计划 ep。成功与 policy failure 均计入已完成；缺失/运行错误不计入。',
        'SR 和 Avg. 仅使用已完成的完整、均衡 blocks。半个 block 中已完成的回合仍计入进度，标为待成组，成组后才进入评分。',
        'Avg. 为该任务各 mode 等权平均；Attribute 子轴各平均两个 target values，再对四个子轴等权平均。',
        '† 表示该任务未跑齐计划 blocks，当前 Avg. 为暂定；各 policy 暂定分数可能基于不同 seed 子集，不作最终排名。',
        f'Overall 仅在该 policy 的 {task_count} 项任务全部跑齐后填写，按 {task_count} 个 Task Avg. 等权平均；不同任务范围的 Overall 不直接比较。',
        'Sequence 缩写为从下往上的颜色顺序；Spatial Top 指 on_top。',
    ]
    if data['excluded_tasks']:
        legend.insert(0, '当前范围排除已下线任务：' + ', '.join(data['excluded_tasks']) + '；原始七任务结果未改写。')
    if replacement := data.get('checkpoint_replacement'):
        checkpoint = replacement['new']
        legend.insert(0, f"{POLICIES[replacement['policy']]} 使用 {checkpoint['repo_id']} "
                      f"@ {checkpoint['revision']}；旧 Clean checkpoint 的回合不计入。")
    if extension := data.get('block_extension'):
        legend.insert(0, f"每项任务从 {extension['from_blocks']} 扩至 {extension['to_blocks']} blocks。")
    md = ['# IF-Ext 分轴结果与完成进度', '', overview, '', *[f'- {x}' for x in legend], '',
          f'两 panel 合并表头版：[{output.with_suffix(".html").name}]({output.with_suffix(".html").name})。下方按任务拆开，便于 Markdown 阅读。', '',
          '| Policy | 已完成回合 | 跑齐任务 | 完整 blocks | Overall |',
          '|---|---:|---:|---:|---:|']
    for policy, label in POLICIES.items():
        p = data['policies'][policy]
        overall = f"{p['overall_pct']:.1f}" if p['overall_pct'] is not None else '—'
        md.append(f"| {label} | {p['recorded']}/{p['expected']} | {p['complete_tasks']}/{task_count} | "
                  f"{p['complete_blocks']}/{p['expected_blocks']} | {overall} |")
    panels = []
    for title, tasks in panels_spec:
        md += ['', '## '+title]
        first = '<tr><th rowspan="2">Policy</th>'
        second = '<tr>'
        for task in tasks:
            label, cols = TASK_COLUMNS[task]
            first += f'<th colspan="{len(cols)+2}">{html.escape(label)}</th>'
            second += ''.join(f'<th>{html.escape(name)}</th>' for name, _ in cols)
            second += '<th>Avg.</th><th>完成进度</th>'
        if tasks == panels_spec[1][1]:
            first += '<th rowspan="2">Overall</th>'
        table = '<table><thead>'+first+'</tr>'+second+'</tr></thead><tbody>'
        for policy, label in POLICIES.items():
            table += '<tr><th>'+html.escape(label)+'</th>'
            for task in tasks:
                row = rows[policy, task]
                for c in row['columns']:
                    table += '<td>'+html.escape(cell(c))+'</td>'
                table += '<td>'+average(row)+'</td><td class="progress">'+progress(row)+'</td>'
            if tasks == panels_spec[1][1]:
                score = data['policies'][policy]['overall_pct']
                table += '<td>'+(f'{score:.1f}' if score is not None else '—')+'</td>'
            table += '</tr>'
        panels.append('<h2>'+html.escape(title)+'</h2><div class="scroll">'+table+'</tbody></table></div>')
        for task in tasks:
            label, cols = TASK_COLUMNS[task]
            md += ['', f'### {label} — `{task}`', '',
                   '| Policy | '+' | '.join(name for name, _ in cols)+' | Avg. | 完成进度 |',
                   '|---|'+'---:|'*(len(cols)+1)+'---|']
            for policy, name in POLICIES.items():
                row = rows[policy, task]
                md.append('| '+name+' | '+' | '.join(cell(c) for c in row['columns'])+
                          ' | '+average(row)+' | '+progress(row)+' |')
    md += ['', '## 原始计数与核对', '',
           f'[分模式 CSV]({output.with_suffix(".csv").name}) · [完整快照 JSON]({output.with_suffix(".json").name})', '',
           '配套 JSON 保留此次中央 summary 快照、评分纳入的 seeds、完整 block 序号和全部 mode 计数；CSV 同时列出评分纳入数与实际已完成数。',
           '生成时核对已归档结果的 SHA-256、provenance、mode 和成功数，并与快照总数交叉检查；不改动正在运行的评测。', '',
           '刷新命令：', '', '```bash',
           'python tools/summarize_formal_policy_results.py --run-dir '+str(data['run_dir'])+
           ' --output '+str(output) + (' --include-archived-tasks' if set(data['tasks']) & set(ARCHIVED_TASKS) else ''), '```', '']
    output.write_text('\n'.join(md))
    page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>IF-Ext 分轴结果与完成进度</title><style>'
            'body{font:15px/1.65 system-ui,sans-serif;margin:24px;color:#182230;background:#fff}'
            '.scroll{overflow-x:auto;margin:16px 0 32px}table{border-collapse:collapse;font-variant-numeric:tabular-nums}'
            'th,td{border:1px solid #d5dce5;padding:9px 12px;white-space:nowrap;text-align:right}'
            'thead th{background:#eef3f8;text-align:center}tbody th{text-align:left;background:#fafbfd}'
            '.progress{font-size:12px;color:#4d596b}li{margin:5px 0}h1{font-size:24px}h2{font-size:20px}'
            '</style><h1>IF-Ext 分轴结果与完成进度</h1><p>'+html.escape(overview)+'</p><ul>'+
            ''.join('<li>'+html.escape(x)+'</li>' for x in legend)+'</ul>'+''.join(panels)+'</html>')
    output.with_suffix('.html').write_text(page)
    output.with_suffix('.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    with output.with_suffix('.csv').open('w', newline='') as f:
        fields = ['policy', 'task', 'mode', 'successes', 'included', 'sr_pct', 'recorded',
                  'recorded_successes', 'completed_blocks', 'expected_blocks', 'complete']
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in data['rows']:
            for mode, counts in row['modes'].items():
                writer.writerow({**{k: row[k] for k in ('policy', 'task', 'completed_blocks',
                    'expected_blocks', 'complete')}, 'mode': mode, **counts})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path,
        default=ROOT/'notes/2026-09-01-if-ext-tasklist/results-current.md')
    parser.add_argument('--include-archived-tasks', action='store_true',
                        help='Include retired tasks when reproducing a historical seven-task report')
    args = parser.parse_args()
    data = snapshot(args.run_dir.resolve(), args.include_archived_tasks)
    generate(data, args.output.resolve())
    print(json.dumps(dict(updated_at=data['updated_at'], output=str(args.output),
                          policies=data['policies']), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
