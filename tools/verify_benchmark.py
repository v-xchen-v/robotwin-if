#!/usr/bin/env python3
"""Verify the delivered seeds, scores and checksums without simulation or Git history."""
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_contracts import CURRENT_SUITE_TASKS
from if_benchmark.seed_modes import build_seed_modes, check_seed_modes


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checksums(directory):
    listed = set()
    for line in (directory / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split(maxsplit=1)
        path = directory / name
        require(path.resolve().is_relative_to(directory.resolve()), f'Unsafe checksum path: {name}')
        require(name not in listed, f'Duplicate checksum path: {name}')
        listed.add(name)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, f'Checksum mismatch: {path}')
    actual = {str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() and p.name != 'SHA256SUMS'}
    require(listed == actual, f'Incomplete checksum inventory: {directory}')


def verify(root=ROOT):
    manifests = root / 'seed-manifests/20-blocks'
    result = root / 'result'
    check_seed_modes(manifests)
    seeds = build_seed_modes(manifests)
    require([t['task'] for t in seeds['tasks']] == list(CURRENT_SUITE_TASKS), 'Task inventory differs')
    require(seeds['episodes_per_policy'] == 460, 'Expected 460 episodes per policy')
    checksums(manifests)
    checksums(result)
    data = json.loads((result / 'results.json').read_text())
    require(data['tasks'] == list(CURRENT_SUITE_TASKS), 'Result task inventory differs')
    require(data['attribute_size'] == dict(big_edge_m=.06, small_edge_m=.04), 'Unexpected Size setting')
    policies = ('xvla', 'lingbot_va', 'lingbot_vla', 'vlact', 'dm05', 'hy_vla')
    require(set(data['policies']) == set(policies), 'Expected six policies')
    with (result / 'episodes.csv').open(newline='') as stream:
        episodes = list(csv.DictReader(stream))
    keys = [(r['policy'], r['task'], int(r['seed'])) for r in episodes]
    require(len(keys) == len(set(keys)) == 2760, 'Duplicate or missing episodes')
    require(all(r['status'] in ('success', 'failure') and r['success'] == str(int(r['status'] == 'success'))
                for r in episodes), 'Invalid episode labels')
    require(len(data['rows']) == 36, 'Expected 36 task-policy scores')
    for policy in policies:
        scores = []
        for task in seeds['tasks']:
            name = task['task']
            selected = [r for r in episodes if r['policy'] == policy and r['task'] == name]
            require([(int(r['seed']), r['mode'], int(r['block_index'])) for r in selected] ==
                    [(r['seed'], r['mode'], r['block']) for r in task['episodes']], f'{policy}/{name}: seed order or mode differs')
            row = next(r for r in data['rows'] if r['policy'] == policy and r['task'] == name)
            successes = sum(int(r['success']) for r in selected)
            require(row['complete'] and row['completed_blocks'] == row['expected_blocks'] == 20,
                    f'{policy}/{name}: incomplete task')
            require(row['recorded_successes'] == successes and row['included_episodes'] == len(selected),
                    f'{policy}/{name}: counts differ')
            require(row['included_seeds'] == [int(r['seed']) for r in selected], f'{policy}/{name}: scoring seeds differ')
            for mode in task['mode_counts']:
                group = [r for r in selected if r['mode'] == mode]
                k = sum(int(r['success']) for r in group)
                require(len(group) == 20 and row['modes'][mode]['successes'] == k and
                        row['modes'][mode]['included'] == 20 and row['modes'][mode]['sr_pct'] == 100*k/20,
                        f'{policy}/{name}/{mode}: counts differ')
            score = statistics.mean(v['sr_pct'] for v in row['modes'].values())
            require(abs(row['avg_pct'] - score) < 1e-10, f'{policy}/{name}: average differs')
            scores.append(score)
        require(abs(data['policies'][policy]['overall_pct'] - statistics.mean(scores)) < 1e-10,
                f'{policy}: Overall differs')
    require(data['summary'] == dict(completed_episodes=2760, expected_episodes=2760,
            completed_blocks=720, expected_blocks=720, complete_task_policy_runs=36), 'Summary differs')
    checkpoints = json.loads((result / 'checkpoints.json').read_text())
    require(set(checkpoints) == set(policies), 'Checkpoint inventory differs')
    for policy, checkpoint in checkpoints.items():
        evidence = result / checkpoint['evidence']
        require(hashlib.sha256(evidence.read_bytes()).hexdigest() == checkpoint['evidence_sha256'],
                f'{policy}: checkpoint evidence differs')
    return dict(tasks=6, policies=6, episodes=2760, blocks=720)


if __name__ == '__main__':
    print('OK:', json.dumps(verify()))
