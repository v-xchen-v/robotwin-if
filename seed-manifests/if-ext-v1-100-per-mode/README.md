# RoboTwin-IF Balanced Seed Manifests

本目录包含 RoboTwin-IF 七个 maintained tasks 的固定、均衡、经 oracle 验证的 evaluation seed manifests。每个 task 的每种 mode 均有 **100 个 exact episode seeds**，总计 **27 个 modes / 2700 个 policy-evaluation episodes**。

生成于 2026-09-03，生成进程正常退出（exit code 0），随后通过了带 generation evidence 的目录级独立验证。

> 本目录是版本化 release `if-ext-v1-100-per-mode`。加入 Git 后应视为只读资产；任何 seed contract、task config、qualification 逻辑或 manifest 内容变化都应发布新目录，而不是原地覆盖。本目录当前尚未提交。

## 文件结构

每个 task 对应两个文件：

- `<task>.json`：给 policy evaluator 使用的 flat manifest，只包含 schema、task、task config 和 exact seeds；
- `<task>.generation.json`：生成与审计 sidecar，包含逐 seed 的 expected/observed mode、setup/plan/check 结果、accepted/rejected blocks、运行时间、manifest SHA-256 和 source/target/config provenance。

原始运行日志 `generation.log` 和退出标记 `.exit_code` 保留在 staging 目录 `outputs/if-seeds-100-per-mode/`，不属于对外 release。

## 覆盖范围

| Task | Modes | Block size | Accepted blocks | Rejected blocks | Candidate acceptance | Seeds | Oracle time |
|---|---|---:|---:|---:|---:|---:|---:|
| `bottle_verb` | pick, shake | 2 | 100 | 58 | 63.3% | 200 | 1h 14m 55s |
| `pick_diverse_object` | seen, unseen | 2 | 100 | 50 | 66.7% | 200 | 14m 37s |
| `attribute_select` | color:red/blue, decal:cat/dog, shape:block/bar, size:big/small | 8 | 100 | 17 | 85.5% | 800 | 3h 33m 48s |
| `arm_select` | left, right | 2 | 100 | 0 | 100.0% | 200 | 11m 3s |
| `stack_sequence` | six RGB bottom-to-top permutations | 6 | 100 | 38 | 72.5% | 600 | 1h 36m 30s |
| `place_relative` | left, right, front, back, on_top | 5 | 100 | 36 | 73.5% | 500 | 41m 27s |
| `grasp_cube_approach` | top, side | 2 | 100 | 0 | 100.0% | 200 | 9m 41s |
| **Total** | **27 modes** | — | **700** | **199** | **77.9% of candidate blocks** | **2700** | **7h 42m 1s** |

Rejected counts are **whole rejected blocks**, not failed policy episodes. If any seed in a candidate block failed setup, oracle planning, success checking, or mode matching, the entire block was rejected. No failed seed was incremented, replaced, or silently omitted.

## Per-mode denominators

The independent validator confirmed the following exact denominators:

- `bottle_verb`: pick=100, shake=100;
- `pick_diverse_object`: seen=100, unseen=100;
- `attribute_select`: color:red=100, color:blue=100, decal:cat=100, decal:dog=100, shape:block=100, shape:bar=100, size:big=100, size:small=100;
- `arm_select`: left=100, right=100;
- `stack_sequence`: red>green>blue=100, red>blue>green=100, green>red>blue=100, green>blue>red=100, blue>red>green=100, blue>green>red=100;
- `place_relative`: left=100, right=100, front=100, back=100, on_top=100;
- `grasp_cube_approach`: top=100, side=100.

Modes are intentionally not duplicated in the flat manifest. They are deterministically derived from the task seed contract in `if_benchmark/seed_contracts.py`; the sidecar records and verifies both `expected_mode` and `observed_mode` for every probed seed.

## Generation parameters

Equivalent invocation:

```bash
CUDA_VISIBLE_DEVICES=0 \
ROBOTWIN_DIR=third_party/robotwin-manifest-clean \
IF_ALLOW_COMPATIBLE_COMMIT=1 \
  scripts/generate_if_100_per_mode.sh \
  outputs/if-seeds-100-per-mode
```

The generation command writes to a staging directory. This release was promoted only after the full directory passed validation.

Resolved parameters:

| Parameter | Value |
|---|---|
| Task config | `demo_clean` |
| Accepted blocks per task | 100 |
| Episodes per mode | 100 |
| Candidate seed floor | 100000 |
| Maximum candidate blocks per task | 500 |
| Manifest schema version | 1 |
| Generation schema version | 1 |

The generator scanned complete balance blocks beginning at the first block aligned at or above seed 100000. It stopped each task immediately after accepting 100 complete blocks.

## Provenance

All seven manifests carry the same provenance record:

| Field | Value |
|---|---|
| robotwin-if commit | `6fd624fd03b0c49e60adb9ee4204031556712431` |
| Linked task-source digest | `719c3f43818403d33f2a79f7a44aed0068a4b5a958fac0bf9b994c23343684bb` |
| Source task files dirty | `false` |
| RoboTwin commit | `b82ffb81d291d14c24be444bb7b6f81719481e0f` |
| RoboTwin compatibility contract dirty | `false` |
| Task config path | `task_config/demo_clean.yml` |
| Task config SHA-256 | `8ee5d0d07daecf7599b8d89b44776b700c7c60da24cd6317e176e6798d8cb11e` |
| Compatible-commit override | `true` |

The compatible-commit override was required because the bridge lock names RoboTwin commit `0aeea2d669c0f8516f4d5785f0aa33ba812c14b4`, while generation used its descendant `b82ffb8`. The compatibility-contract paths were compared before generation and had no committed differences between those revisions; generation used a separate clean target with `target_contract_dirty=false`.

The `target_root` stored in the sidecars is the local generation path. Reproducing this release should rely on the commit, source digest, config hash, generator versions, and manifest hashes rather than requiring the same absolute filesystem path.

## Manifest SHA-256

These hashes are calculated over the canonical flat-manifest serialization used by `if_benchmark.seed_manifest.manifest_sha256`:

```text
bottle_verb          7b6896e1c721323799547ffa450bc8621f292eac19058095b0541d344d2799af
pick_diverse_object  318ac775a958f1fdb6ef27348ac6a06162b9eacd789c2d693b42f46bf0631cc2
attribute_select     a4922579f54951804565eeaa73de99273295985073c02014e95195621298eff2
arm_select           b47088df90b8d0dadb2d3c9bd8242d621202352291984adb32aa24c9ff491697
stack_sequence       c5dc20abdbbf3c9d89665c15affb5d5857c7e35b0aed92ccfc91d5c3324e644a
place_relative       9dd739804aa2980d92ee6f3ac4663590b5918de48f9e74d2e7b6fb7fe09725d4
grasp_cube_approach  16d605d823fed6fc7c3d58b5e4b1b8c4a8b618b3f1fb596c883601d245115e6d
```

## Validation

Run from the robotwin-if repository root:

```bash
python tools/validate_if_seed_manifest.py \
  --require-evidence \
  seed-manifests/if-ext-v1-100-per-mode
```

A successful validation must report all seven files as `OK`, each with `blocks=100`, the expected seed count, all mode denominators equal to 100, and `evidence=verified`.

## Evaluator consumption

The flat manifest contains exact episode seeds:

```json
{
  "schema_version": 1,
  "task": "arm_select",
  "task_config": "demo_clean",
  "seeds": [100000, 100001]
}
```

The real files contain all 100 accepted blocks. An evaluator must preserve list order and pass each value directly to the one-episode setup path:

```python
for episode_seed in manifest["seeds"]:
    task.setup_demo(seed=episode_seed, is_test=True, ...)
```

For a fair policy comparison, every policy must evaluate the exact same manifest and produce one result for every listed seed.

Do not:

- pass these values to a CLI layer that interprets them as run/shard seeds;
- sort, deduplicate, drop, increment, or replace seeds;
- retry a failed policy episode using another seed;
- silently reduce a mode denominator;
- mix manifests generated under different source/config provenance.

A policy failure, timeout, or action-limit failure remains a failure for that exact seed. Infrastructure failures should mark the evaluation incomplete rather than trigger seed substitution.

## Collect-data candidate-pool consumption

These manifests may also be used as an ordered, oracle-qualified **candidate seed pool** for data collection. This is different from formal evaluation: collect-data does not need to reproduce the complete manifest, and it may continue to the next manifest seed after a replay or collection failure until it has collected the requested number of successful episodes.

A typical collection policy is:

```python
collected_seeds = []

for seed in manifest["seeds"]:
    if collect_one_oracle_episode(seed):
        collected_seeds.append(seed)
    if len(collected_seeds) == target_episodes:
        break
```

The collector must write `collected_seeds` to the resulting dataset's own `seed.txt` (or equivalent metadata). That list records what was actually collected and is not required to equal the source manifest. Using this prequalified pool avoids re-scanning many candidates that previously produced `UnStableError`, `plan_success=False`, or `check_success=False`; replay can still fail because of simulator nondeterminism, environment differences, or changed source/config provenance.

If mode balance matters, collection should stop on complete blocks rather than an arbitrary episode count. Prefer a `target_blocks` interface: consume seeds block-by-block, retain a block only when all of its members are collected, and stop after the requested number of complete blocks. Fifty complete blocks produce 50 episodes per mode and the following task totals:

| Task | Block size | 50 complete blocks |
|---|---:|---:|
| `bottle_verb` | 2 | 100 episodes |
| `pick_diverse_object` | 2 | 100 episodes |
| `attribute_select` | 8 | 400 episodes |
| `arm_select` | 2 | 100 episodes |
| `stack_sequence` | 6 | 300 episodes |
| `place_relative` | 5 | 250 episodes |
| `grasp_cube_approach` | 2 | 100 episodes |

For an unbalanced or task-local collection that only needs 50 successful episodes in total, the collector may instead scan in manifest order and stop at 50. An exact 50-seed prefix is block-aligned for block sizes 2 and 5, but not for `attribute_select` (block size 8) or `stack_sequence` (block size 6); use 48 or 56 for the former and 48 or 54 for the latter if a nearby block-aligned total is preferred.

The current RoboTwin `use_seed: true` path is not by itself a manifest replay adapter. It reads a local `seed.txt`, skips the planning phase, and expects previously saved pre-motion trajectory files. The manifest generator qualifies seeds but does not write those trajectory files. A manifest-aware collector must therefore load and validate the JSON, execute the oracle for each candidate seed, save the trajectory, and then write the collected dataset.

These manifests and RoboTwin `data/<task>/<config>/seed.txt` files have different roles:

- the release manifest is a fixed, balanced, auditable evaluation set and may serve as a prequalified collection candidate pool;
- a dataset `seed.txt` records the episodes actually collected;
- a dataset seed list must not be substituted for the formal evaluation manifest.

RoboTwin-IF/IF-Ext is evaluation test-only. Oracle trajectories or videos collected from these exact seeds may be used for evaluator debugging, visualization, and success-signal verification, but must not be included in policy training or fine-tuning data.
