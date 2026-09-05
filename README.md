# robotwin-if

在 [RoboTwin 2.0](https://github.com/RoboTwin-Platform/RoboTwin) 上维护七个单轴 instruction-following diagnostic tasks。RoboTwin 以 git submodule 锁定；任务通过软链注入，**不 fork、不修改上游源码**。

| 诊断轴 | Task name | 对比值 |
|---|---|---|
| Verb-Select | `bottle_verb` | pick / shake |
| Noun-Grounding | `pick_diverse_object` | 仅按名词从同 familiarity group 中选择目标 |
| Attribute-Select | `attribute_select` | color / decal / shape / size |
| Arm-Select | `arm_select` | left / right |
| Sequence | `stack_sequence` | 六种 bottom-to-top 顺序 |
| Spatial-Direction | `place_relative` | left / right / front / back / on top |
| Grasp-Approach | `grasp_cube_approach` | top / side |

唯一正式维护的 IF inventory 是 [`eval_cfg/if_tasks.yml`](eval_cfg/if_tasks.yml)。其他 env/JSON 可以为历史或实验目的留在仓库中，但只要没有列入该文件，就不属于 active suite。Manifest membership 与 production readiness 分开管理：例如 `pick_diverse_object` 属于上述七项，其已锁定的四类 Unseen production pool 仍由独立测试 gate 持续约束。

范围仅限 benchmark task（场景、干扰物、指令模板、成功判定与评测语义），**不在本仓库训练模型**。真实 VLA 评测在 CogACT 侧进行：把本仓库挂入 CogACT，由这里锁定的 RoboTwin runtime 运行任务，由 CogACT/X-VLA 提供推理。

## 设计原则：零改上游

任务源码维护在 `tasks/` 下；安全 installer 只把 canonical IF 七项及其四个 helper 软链到 RoboTwin：

- `envs/<task_name>.py`（七项）；
- `envs/_if_grounding.py`、`_if_relative.py`、`_pick_diverse_object_pool.py`、`_if_eval.py`；
- `description/task_instruction/<task_name>.json`（七项）。

历史/实验 env 即使仍在 `tasks/` 中也不会被安装；当前七项不依赖额外 object-description bridge。Installer 不修改 RoboTwin tracked 文件，尤其不会 merge 或替换 `task_config/_eval_step_limit.yml`。

Bridge 之后，RoboTwin 的 collect/eval harness 可像发现 raw task 一样通过 task name 加载新增任务。Bridge 只负责 runtime discovery；它不负责选择 balanced seeds 或计算 per-mode IF 指标。

## 用法

### 1. 环境搭建

```bash
bash setup_robotwin.sh [--assets_cache <本地资产缓存目录>]
```

安装 RoboTwin 2.0 仿真环境（SAPIEN/CUDA/curobo 等）。详见 [`docs/features/01-环境搭建.md`](docs/features/01-环境搭建.md)。

### 2. 桥接 / 解绑任务

#### 模式 A：锁定的 nested runtime（推荐）

```bash
# 默认 target = third_party/robotwin
bash scripts/bridge_tasks.sh --dry-run
bash scripts/bridge_tasks.sh
bash scripts/bridge_tasks.sh --check

# 卸载前先查看计划；真正卸载使用同一命令但去掉 --dry-run
bash scripts/unbridge_tasks.sh --dry-run
```

Nested checkout 固定在已验证的 RoboTwin commit `0aeea2d669c0f8516f4d5785f0aa33ba812c14b4`，适合 benchmark release、CI 和 CogACT/X-VLA 评测。Fresh clone、new worktree 或新的 CI job 都要重新 bridge；软链和 target-side `.robotwin-if-bridge.json` 是 workspace installation state，不属于 RoboTwin submodule commit。

#### 模式 B：接入外部 repo 已有的 RoboTwin

```bash
bash scripts/bridge_tasks.sh --robotwin-dir /path/to/external/RoboTwin --dry-run
bash scripts/bridge_tasks.sh --robotwin-dir /path/to/external/RoboTwin
bash scripts/bridge_tasks.sh --robotwin-dir /path/to/external/RoboTwin --check
```

Target 解析优先级为 `--robotwin-dir`、`ROBOTWIN_DIR`、默认 nested checkout。外部 checkout 的 commit 若不是上述 locked commit、没有可读且 target-root 精确匹配的 git metadata，或 compatibility contract files 有本地修改，默认拒绝；只有人工确认后才显式放行：

```bash
bash scripts/bridge_tasks.sh \
  --robotwin-dir /path/to/external/RoboTwin \
  --allow-compatible-commit

# mismatch checkout 的后续 check 也必须显式声明同一 opt-in
bash scripts/bridge_tasks.sh \
  --robotwin-dir /path/to/external/RoboTwin \
  --allow-compatible-commit --check
```

即使显式放行，Base_Task、instruction generator、`envs.utils` 的实际 package exports 与目录布局等静态 API contract 仍必须全部通过。Ownership manifest 记录实际 target/source commits、`source_dirty`、18 个 linked sources 的 deterministic `source_digest`、`target_contract_dirty` 和每个链接的精确 raw target；它不会把 dirty source 错写成可由 commit 单独复现，`--check` 也能发现 dirty source 内容再次变化。

Bridge 在写入前对所有 destination 做完整 preflight：正确旧链接会被 adopt，missing link 才新增，foreign/dangling symlink、真实文件或目录都会使整次安装在 mutation 前失败；不提供 `--force`。重跑 bridge 会安全清理 manifest-owned stale links 和仍指向本 source 的旧 inactive glob links。Unbridge 以 manifest 为准，因此 source 文件重命名/删除后仍可清理；被外部修改的 destination 一律 `skip-modified` 并保留 ownership 记录，绝不误删。Bridge/check/unbridge 通过 target-directory lock 串行化完整 transaction，dry-run 不新增 lock 文件。

### 3. 采集 oracle 专家演示

锁定版本的 RoboTwin collect 是单任务入口。遍历七项 IF manifest：

```bash
bash scripts/bridge_tasks.sh
cd third_party/robotwin

for t in $(python3 -c "import yaml; print(' '.join(yaml.safe_load(open('../../eval_cfg/if_tasks.yml'))['tasks']))"); do
  bash collect_data.sh "$t" demo_clean 0   # <task> <config> <gpu_id>
done
```

可执行清单：

- [`eval_cfg/if_tasks.yml`](eval_cfg/if_tasks.yml)：维护中的 IF 七项；
- [`eval_cfg/all_tasks_plus_if.yml`](eval_cfg/all_tasks_plus_if.yml)：锁定的 native 50 + 同一 IF 七项，共 57 项。

每个任务 collect 结束时会调用 RoboTwin 原生指令生成管线，无需单独执行 instruction generator。

### 4. Policy 评测

RoboTwin 没有统一的顶层 eval 命令；每个 policy 使用自己的 `eval.sh`，参数签名也可能不同。常见入口为：

```bash
cd third_party/robotwin/policy/<PolicyName>
bash eval.sh <task_name> demo_randomized <ckpt_setting> <expert_data_num> <seed> <gpu_id>
```

- 把 `task_name` 换成 task inventory 中任一新增任务即可完成 runtime 加载；checkpoint 必须具备相应行为 repertoire，结果才有诊断意义。
- 各 policy 的 `deploy_policy.yml` 通常以 `instruction_type: unseen` 做正式 IF 评测；`seen` 只用于 sanity check。
- 原生 eval 会跳过 oracle-invalid candidate seeds，适合 smoke test，但不能保证每个 mode denominator 均衡。

七项 task 在 eval mode 使用集中维护的 policy-action budget（collect 不受影响）：

| Task | `step_lim` | Native structural analog |
|---|---:|---|
| `bottle_verb` | 700 | `shake_bottle`（取最长 shake branch） |
| `pick_diverse_object` | 400 | single grasp/lift |
| `attribute_select` | 400 | single grasp/lift |
| `arm_select` | 400 | single grasp/lift |
| `stack_sequence` | 1200 | `stack_blocks_three` |
| `place_relative` | 400 | `place_a2b_left` |
| `grasp_cube_approach` | 400 | single grasp/lift |

Mapping 位于 `tasks/envs/_if_eval.py`，task 在 `_init_task_env_` 返回后覆盖 eval limit，因此不修改 upstream config。Locked Base_Task 对未知 task 可能先打印 fallback-to-1000 提示，但 policy rollout 实际读取的是随后覆盖的固定值。现有 oracle trajectory 最大 recorded frames（按表中 task 顺序）为 255/103/89/89/479/163/99，只能支持相对复杂度判断；`step_lim` 统计 policy action calls，仍需在后续 CogACT rollout 中监测是否有 episode 撞到 limit。

正式 IF 结果不能任意跳过单个 seed。应先按 task 的完整 balance block 验证并固化 seed manifest，再让所有 policy 重放同一批 episodes。这里的 block 不一定是同一物理场景：`attribute_select` 的 8-seed block 包含四个 same-scene pair，`pick_diverse_object` 的 seen/unseen block 则是两个独立 familiarity scenes。具体 contract 见 [`eval_cfg/README.md`](eval_cfg/README.md)。

### 5. 生成与消费 balanced seed manifest

完整的生成、验证、resume 与外部 evaluator 消费流程见 [`docs/seed-manifest-usage.md`](docs/seed-manifest-usage.md)。

`eval_cfg/if_tasks.yml` 回答“运行哪些 task”；seed manifest 回答“每个 task 运行哪些 exact episode seeds”。面向外部 evaluator 的 JSON 故意保持扁平：

```json
{
  "schema_version": 1,
  "task": "arm_select",
  "task_config": "demo_clean",
  "seeds": [100000, 100001, 100002, 100003]
}
```

先完成 bridge，再在 RoboTwin/SAPIEN 环境中生成 oracle-qualified blocks：

```bash
python tools/generate_if_seed_manifest.py \
  --all \
  --task-config demo_clean \
  --accepted-blocks 2 \
  --max-candidate-blocks 20 \
  --output-dir /path/to/output
```

生成器逐个 exact seed 调用 `setup_demo`、`play_once` 与 `check_success`；任一成员失败就拒绝整个 block，不使用 `seed + 1` 替换失败成员。`--resume` 从逐 block 原子 checkpoint 续跑，并要求 task/config/count、contract、target/source commit、linked-source digest 与实际 task-config YAML SHA-256 全部一致；`--overwrite` 与 `--resume` 互斥。外部 RoboTwin 的 target 解析与 compatible-commit opt-in 和 bridge 相同。

每个 `<task>.json` 旁边的 `<task>.generation.json` 是可忽略的审计 sidecar，记录 accepted/rejected blocks、逐 seed oracle/mode 结果、source/target/config provenance、耗时和 manifest SHA-256。可在不安装 SAPIEN 的环境独立检查：

```bash
python tools/validate_if_seed_manifest.py --require-evidence /path/to/output
```

外部 policy evaluator 只需读取 `task`、`task_config`、`seeds`，并按列表逐 episode 运行。显式提供 manifest 后，某个 seed 无法运行必须判定整次评测无效；不得静默跳过、递增、补抽或回退到原生动态模式。未提供 manifest 时，RoboTwin 原生动态 seed/skip 行为保持不变，仍可用于 raw task 和 smoke test。本阶段只实现 seed pipeline；policy result JSONL、`eval_signals()`、per-mode success/gap reporter 与 CogACT replay wrapper 仍属后续工作。

### 6. 测试

测试采用可直接执行的 Python 脚本。常见入口：

```bash
python tests/test_task_bridge.py
python tests/test_eval_step_limits.py
python tests/test_task_manifests.py
python -m unittest discover -s tests -p 'test_if_seed_*.py' -v
python tests/<task>/test_instructions.py
python tests/<task>/test_check_success.py
```

不同任务的 instruction test 可能按职责命名为 `test_instruction_routing.py` 等；以各 task 测试目录为准。多数 Layer-A routing 与静态成功判定测试无需启动仿真。

## 仓库结构

```text
tasks/                  任务 env、instruction JSON 与对象描述；bridge 的 source of truth
if_benchmark/           simulator-free seed contracts、manifest 与 generation state
eval_cfg/               canonical IF 七项与 native 50 + IF 七项 task inventory
scripts/                thin shell entrypoints + stdlib ownership installer
tests/                  inventory、seed pipeline、routing 与 success invariants
tools/                  seed generator/validator、probe、report 与可视化工具
docs/                   设计及逐任务实现记录
notes/                  实验、评审与集成证据
third_party/robotwin/    锁定的 RoboTwin 2.0 submodule
```

## 当前状态

七项维护范围已固定，task inventory、bridge inventory 与 seed-contract inventory 由同一静态 gate 锁定。`pick_diverse_object` 的四类 production Unseen pool 已通过独立 gate。Bridge 已具备 external target、commit/API compatibility、collision preflight、ownership manifest、check/dry-run、stale cleanup 和安全 unbridge；七项 eval limit 也已集中固定。P2 seed pipeline 已提供 flat manifest、完整 block oracle generator、checkpoint/evidence 与 simulator-free validator。2026-09-03 的 1-block / 2-candidate bounded pilot 已完成：六项发布并独立验证了完整 manifest，`pick_diverse_object` 两组均被 whole-block rejection、未发布 partial manifest；详见 [`notes/2026-09-03-if-seed-manifest-pilot/`](notes/2026-09-03-if-seed-manifest-pilot/)。这仍不是 production freeze；task config 发布、production accepted-block 规模、`eval_signals()`/per-mode policy reporter 与 CogACT replay wrapper 尚未完成，不能由“原生 eval 能跑”替代。
