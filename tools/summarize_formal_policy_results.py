#!/usr/bin/env python3
"""Snapshot the formal IF run into balanced, fine-grained result tables."""
import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import statistics
from datetime import datetime, timezone
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_contracts import contract_for_seeds, describe_seed, CURRENT_SUITE_TASKS  # noqa: E402

POLICIES = dict(xvla='X-VLA', lingbot_va='LingBot-VA', lingbot_vla='LingBot-VLA',
                vlact='VLAct', dm05='DM05', hy_vla='Hy-VLA')
TASKS = {
    'press_lift_stapler': ('Verb Stapler', [('Press', ['press']), ('Lift', ['lift'])]),
    'pick_diverse_object': ('Noun', [('Seen', ['seen']), ('Unseen', ['unseen'])]),
    'attribute_select': ('Attribute', [
        ('Color', ['color:red', 'color:blue']), ('Decal', ['decal:cat', 'decal:dog']),
        ('Shape', ['shape:block', 'shape:bar']), ('Size', ['size:big', 'size:small'])]),
    'arm_select': ('Arm', [('Left', ['left']), ('Right', ['right'])]),
    'stack_sequence': ('Sequence', [
        ('RGB', ['red>green>blue']), ('RBG', ['red>blue>green']),
        ('GRB', ['green>red>blue']), ('GBR', ['green>blue>red']),
        ('BRG', ['blue>red>green']), ('BGR', ['blue>green>red'])]),
    'place_relative': ('Spatial', [(x.title(), [x]) for x in ('left', 'right')]
                       + [('Top', ['on_top'])]),
}
TASK_COLUMNS = TASKS


def columns_for(task, modes):
    return TASK_COLUMNS[task][1]


def read(path):
    return json.loads(path.read_text())


def balanced_row(spec, source, records):
    """Exclude partial groups from scores, retaining all finished work in progress."""
    task = spec['task']
    contract = contract_for_seeds(task, spec["seeds"])
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
    for label, keys in columns_for(task, contract.modes):
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


def snapshot(base, manifest_dir=ROOT / 'seed-manifests/20-blocks', blocks=20):
    """Read exact-seed evaluator outputs; partial blocks never enter scores."""
    from if_benchmark.seed_modes import build_seed_modes, check_seed_modes
    if not 1 <= blocks <= 20:
        raise ValueError('blocks must be 1..20')
    check_seed_modes(manifest_dir)
    manifests = build_seed_modes(manifest_dir)
    if [t['task'] for t in manifests['tasks']] != list(CURRENT_SUITE_TASKS):
        raise ValueError('Expected the six maintained tasks')
    policies = [p for p in POLICIES if (base / p).is_dir()]
    if not policies:
        raise ValueError('No policy directories found')
    rows = []
    for policy in policies:
        for task in manifests['tasks']:
            name = task['task']
            spec = dict(task=name, seeds=[r['seed'] for r in task['episodes'] if r['block'] < blocks])
            directory = base / policy / name
            records = {}
            index = directory / 'results.jsonl'
            if index.exists():
                pending = [json.loads(line) for line in index.read_text().splitlines()]
            else:
                # Frozen downloads keep individual records without a JSONL index.
                pending = [read(p) for p in directory.glob(f'{name}_ep*_result.json')]
                pending.sort(key=lambda r: r['seed'])
            for r in pending:
                seed = r['seed']
                if seed not in spec['seeds'] or seed in records:
                    raise ValueError(f'{policy}/{name}: duplicate or unplanned seed {seed}')
                if (r['task'] != name or r['mode'] != describe_seed(name, seed).mode or
                    r['status'] not in ('success', 'failure') or not r['oracle_success'] or
                    r['success'] != (r['status'] == 'success')):
                    raise ValueError(f'{policy}/{name}/{seed}: invalid episode')
                path = directory / f'{name}_ep{seed}_result.json'
                payload = path.read_bytes()
                if json.loads(payload) != r:
                    raise ValueError(f'{path}: differs from results.jsonl')
                marker_path = directory / f'{name}_ep{seed}_provenance.json'
                if marker_path.exists():
                    marker = read(marker_path)
                    if hashlib.sha256(payload).hexdigest() != marker['files_sha256'][path.name]:
                        raise ValueError(f'{path}: provenance hash mismatch')
                records[seed] = r
            if list(records) != [seed for seed in spec['seeds'] if seed in records]:
                raise ValueError(f'{policy}/{name}: record order differs from manifest')
            size = len(task['mode_counts'])
            counts = dict(policy=policy, recorded_episodes=len(records),
                successes=sum(r['success'] for r in records.values()),
                complete=len(records) == len(spec['seeds']),
                completed_blocks=sum(all(s in records for s in spec['seeds'][i:i+size])
                                     for i in range(0, len(spec['seeds']), size)),
                per_mode={m: dict(recorded=sum(r['mode'] == m for r in records.values()),
                    successes=sum(r['success'] for r in records.values() if r['mode'] == m))
                    for m in task['mode_counts']})
            rows.append(balanced_row(spec, counts, records))
    totals = {}
    for policy in policies:
        selected = [r for r in rows if r['policy'] == policy]
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
    return dict(updated_at=datetime.now(timezone.utc).isoformat(), run_dir=str(base),
                manifest_dir=str(manifest_dir), blocks_per_task=blocks,
                tasks=list(CURRENT_SUITE_TASKS), summary=summary, rows=rows, policies=totals)


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
    labels = {task: TASK_COLUMNS[task][0] for task in data['tasks']}
    policies = {p: POLICIES[p] for p in data['policies']}
    panels_spec = [('Xa — Selection / Grounding', data['tasks'][:4]),
                   ('Xb — Structured Execution', data['tasks'][4:])]
    overview = (f"快照：{data['updated_at']}；完成 {source['completed_episodes']}/{source['expected_episodes']} 回合，"
                f"完整 blocks {source['completed_blocks']}/{source['expected_blocks']}，"
                f"跑齐任务组合 {source['complete_task_policy_runs']}/{len(policies) * task_count}。")
    legend = [
        f'本报告采用 {task_count} 项任务，使用固定 seeds 的完整 blocks。',
        '模式单元格为 SR (%)（成功数/纳入统计回合数）；0.0 表示已评测但没有成功，— 表示尚无完整 block 可统计。',
        '每项进度为已完成/计划 blocks、全部有效已完成回合/计划 ep。成功与 policy failure 均计入已完成；缺失/运行错误不计入。',
        'SR 和 Avg. 仅使用已完成的完整、均衡 blocks。半个 block 中已完成的回合仍计入进度，标为待成组，成组后才进入评分。',
        'Avg. 为该任务各 mode 等权平均；Attribute 子轴各平均两个 target values，再对四个子轴等权平均。',
        '† 表示该任务未跑齐计划 blocks，当前 Avg. 为暂定；各 policy 暂定分数可能基于不同 seed 子集，不作最终排名。',
        f'Overall 仅在该 policy 的 {task_count} 项任务全部跑齐后填写，按 {task_count} 个 Task Avg. 等权平均；不同任务范围的 Overall 不直接比较。',
        'Sequence 缩写为从下往上的颜色顺序；Spatial Top 指 on_top。',
    ]
    if reuse := data.get('result_reuse'):
        legend.insert(0, reuse['note'])
    md = ['# robotwin-if 评测结果', '', overview, '', *[f'- {x}' for x in legend], '',
          f'两 panel 合并表头版：[{output.with_suffix(".html").name}]({output.with_suffix(".html").name})。下方按任务拆开，便于 Markdown 阅读。', '',
          '| Policy | 已完成回合 | 跑齐任务 | 完整 blocks | Overall |',
          '|---|---:|---:|---:|---:|']
    for policy, label in policies.items():
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
            label = labels[task]
            cols = columns_for(task, rows[next(iter(policies)), task]["modes"])
            first += f'<th colspan="{len(cols)+2}">{html.escape(label)}</th>'
            second += ''.join(f'<th>{html.escape(name)}</th>' for name, _ in cols)
            second += '<th>Avg.</th><th>完成进度</th>'
        if tasks == panels_spec[1][1]:
            first += '<th rowspan="2">Overall</th>'
        table = '<table><thead>'+first+'</tr>'+second+'</tr></thead><tbody>'
        for policy, label in policies.items():
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
            label = labels[task]
            cols = columns_for(task, rows[next(iter(policies)), task]["modes"])
            md += ['', f'### {label} — `{task}`', '',
                   '| Policy | '+' | '.join(name for name, _ in cols)+' | Avg. | 完成进度 |',
                   '|---|'+'---:|'*(len(cols)+1)+'---|']
            for policy, name in policies.items():
                row = rows[policy, task]
                md.append('| '+name+' | '+' | '.join(cell(c) for c in row['columns'])+
                          ' | '+average(row)+' | '+progress(row)+' |')
    md += ['', '## 原始计数与核对', '',
           f'[分模式 CSV]({output.with_suffix(".csv").name}) · [完整快照 JSON]({output.with_suffix(".json").name})', '',
           '配套 JSON 保留评分纳入的 seeds、完整 block 序号和全部 mode 计数；CSV 同时列出评分纳入数与实际已完成数。',
           '汇总时核对逐回合 JSON、manifest seed 和 mode；若存在 results.jsonl 或 provenance，还验证索引与记录 SHA-256。', '',
           '刷新命令：', '', '```bash',
           'python tools/summarize_formal_policy_results.py --run-dir '+str(data['run_dir'])+
           ' --blocks '+str(data.get('blocks_per_task', 20))+' --output outputs/report/results.md', '```', '']
    output.write_text('\n'.join(md))
    page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>robotwin-if 评测结果</title><style>'
            'body{font:15px/1.65 system-ui,sans-serif;margin:24px;color:#182230;background:#fff}'
            '.scroll{overflow-x:auto;margin:16px 0 32px}table{border-collapse:collapse;font-variant-numeric:tabular-nums}'
            'th,td{border:1px solid #d5dce5;padding:9px 12px;white-space:nowrap;text-align:right}'
            'thead th{background:#eef3f8;text-align:center}tbody th{text-align:left;background:#fafbfd}'
            '.progress{font-size:12px;color:#4d596b}li{margin:5px 0}h1{font-size:24px}h2{font-size:20px}'
            '</style><h1>robotwin-if 评测结果</h1><p>'+html.escape(overview)+'</p><ul>'+
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
    parser.add_argument('--output', type=Path, default=Path('outputs/report/results.md'))
    parser.add_argument('--manifest-dir', type=Path, default=ROOT / 'seed-manifests/20-blocks')
    parser.add_argument('--blocks', type=int, default=20, help='Planned blocks per task (1..20)')
    args = parser.parse_args()
    data = snapshot(args.run_dir.resolve(), args.manifest_dir.resolve(), args.blocks)
    generate(data, args.output.resolve())
    print(json.dumps(dict(updated_at=data['updated_at'], output=str(args.output),
                          policies=data['policies']), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
