#!/usr/bin/env python3
"""Build the spatial3 manifest/result projection from the frozen five-mode release (CPU only)."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from if_benchmark.seed_contracts import IF_SEED_CONTRACTS, describe_seed
from if_benchmark.seed_manifest import manifest_sha256, validate_manifest, write_manifest
from if_benchmark.seed_modes import export_texts
from tools.summarize_formal_policy_results import snapshot, generate

PARENT_RELEASE = ROOT / 'seed-manifests/if-ext-v2-six-tasks-20-per-mode'
PARENT_RESULT = ROOT / 'result/if-ext-v2-six-tasks-20blocks'
RELEASE = ROOT / 'seed-manifests/if-ext-v2-six-tasks-spatial3-20-per-mode'
RESULT = ROOT / 'result/if-ext-v2-six-tasks-spatial3-20blocks'
EVIDENCE = ROOT / 'bak/place_relative-five-modes'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def retained(row):
    return not (row['task'] == 'place_relative' and row['mode'] in ('front', 'back'))


def write_csv(path, rows, fields):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def finish_package():
    (RELEASE / "README.md").write_text("""# IF-Ext v2：六任务、Spatial 三模式、20 blocks

当前正式清单：6 tasks × 20 blocks；每个 policy **460 回合**，6 policies 合计 **2760 回合、720 blocks**。
`place_relative` 仅含 left/right/on_top，每个 mode 20 回合；其余五项任务与上一版完全一致。

Spatial 使用 schema 2，保留原 seed：每组 `[5k, 5k+1, 5k+4]`，场景仍为 `seed // 5`。
没有重新编号、更换场景或筛选成功回合。原五模式清单及 oracle 资格证据由
`qualification-files.json` 绑定；全部 2760 回合已完成，可以按 `reusable-results.yml` 复用。
旧五模式 flat manifest 保持 schema 1，用于历史校验，当前运行入口拒绝 front/back。

- [显式 seed/mode JSON](seed-modes.json) · [CSV](seed-modes.csv)
- [套件及计数](suite.yml) · [复用清单](reusable-results.yml)
- [决策与证据](../../docs/place-relative-spatial3.md)
- [结果](../../result/if-ext-v2-six-tasks-spatial3-20blocks/README.md)

CPU 校验：`python seed-manifests/if-ext-v2-six-tasks-spatial3-20-per-mode/verify.py`。
运行：`bash scripts/eval.sh --policy <policy> --output-dir <new-output>`，先启动相应模型 server。
入口默认本目录；每个任务串行跑满 20 blocks，不自动重跑失败。
""")
    (RESULT / "README.md").write_text("""# IF-Ext v2：六任务、Spatial 三模式、20 blocks

视频复核后，Spatial 仅计 left/right/on_top，保留原 20 个场景。
每个 policy **460/460 回合、120/120 blocks**；全套 **2760/2760 回合、720/720 blocks**。
共有 **1259 次成功、1501 次已完成的 policy failure**。

- [HTML 结果表](results.html) · [Markdown](results.md)
- [逐回合 CSV](episodes.csv) · [分模式 CSV](results.csv)
- [完整统计快照](results.json) · [来源与投影说明](provenance.json)
- [Checkpoint 版本](checkpoints.json) · [当前 manifest](../../seed-manifests/if-ext-v2-six-tasks-spatial3-20-per-mode/README.md)
- [决策、240 个排除回合与证据](../../docs/place-relative-spatial3.md)

不重跑、不改判、不替换 seed。front/back 统一排除 240 回合，其中 2 个原自动成功；
其余回合与源结果逐行相同，原记录 SHA/provenance 已核对。
Spatial Avg. 对三个模式等权；Overall 对六个 Task Avg. 等权，不是 460 个回合直接合并。
这是评测后的范围调整，新旧指标不可直接视作性能提升。

原 [六任务五模式包](../if-ext-v2-six-tasks-20blocks/README.md) 和
[七任务包](../if-ext-v2-wide-20blocks/README.md) 未改写。
X-VLA 为 clean-only checkpoint，其余五个为 clean+random；无公开 X-VLA clean+random checkpoint。
Hy-VLA pick_diverse_object seed 100052 的 coffee-box 自动成功仍待人工复核，本次未修改。

视频和动作保存在原运行目录：
`/Data/robotwin-if/evaluations/if-seven-tasks-v2-wide-20blocks-001/<policy>/<task>/`。
复核页打开“包含已下线的任务 / 模式”仍可查看 front/back。

本目录内执行 `sha256sum -c SHA256SUMS` 可校验。
""")
    (RESULT / "SHA256SUMS").write_text("".join(f"{sha(p)}  {p.relative_to(RESULT)}\n" for p in sorted(RESULT.rglob("*")) if p.is_file() and p.name != "SHA256SUMS"))


def build(run):
    # Never mutate historical packages. Verify the frozen source before projection.
    for line in (PARENT_RESULT / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split(maxsplit=1)
        assert sha(PARENT_RESULT / name.lstrip('*')) == expected, name
    data = snapshot(run)
    historical = snapshot(run, include_archived_modes=True)
    old = read(PARENT_RESULT / 'results.json')
    assert historical['rows'] == old['rows'] and historical['policies'] == old['policies']
    assert data['summary']['completed_episodes'] == data['summary']['expected_episodes'] == 2760
    assert data['summary']['completed_blocks'] == data['summary']['expected_blocks'] == 720
    assert not RELEASE.exists() and not RESULT.exists(), 'Destination exists; do not overwrite a release'
    RELEASE.mkdir(); RESULT.mkdir(); (RESULT / 'manifests').mkdir()
    suite = yaml.safe_load((PARENT_RELEASE / 'suite.yml').read_text())
    suite.update(release=RELEASE.name, created_at=datetime.now(timezone.utc).isoformat(),
        parent_release=PARENT_RELEASE.name, supersedes=PARENT_RELEASE.name,
        episodes_per_policy=460, episodes_all_six_policies=2760, reusable_episodes=2760,
        retired_modes={'place_relative': ['front', 'back']},
        reuse_condition='Keep all left/right/on_top outcomes for the same 20 scenes; no outcome relabeling.',
        qualification_note='Subset of previously qualified five-mode blocks; original seeds and scene mapping preserved.')
    proofs = {str(p.relative_to(ROOT)): sha(p) for p in PARENT_RELEASE.iterdir() if p.is_file()}
    for spec in suite['tasks']:
        manifest = read(PARENT_RELEASE / spec['manifest'])
        if spec['task'] == 'place_relative':
            manifest['schema_version'] = 2
            manifest['seeds'] = [s for s in manifest['seeds'] if describe_seed('place_relative', s).mode in IF_SEED_CONTRACTS['place_relative'].modes]
            spec['qualification'] = dict(type='subset_of_qualified_blocks',
                parent_manifest=str((PARENT_RELEASE / spec['manifest']).relative_to(ROOT)),
                seed_mapping='scene=seed//5; offsets=0,1,4; no new oracle execution')
        write_manifest(RELEASE / spec['manifest'], manifest)
        checked = validate_manifest(manifest)
        spec.update(manifest_sha256=manifest_sha256(manifest), modes=checked['mode_denominators'],
                    episodes_per_policy=len(manifest['seeds']), reusable_seeds_per_policy=manifest['seeds'])
        shutil.copy2(RELEASE / spec['manifest'], RESULT / 'manifests' / spec['manifest'])
    reuse = yaml.safe_load((PARENT_RELEASE / 'reusable-results.yml').read_text())
    reuse['episodes'] = [r for r in reuse['episodes'] if retained(r)]
    reuse.update(count=len(reuse['episodes']), successes=sum(r['success'] for r in reuse['episodes']))
    assert (reuse['count'], reuse['successes']) == (2760, 1259)
    (RELEASE / 'suite.yml').write_text(yaml.safe_dump(suite, sort_keys=False))
    (RELEASE / 'reusable-results.yml').write_text(yaml.safe_dump(reuse, sort_keys=False))
    write(RELEASE / 'qualification-files.json', proofs)
    for name, contents in export_texts(RELEASE).items():
        (RELEASE / name).write_text(contents)
    shutil.copy2(ROOT / 'tools/verify_spatial3_release.py', RELEASE / 'verify.py')
    with (PARENT_RESULT / 'episodes.csv').open(newline='') as f:
        reader = csv.DictReader(f); fields = reader.fieldnames; episodes = list(reader)
    kept = [r for r in episodes if retained(r)]
    removed = [r for r in episodes if not retained(r)]
    assert len(removed) == 240 and sum(int(r['success']) for r in removed) == 2
    # Assert identical raw records; the current package is solely a scope projection.
    for row in episodes:
        assert sha(run / row['record_path']) == row['record_sha256']
    write_csv(RESULT / 'episodes.csv', kept, fields)
    write_csv(EVIDENCE / 'excluded-episodes.csv', removed, fields)
    reuse_by_key = {(r['policy'], r['task'], r['seed']): r for r in yaml.safe_load((PARENT_RELEASE / 'reusable-results.yml').read_text())['episodes']}
    evidence = []
    (EVIDENCE / 'records').mkdir(exist_ok=True)
    for row in removed:
        seed = int(row['seed']); success = int(row['success']); policy = row['policy']
        source = reuse_by_key[policy, row['task'], seed]
        name = f'place_relative_ep{seed}_{success}.mp4'
        item = dict(policy=policy, seed=seed, mode=row['mode'], automatic=row['status'],
            instruction=row['instruction'], video=str(run / policy / 'place_relative' / name),
            video_sha256=source['files_sha256'][name], record_path=row['record_path'],
            record_sha256=row['record_sha256'], review_query=f'?episode={policy}/place_relative/{seed}')
        # Keep first paired front/back scene for every policy and every automatic success.
        if seed in (100007, 100008) or success:
            assert sha(Path(item['video'])) == item['video_sha256']
            target = EVIDENCE / 'records' / f'{policy}-place_relative-{seed}.json'
            shutil.copy2(run / row['record_path'], target)
            item['example_record'] = str(target.relative_to(ROOT))
        evidence.append(item)
    write(EVIDENCE / 'evidence.json', dict(source_result=str(PARENT_RESULT.relative_to(ROOT)),
        source_episode_csv_sha256=sha(PARENT_RESULT/'episodes.csv'), excluded_episodes=240,
        automatic_successes=2, automatic_failures=238,
        manual_review_basis='User video-review observation in conversation; no persisted place_relative annotations at decision time.',
        episodes=evidence))
    generate(data, RESULT / 'results.md')
    shutil.copy2(PARENT_RESULT / 'checkpoints.json', RESULT / 'checkpoints.json')
    write(RESULT / 'provenance.json', dict(scope='six tasks, Spatial left/right/on_top, 20 blocks',
        source_package=str(PARENT_RESULT.relative_to(ROOT)), source_run=str(run),
        source_episodes_csv_sha256=sha(PARENT_RESULT/'episodes.csv'),
        source_report_json_sha256=sha(PARENT_RESULT/'results.json'),
        excluded_modes={'place_relative': ['front', 'back']}, excluded_episodes=240,
        excluded_successes=2, included_rows_unchanged=True, new_evaluation=False,
        historical_five_mode_scores_verified=True,
        evidence='../../bak/place_relative-five-modes/evidence.json',
        note='Post-hoc scope change, not a model improvement or correction of automatic labels.'))
    finish_package()
    print(json.dumps(dict(summary=data['summary'], policies=data['policies']), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    build(args.run_dir.resolve())
