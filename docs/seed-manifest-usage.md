# Balanced Seed Manifest 使用指南

本文面向两类使用者：

1. **Manifest 生成者**：使用 RoboTwin oracle 生成一组固定、均衡、可审计的 episode seeds；
2. **Policy evaluator 使用者**：读取生成的 flat JSON，并让不同 policy 严格评测同一批 exact seeds。

如果你只负责跑 policy，通常只需要阅读“输出文件”和“在 evaluator 中使用 manifest”两节，不需要解析 `.generation.json`。

---

## 1. Manifest 解决什么问题

RoboTwin 原生 evaluator 会从一个起始 seed 开始检查 oracle。如果某个 episode 的 oracle 失败，它会递增 seed 并继续寻找可用 episode。这适合开发和 smoke test，但不保证 IF task 的不同 mode 拥有相同 denominator。

Balanced seed manifest 改为提前生成一份固定列表：

```json
{
  "schema_version": 1,
  "task": "bottle_verb",
  "task_config": "demo_clean",
  "seeds": [100002, 100003, 100006, 100007]
}
```

之后所有 policy 都按列表原顺序评测完全相同的 episode seeds。

Manifest 中的 seed 是直接传给 `task.setup_demo(seed=...)` 的 **exact episode seed**，不是 RoboTwin 原生 `eval.sh` 的 CLI run/shard seed。

---

## 2. `accepted-blocks` 与 episode 数量

生成器以完整 **balance block** 为单位接受或拒绝 candidate seeds。每个 block 恰好包含该 task 的每种 mode 一次。

因此：

```text
--accepted-blocks 100
```

表示每种 mode 各有 100 个 episodes，而不是所有 mode 合计 100 个。

| Task | 每个 block 的 modes | Block size | 100 blocks 的总 episodes |
|---|---|---:|---:|
| `bottle_verb` | pick / shake | 2 | 200 |
| `pick_diverse_object` | seen / unseen | 2 | 200 |
| `attribute_select` | color:red/blue、decal:cat/dog、shape:block/bar、size:big/small | 8 | 800 |
| `arm_select` | left / right | 2 | 200 |
| `stack_sequence` | 六种堆叠顺序 | 6 | 600 |
| `place_relative` | left / right / front / back / on_top | 5 | 500 |
| `grasp_cube_approach` | top / side | 2 | 200 |

七项都生成 100 blocks 时：

```text
每个 mode = 100 episodes
七项合计 = 2700 policy-evaluation episodes
```

例如 `bottle_verb --accepted-blocks 100` 的结果是：

```text
pick  = 100 episodes
shake = 100 episodes
总计  = 200 episodes
```

---

## 3. 准备运行环境

Manifest 生成需要 RoboTwin/SAPIEN oracle 环境；manifest 验证和 policy 侧读取 JSON 不需要 SAPIEN。

首次使用先完成 RoboTwin 环境安装和 bridge：

```bash
bash setup_robotwin.sh
bash scripts/bridge_tasks.sh
bash scripts/bridge_tasks.sh --check
```

`--check` 应显示：

```text
check passed: 18 owned links
```

生成期间不要修改以下输入：

- task env/helper/instruction source；
- RoboTwin checkout；
- task config YAML；
- generator 参数。

`.generation.json` 会记录 source digest、RoboTwin commit 和 task-config SHA-256。即使 config 文件名仍是 `demo_clean`，内容改变后也不能继续旧 checkpoint。

---

## 4. 一条命令生成七项、每个 mode 100 episodes

使用仓库提供的 wrapper：

```bash
scripts/generate_if_100_per_mode.sh outputs/if-seeds-100-per-mode
```

默认配置：

```text
Conda environment       RoboTwin
Task config             demo_clean
Accepted blocks/task    100
Candidate cap/task      500
Candidate seed floor    100000
```

脚本会按 canonical inventory 依次处理七项。某个 task 失败时，它会保留 checkpoint、继续处理后续 task，并在最后返回 nonzero。

生成可能持续数小时，建议在稳定的终端/tmux 中运行。`100 blocks` 的真实耗时取决于每项 oracle rejection rate，不能只用最终 2700 个 policy episodes 估算。

### 修改默认配置

通过环境变量配置：

```bash
IF_TASK_CONFIG=demo_clean \
IF_MAX_CANDIDATE_BLOCKS=800 \
IF_CANDIDATE_FLOOR=100000 \
ROBOTWIN_CONDA_ENV=RoboTwin \
  scripts/generate_if_100_per_mode.sh outputs/if-seeds-100-per-mode
```

可用变量：

| 变量 | 默认值 | 用途 |
|---|---|---|
| `ROBOTWIN_CONDA_ENV` | `RoboTwin` | 运行 oracle 的 Conda 环境 |
| `IF_TASK_CONFIG` | `demo_clean` | RoboTwin task config |
| `IF_MAX_CANDIDATE_BLOCKS` | `500` | 每个 task 最多检查多少个 candidate blocks |
| `IF_CANDIDATE_FLOOR` | `100000` | candidate episode seed 下界 |
| `ROBOTWIN_DIR` | nested RoboTwin | 使用外部 RoboTwin checkout |
| `IF_ALLOW_COMPATIBLE_COMMIT` | `0` | 设为 `1` 后显式接受已人工检查的 compatible target |

`IF_MAX_CANDIDATE_BLOCKS` 只是扫描上限。生成器找到 100 个 accepted blocks 后立即停止，不会为了用完 cap 继续运行。

---

## 5. 只生成一个 task

如果只需要 Verb-Select，或希望为不同 task 设置不同 candidate cap，可以直接调用 generator：

```bash
conda run --no-capture-output -n RoboTwin \
  python tools/generate_if_seed_manifest.py \
  --task bottle_verb \
  --task-config demo_clean \
  --accepted-blocks 100 \
  --max-candidate-blocks 500 \
  --candidate-floor 100000 \
  --output-dir outputs/if-seeds-100-per-mode
```

成功后会得到 100 个 pick seeds 和 100 个 shake seeds。

---

## 6. 生成器如何选择 seeds

以 `bottle_verb` 为例，candidate blocks 为：

```text
block 50000 -> [100000, 100001] -> [pick, shake]
block 50001 -> [100002, 100003] -> [pick, shake]
block 50002 -> [100004, 100005] -> [pick, shake]
```

对于每个 exact seed，生成器运行：

```text
setup_demo(seed)
→ play_once()
→ plan_success
→ check_success()
→ close_env()
```

一个 episode 必须同时满足：

- setup 成功；
- oracle planning 成功；
- task success check 成功；
- 实际 mode 与 seed contract 预期一致。

如果 block 中任一成员失败，整个 block 都被拒绝：

```text
100000 pick  pass
100001 shake fail

=> [100000, 100001] 整组拒绝
```

生成器会尝试下一整个 block，不会只保留通过的成员，也不会使用 `seed + 1` 替换失败成员。因此最终 manifest 的 block 之间可以有 gap，但每个保留 block 一定完整。

---

## 7. 输出文件

七项全部成功时，输出目录包含：

```text
outputs/if-seeds-100-per-mode/
├── bottle_verb.json
├── bottle_verb.generation.json
├── pick_diverse_object.json
├── pick_diverse_object.generation.json
├── attribute_select.json
├── attribute_select.generation.json
├── arm_select.json
├── arm_select.generation.json
├── stack_sequence.json
├── stack_sequence.generation.json
├── place_relative.json
├── place_relative.generation.json
├── grasp_cube_approach.json
└── grasp_cube_approach.generation.json
```

### `<task>.json`：给 evaluator 使用

例如：

```json
{
  "schema_version": 1,
  "task": "bottle_verb",
  "task_config": "demo_clean",
  "seeds": [100002, 100003, 100006, 100007]
}
```

正式的 100-block Bottle manifest 会包含 200 个 seeds。Evaluator 只需要读取：

- `task`；
- `task_config`；
- `seeds`。

### `<task>.generation.json`：生成与审计证据

Sidecar 记录：

- accepted/rejected candidate blocks；
- 每个 seed 的 expected/observed mode；
- setup/plan/check 状态和异常；
- source/target/config provenance；
- manifest SHA-256；
- 运行时间和 rejection summary。

普通 policy evaluator 不需要解析它。Benchmark 发布者和 validator 使用它确认 flat manifest 是在指定代码、runtime 和 config 下生成的。

### Exhausted 时的输出

如果达到 candidate cap 仍不足 100 个 accepted blocks：

```text
存在 <task>.generation.json
不存在 <task>.json
进程返回 nonzero
```

缺少 flat manifest 是有意设计：不足目标数量时不能发布较小或不均衡的 seed list。

---

## 8. 验证生成结果

Wrapper 会在每个 task 成功后自动验证。也可以独立运行：

```bash
python tools/validate_if_seed_manifest.py \
  --require-evidence \
  outputs/if-seeds-100-per-mode/bottle_verb.json
```

Bottle 100 blocks 的期望输出包含：

```text
seeds=200 blocks=100 modes=[pick=100, shake=100] evidence=verified
```

验证整个目录：

```bash
python tools/validate_if_seed_manifest.py \
  --require-evidence \
  outputs/if-seeds-100-per-mode
```

只要目录中有 exhausted sidecar 而没有相邻 flat manifest，目录验证就会返回 nonzero。这表示该 task 尚未完成，不是 validator malfunction。

---

## 9. 中断、恢复和重新生成

### 运行被中断

使用原输出目录和完全相同的参数：

```bash
scripts/generate_if_100_per_mode.sh \
  outputs/if-seeds-100-per-mode \
  --resume
```

Generator 从逐 block checkpoint 继续；已经完成的 task 不重新跑 oracle。

`--resume` 要求以下内容完全匹配：

- task/config；
- accepted-block target；
- candidate cap/floor；
- contract schema；
- RoboTwin target/commit；
- linked-source digest；
- task-config SHA-256。

任何一项改变都会 fail closed。

### 已达到 candidate cap

Exhausted checkpoint 不能通过提高 cap 后直接 resume，因为 candidate cap 是 generation provenance 的一部分。推荐使用新输出目录：

```bash
IF_MAX_CANDIDATE_BLOCKS=1000 \
  scripts/generate_if_100_per_mode.sh \
  outputs/if-seeds-100-per-mode-cap1000
```

如果明确要丢弃旧 checkpoint，也可以提高 cap 后对原目录使用 `--overwrite`，但这会从头生成：

```bash
IF_MAX_CANDIDATE_BLOCKS=1000 \
  scripts/generate_if_100_per_mode.sh \
  outputs/if-seeds-100-per-mode \
  --overwrite
```

不要用 `--overwrite` 绕过 provenance mismatch；应先确认 source/config 为什么变化。

---

## 10. 在 policy evaluator 中使用 manifest

不同 policy 必须共享同一份 `<task>.json`。典型消费逻辑：

```python
import json

with open("bottle_verb.json", encoding="utf-8") as handle:
    manifest = json.load(handle)

for episode_seed in manifest["seeds"]:
    result = evaluate_one_exact_episode(
        task_name=manifest["task"],
        task_config=manifest["task_config"],
        episode_seed=episode_seed,
        allow_seed_skip=False,
    )
    save_result(episode_seed, result)
```

`evaluate_one_exact_episode` 应把 `episode_seed` 直接用于：

```python
task.setup_demo(seed=episode_seed, ...)
```

Policy evaluator 仍负责：

- 初始化 task；
- 设置该 policy 使用的 instruction type；
- policy inference 和 action rollout；
- 调用 success/eval signal；
- 保存每个 seed 的 policy result。

Seed manifest 只负责固定 episode 集合，不包含 policy 输出。目前本仓库还没有定义通用 policy-result JSONL 或 CogACT manifest replay wrapper。

### 不要直接把 manifest seed 传给原生 CLI `seed`

RoboTwin 原生 evaluator 会把 CLI seed 转换为另一个起始 episode seed，并在 oracle-invalid 时继续递增。因此下面这种调用通常不是 exact replay：

```bash
# 错误示意：100002 在这里可能被解释为 run/shard seed
policy/eval.sh bottle_verb ... 100002 ...
```

Formal evaluator 必须使用能够直接接收 exact episode seed 的底层 one-episode 路径，绕过原生动态 seed-skip loop。

---

## 11. Policy replay 的失败规则

Manifest 中的 episode 已在对应 source/config 下通过 oracle qualification。Replay 时：

- policy 没完成任务、超时或撞到 action limit：记录为 policy failure；
- simulator/setup/asset 发生基础设施错误：将本次 evaluation 标记为 invalid/incomplete；
- 不论哪种情况，都不能偷偷换 seed。

禁止：

```text
跳过失败 seed
使用 seed + 1
重新抽一个 episode
只减少 denominator
让不同 policy 使用不同替代 seed
```

正式比较前应确认每个 policy result 都覆盖 manifest 中的每个 seed，并且没有额外 seeds。

---

## 12. 推荐发布内容

一个可复现的 benchmark seed release 至少应包含：

```text
seed-manifests/
├── README.md
├── bottle_verb.json
├── bottle_verb.generation.json
├── ...
└── grasp_cube_approach.generation.json
```

同时固定：

- robotwin-if commit；
- RoboTwin commit；
- task config 文件内容；
- generator/contract schema version；
- 每个 task 的 accepted-block count；
- 所有 manifest 与 sidecar。

不要把只有 bounded-pilot evidence、缺少 flat manifest 的目录当作 production seed release。
