"""Human-readable seed/mode exports derived from the evaluator's flat manifests."""
import csv
import io
import json
from pathlib import Path

from .seed_contracts import IF_SEED_CONTRACTS, describe_seed
from .seed_manifest import load_manifest, manifest_sha256, validate_manifest

CSV_FIELDS = ('task', 'task_config', 'block', 'seed', 'mode', 'block_offset', 'scene_index', 'scene_offset')


def build_seed_modes(directory):
    directory = Path(directory)
    tasks = []
    for task in IF_SEED_CONTRACTS:
        manifest = load_manifest(directory / f'{task}.json')
        checked = validate_manifest(manifest)
        if manifest['task'] != task or len(checked['block_ids']) != 20:
            raise ValueError(f'{task}: expected the complete 20-block manifest')
        size = IF_SEED_CONTRACTS[task].block_size
        episodes = []
        for index, seed in enumerate(manifest['seeds']):
            description = describe_seed(task, seed)
            episodes.append(dict(block=index // size, seed=seed, mode=description.mode,
                                 block_offset=description.block_offset,
                                 scene_index=description.scene_index, scene_offset=description.scene_offset))
        tasks.append(dict(task=task, task_config=manifest['task_config'], manifest=f'{task}.json',
                          manifest_sha256=manifest_sha256(manifest), blocks=20,
                          mode_counts=checked['mode_denominators'], episodes=episodes))
    return dict(schema_version=1, release=directory.name, instruction_type='unseen',
                block_numbering='zero-based ordinal within each task manifest; not seed // block_size',
                task_count=len(tasks), blocks_per_task=20,
                episodes_per_policy=sum(len(t['episodes']) for t in tasks), tasks=tasks)


def export_texts(directory):
    data = build_seed_modes(directory)
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator='\n')
    writer.writeheader()
    for task in data['tasks']:
        writer.writerows(dict(task=task['task'], task_config=task['task_config'], **row)
                         for row in task['episodes'])
    return {'seed-modes.json': json.dumps(data, ensure_ascii=False, indent=2) + '\n',
            'seed-modes.csv': stream.getvalue()}


def check_seed_modes(directory):
    directory = Path(directory)
    for name, expected in export_texts(directory).items():
        if (directory / name).read_text() != expected:
            raise ValueError(f'Seed/mode export differs from flat manifests: {name}')
