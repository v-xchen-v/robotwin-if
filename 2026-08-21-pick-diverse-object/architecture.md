# Pick-Diverse-Object：实现架构

> 更新于 2026-09-03。本文只描述当前 object-familiarity production path 与保留的通用 probe；旧 color+noun 实现和已淘汰的一次性候选实验仅作为历史结论。

## 模块边界

| 模块 | 职责 |
|---|---|
| `tasks/envs/_pick_diverse_object_pool.py` | simulator-free taxonomy、production/candidate manifests、Apple top-contact builder、seed schedule |
| `tasks/envs/pick_diverse_object.py` | 真实 scene setup、sampling、placement、instruction info、oracle |
| `tasks/envs/_if_grounding.py` | target-specific lift-and-held success helper |
| `tasks/task_instruction/pick_diverse_object.json` | noun-only templates；顶层 keys 仅表示 template split |
| `tools/probe_pick_diverse_unseen.py` | retained exact-candidate trials 与真实 production-seed trials，增量写 JSON/CSV |
| `tools/_pick_diverse_probe_logic.py` | simulator-free fail-closed qualification 与 video-path helpers |
| `tools/render_pick_pool_snapshots.py` | 真实贴图 exact-variant contact sheets |
| `tools/report_pick_diverse_object.py` | 从 production pools/schedule 重建 familiarity 并聚合指标 |
| `tests/pick_diverse_object/` | static contract、instruction、real wiring、Apple grasp、success semantics、reporter |

共享 pool module 不 import SAPIEN，因此 static tests 和 reporter 可直接复用生产定义，不复制 pool 表。

## Pool entry schema

每个 noun 对应一个现役 entry：

```python
{
    "asset": str,
    "model_ids": tuple[int, ...],
    "rest_qpos": tuple[float, float, float, float],
    "rotate_rand": bool,
    "rotate_lim": tuple[float, float, float],
    "grasp_strategy": str,
    "grasp_kwargs": dict,
    "placement_radius": float,
}
```

当前 schema 不含 generic actor config、scale override 或 per-arm kwargs。paintbrush 通过 generic `grasp_kwargs={"contact_point_id": 0, ...}` 选择已有 contact pose。

Production Apple 使用 `grasp_strategy="apple_top_down"`。`_apple_top_down_actor_config()` deep-copy actor 已加载的 native config，只将 contact poses 替换为四个已验证的 top-down wrist-roll rotations，并把 translation 设为 native metadata `center`。它不 import simulator，也不修改 source JSON。

## Final production manifests

- Seen：12 nouns / 12 exact variants。
- Unseen（固定顺序）：
  1. dumbbell — `052_dumbbell/base0`
  2. apple — `035_apple/base1`
  3. wooden mallet — `084_woodenmallet/base3`
  4. paintbrush — `093_brush-pen/base1`

原 14 nouns / 54 exact variants 的 `UNSEEN_CANDIDATES` 与 notebook/paintbrush manual inventory 继续作为 reusable shortlist；它们不是 production admission 的自动来源。

## Production setup flow

```text
raw seed
  ├─ familiarity_for_seed(seed) -> even Seen / odd Unseen
  ├─ select production pool; Unseen pool < 4 nouns 时 fail closed
  ├─ target_for_seed(seed, pool)
  │    ├─ group_index = seed // 2
  │    ├─ noun cycles in manifest order
  │    └─ exact ID cycles after a full noun cycle
  ├─ sample 3 distinct distractor nouns from the same pool
  ├─ place four actors by decreasing footprint radius
  ├─ production Apple only: deep-copy native config and inject top contacts
  ├─ settle and record target_origin_z
  └─ log target + scene familiarity/noun/asset/model IDs
```

### Placement

Production 的排序 key 为负 `placement_radius` 加 seed-driven tie breaker。任意 pair 必须满足：

```python
xy_distance > radius_a + radius_b + 0.025
```

Forced exact-candidate probe 固定 target-first；production 固定 radius-first。环境不再暴露任意 placement-policy override。

## Retained overrides

以下 class hooks 仅供 exact candidate probe/semantic isolation，定义时全部为 `None`：

```python
FAMILIARITY_OVERRIDE
TARGET_NOUN_OVERRIDE
TARGET_MODEL_ID_OVERRIDE
TARGET_SIDE_OVERRIDE
POOL_OVERRIDE
DISTRACTOR_NOUNS_OVERRIDE
```

真实 production-seed probe 首先清空全部 hooks。wiring test 不为 setup failure 换 seed，因为替换 raw seed 会掩盖 parity、schedule、placement 或 determinism regression。

## Instruction flow

环境只提供：

```python
self.info["info"] = {
    "{A}": f"the {self.target_noun}",
    "{a}": str(arm_tag),
}
```

四个 scene nouns 强制不同，故 `{A}` 单靠 noun 唯一定位目标。JSON 顶层 `seen`/`unseen` 只选择 sentence template，不控制 object familiarity。

## Oracle 与 success

1. target x 位置决定 left/right arm，probe 可显式覆盖。
2. 从 target entry 复制 `grasp_kwargs`。
3. 按 `grasp_strategy` 执行既有 bottle/cup/shoe/mug/phone 特例、default grasp 或 Apple top-down grasp。
4. Apple 仍复用 `Base_Task.grasp_actor()` / `choose_grasp_pose()`，planner 在四个 vertical wrist rolls 中选择可达者。
5. close 后、lift 前记录 end-effector approach-axis world-z 分量，仅作诊断。
6. 所有目标统一 world-frame `z=0.12` lift。
7. `check_success()` 只检查 named target。

`named_object_lifted_and_held(task, actor, modelname, origin_z)` 的语义是：

```text
(actor.z - settled_origin_z > 0.02)
AND actor remains in gripper contact
```

抬起 distractor、只撞起 target 或 target 未被保持都不能成功。

## Probe architecture

### Candidate mode

`--nouns`、`--model-id`、`--variants`、`--first-id-per-noun` 选择 retained shortlist/manual exact variants；`--arms` 和 `--repeats` 控制覆盖。每个 trial 强制一个 Unseen candidate target，加三个不同 noun 的 retained candidate distractors。

记录 setup、settle、actual arm、workspace/motion、oracle、target z-rise、instruction target、placement sequence 与 failure stage。每个 trial 后立即写 JSON/CSV；相对 output/video path 按 invocation cwd 解析。generic settle failure 在 `play_once()` 前 fail closed，保留原 seed denominator。

可选 `--video-dir` 只用于 grasp phase。已有 MP4 默认拒绝覆盖；`--overwrite` 必须显式给出。

### Production mode

`--production-seeds` 只接受 odd seeds，且不能与 candidate selectors 混用。它清空 overrides 后使用真实 locked pool 和 target schedule，用于验证 coexistence、routing 与 oracle，不提供失败 seed replacement。

### 已删除的实验接口

Closeout 删除了 098 speaker、旧 Apple pose-family/radius-first、perfume、toothpaste、whiteboard eraser 与 tissue-box 的 one-off manifests、stability metadata、policy registries及 raw/debug artifacts。这些实验的 aggregate outcomes 留在 decisions/selection notes，但不再承诺用当前 runtime 逐项复现。

## Reporter flow

Reporter import 同一 manifests/schedule，根据 raw seed 重建 expected familiarity 与 target，并输出：

```text
Seen micro + noun macro
Unseen micro + noun macro
balanced average
absolute gap
retention
per-noun and per-exact-variant tables
tried/kept composition
```

若 production Unseen pool 少于四类则拒绝运行。标题和解释固定使用 all-Seen/all-Unseen scene；不得生成 target-only causal 文案。

## Verification layers

1. `test_pool.py`：taxonomy、14/54 shortlist、manual inventory、final exact manifests、seed cycles、override defaults、Apple top-contact geometry/config isolation。
2. `test_probe_logic.py`：generic fail-closed qualification 与 video naming/overwrite。
3. `test_instructions.py`：template split、placeholder routing、noun-only grammar。
4. `test_wiring.py`：real-SAPIEN seeds 0–7 production wiring、determinism、Apple target/distractor config isolation、source JSON immutability。
5. `test_apple_top_grasp.py`：12 个冻结双臂场景；失败不换 seed，成功 grasp 必须满足 vertical approach diagnostic。
6. `test_check_success.py`：negative semantics + Seen 12 / current Unseen 4 oracle positives。
7. `test_reporter.py`：aggregation 与 exact-target mapping。
8. normal `collect_data.sh`：20-success native pipeline、HDF5、MP4、instruction 与 scene-info integrity。

实际 closeout test counts 以 `report.html` verification matrix 和最终运行记录为准。normal collection 为 20/23 raw seeds，Apple target episodes 2/9 的 ordered review 均通过；它是 scripted-oracle pipeline evidence，不是 VLA evaluation。
