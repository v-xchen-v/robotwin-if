# New-task integration closeout: bridge、外部 repo 与 seed 评测规范

Date: 2026-09-03

> 目的：审计新增 task 相对 RoboTwin raw/native task 的集成完整度，明确 bridge/unbridge 的边界、其他 repo 的推荐接入方式，以及正式 IF benchmark 对 seed 采样和指标统计的额外要求。
>
> 这份文档更新并收紧了 `notes/2026-08-19-task-bridging/` 与 `notes/2026-08-27-eval-flow/understanding.md` 的早期结论：**bridge 后在 task discovery / Base_Task 接口层与 raw task 等价，但“能用原生 eval 跑”不等于“得到 benchmark-correct 的 IF 结果”。**

---

## 0. 结论先行

**bridge 之后，新增 task 在 RoboTwin 的任务发现和执行接口层可以像 raw task 一样使用；但在可复现 benchmark 层，目前还不能完全等价。**

| 层次 | 当前状态 | 结论 |
|---|---|---|
| Task discovery / import | 文件名、类名、task name 对齐 | 等价 |
| `Base_Task` 生命周期接口 | 复用统一的 setup/play/check/get/set/take 接口 | 等价 |
| 原生 collect | 可走 `collect_data.py` | 基本等价，能跑 |
| 原生 binary eval | 可走具体 policy 的 `eval.sh` / `eval_policy.py` | 基本等价，能跑 |
| IF benchmark sampling | complete-block generator/validator 与 bounded pilot 已完成；production 规模尚未冻结 | 基础设施与小规模实测完成，release 未完成 |
| IF benchmark metrics | 原生 eval 不读取 `eval_signals()`，不报 per-mode/gap | 尚不等价 |

对外应采用两句分层承诺：

> **Runtime compatibility:** bridge 后，新增 task 是标准 RoboTwin task plugin，可通过原生 collect/eval 的 task-name 接口运行。
>
> **Benchmark reproducibility:** 正式 IF 结果必须使用 robotwin-if 提供的固定 balanced seed manifest 和 IF reporter；让原生 evaluator 自行递增并跳过 seed，只适合 smoke test，不应直接作为最终 benchmark 数字。

---

## 1. High-level 结构

```text
robotwin-if
├── tasks/envs/                  新增 task 实现；source of truth
├── tasks/task_instruction/      seen/unseen 指令模板
├── tasks/objects_description/   新对象描述（如有）
├── task configs                 尚需正式纳入主仓库并 bridge
├── eval_cfg/                    task suite / benchmark inventory
├── if_benchmark/                simulator-free seed contract/manifest/state
├── tools/
│   ├── generate_if_seed_manifest.py   real-oracle complete-block generator
│   └── validate_if_seed_manifest.py   stdlib-only validator
└── scripts/
    ├── bridge_tasks.sh          将 task plugin 安装进 RoboTwin runtime
    └── unbridge_tasks.sh        卸载本 bridge 拥有的注入项
             │
             ▼
RoboTwin runtime
├── envs/<task>.py
├── description/task_instruction/<task>.json
├── description/objects_description/...
├── task_config/...
└── script/
    ├── collect_data.py
    └── eval_policy.py
             │
             ▼
Policy repository / policy server
```

Bridge 的职责应严格限定为：

> **将 robotwin-if 中维护的 task plugin 暴露给某个兼容的 RoboTwin runtime。**

Bridge 不负责：

- 选择正式 benchmark episodes；
- 保证 mode/axis/value 均衡；
- 决定不同 policy 使用哪些 seeds；
- 计算 per-mode、directional/default gap；
- 拆分 execution 与 instruction-following signal。

这些属于 bridge 之上的 benchmark manifest/eval wrapper/reporter。

---

## 2. 为什么 bridge 后可以按 raw task 的方式调用

RoboTwin 原生入口按 `task_name` 动态发现任务：

```python
module = importlib.import_module(f"envs.{task_name}")
env_class = getattr(module, task_name)
```

所以必须同时满足：

```text
envs/arm_select.py
class arm_select(...)
CLI task_name = arm_select
```

新增任务也遵循标准 `Base_Task` 生命周期：

- `setup_demo(...)`
- `play_once()`
- `check_success()`
- `get_obs()`
- `set_instruction(...)`
- `take_action(...)`

Instruction generator 同样按 task name 读取：

```text
description/task_instruction/<task_name>.json
```

因此 bridge 后，原生 collector/evaluator 不需要知道文件来自 upstream 还是 robotwin-if symlink；在命令中把 raw task name 换成 new task name 即可。

概念调用：

```bash
cd <robotwin-runtime>

# collect
bash collect_data.sh <new_task_name> <task_config> ...

# eval；其余参数按具体 policy/eval.sh 的签名填写
bash policy/<policy>/eval.sh <new_task_name> ...
```

注意：不同 policy 的 `eval.sh` 参数并不统一。ACT 类入口常见六参数，但 Your_Policy、GO1、OpenVLA 等存在不同签名。文档只能承诺 task name 的替换方式一致，不能给所有 policy 宣称一个统一参数表。

---

## 3. Bridge/unbridge 审计

### 3.1 2026-09-03 P1 实现状态

Shell 脚本现为 thin entrypoint，实际逻辑由 stdlib-only `scripts/_task_bridge.py` 统一实现。Bridge 不再 glob 全仓库，只维护 canonical IF 七项：

1. 7 个 `tasks/envs/<task>.py` → `RoboTwin/envs/`；
2. 4 个共享 helper → `RoboTwin/envs/`；
3. 7 个同名 instruction JSON → `RoboTwin/description/task_instruction/`。

总计 18 个 owned links。Inactive/legacy env 仍可保留 source，但不进入安装 inventory；当前七项不需要 object-description bridge。

已实现并由 simulator-free integration test 覆盖：

- `--robotwin-dir` / `ROBOTWIN_DIR` / nested default 三层 target resolution；
- 全量 collision preflight，foreign/dangling symlink、真实文件和目录均在 mutation 前拒绝；
- target-side `.robotwin-if-bridge.json` ownership state 与原子写入；
- `--dry-run`、`--check` 和幂等重跑；
- adoption of correct legacy links；
- manifest-backed stale cleanup 与旧 inactive glob-link cleanup；
- source rename/delete 后仍可 unbridge；
- 被修改的 destination 只 `skip-modified`，保留 state，不误删；
- manifest path confinement、raw-target/source consistency 与 corrupt-state rejection；
- link mutation 异常时回滚本次新增/移除项。

### 3.2 安全与兼容性规则

#### Target resolution

```bash
scripts/bridge_tasks.sh --robotwin-dir /path/to/RoboTwin
scripts/unbridge_tasks.sh --robotwin-dir /path/to/RoboTwin
```

解析优先级固定为：

1. CLI `--robotwin-dir`；
2. `ROBOTWIN_DIR` 环境变量；
3. 默认 nested `third_party/robotwin`。

#### Collision preflight

- destination 不存在：计划 `add`；
- destination 已解析到 exact current source：`adopt` 或 `ok`；
- foreign/dangling symlink：`collision`；
- 真实文件或目录：`collision`；
- 任一 collision 使整次 bridge 在 mutation 前失败。

没有 `--force`；installer 不会覆盖非本 bridge 所有的内容。

#### Ownership 与 stale cleanup

成功 bridge 后原子写入 `<robotwin-dir>/.robotwin-if-bridge.json`，记录 schema、source/target roots 与 commits、source dirty / linked-source SHA-256 digest / target contract dirty provenance、compatibility opt-in，以及每个 link 的 source-relative path、target-relative destination 和 exact raw symlink target。Bridge/check/unbridge 使用 target-directory `flock` 串行化完整 preflight→mutation→state transaction；dry-run 不会为了锁而新建 target 文件。

后续 bridge 会把 state 中不再属于 desired inventory 的项视为 stale；只有 destination 仍是 exact recorded symlink 时才删除。Unbridge 同样读取 state，而不是枚举当前 source，因此 source 文件已重命名/删除也能清理。若 destination 被改动，则保留该文件和对应 ownership entry，并以 nonzero exit 要求人工处理。

无 manifest 的 legacy unbridge 只做保守 fallback：删除仍解析到本仓库现存 source 的旧 links，并警告无法发现 source 已删除的历史链接。

#### Commit / API compatibility

Locked commit 是 `0aeea2d669c0f8516f4d5785f0aa33ba812c14b4`。Mismatch、git top-level 不等于所选 target、无 git metadata，或 compatibility contract paths 有本地修改，均默认拒绝；`--allow-compatible-commit` 只显式接受这些 provenance 差异，不能跳过以下 simulator-free static contract：

- Base_Task 文件和七项使用的方法；
- instruction loading/filtering/seen-unseen placeholder replacement；
- `Actor`、`ArmTag`、`UnStableError`、`create_actor`、`create_box`、`rand_pose` 等 env utility symbols；
- collect/eval scripts、global config、eval-step-limit config 和 injection directories。

#### Fresh clone / CI / worktree 必须重新 bridge

软链是 workspace installation state，不属于 RoboTwin submodule commit。因此：

- fresh clone 后要重新 bridge；
- 新 worktree 要重新 bridge；
- 每个 CI job 要重新 bridge；
- 更新 robotwin-if commit 后建议重新 bridge；
- bridge 后 RoboTwin submodule 显示 untracked/dirty 是当前方案的预期副作用。

---

## 4. 外部 repo 的两种接入模式

### 方案 A（推荐）：使用 robotwin-if 锁定的 nested RoboTwin

```text
external-policy-repo/
└── third_party/robotwin-if/
    ├── tasks/
    └── third_party/robotwin/
```

初始化：

```bash
git submodule update --init --recursive
cd third_party/robotwin-if
scripts/bridge_tasks.sh
```

之后将：

```text
third_party/robotwin-if/third_party/robotwin
```

作为仿真与评测 runtime。

优点：

- robotwin-if commit 与 RoboTwin commit 一起锁定；
- 最容易复现；
- 避免外部 RoboTwin API 漂移；
- 最适合 benchmark release 和论文评测。

缺点：

- 外部 repo 已经包含 RoboTwin 时可能出现两个 checkout；
- 外部启动脚本需要明确指向 nested runtime。

对于 CogACT/X-VLA 一类外部 policy repo，推荐由 CogACT 提供模型推理端，由 robotwin-if 锁定的 RoboTwin runtime 运行任务；不需要把 policy 集成进 robotwin-if。

### 方案 B：bridge 到外部 repo 已有的 RoboTwin

```text
external-policy-repo/
├── third_party/robotwin/
└── third_party/robotwin-if/
```

目标接口：

```bash
third_party/robotwin-if/scripts/bridge_tasks.sh \
  --robotwin-dir third_party/robotwin --dry-run
third_party/robotwin-if/scripts/bridge_tasks.sh \
  --robotwin-dir third_party/robotwin
third_party/robotwin-if/scripts/bridge_tasks.sh \
  --robotwin-dir third_party/robotwin --check
```

若 external checkout 不是 locked commit，以上三步需要显式加入 `--allow-compatible-commit`；这只表示调用方接受 commit mismatch，静态 API contract 仍强制执行，actual commit 会记录到 ownership state。

优点：

- 只保留一个 RoboTwin checkout；
- 容易融入外部 repo 的既有启动脚本。

缺点：

- 调用方必须明确承担 compatible-but-not-identical runtime 风险；
- 不同 policy repo 可能实际使用不同 upstream 版本；
- benchmark 复现性低于 locked nested 模式。

---

## 5. 尚未完成的运行配套

### 5.1 Task configs 没有正式进入 bridge

当前 bridge 不处理 `task_config`。本地 `pdo_bench.yml`、`pr_bench.yml` 位于 submodule ignored workspace，fresh clone 不会获得；`demo_clean.yml` 还有本地 `episode_num: 50 → 2` 修改，不能作为发布依赖。

建议主仓库增加：

```text
tasks/task_config/
├── if_collect.yml
├── if_eval.yml
└── ...
```

普通 task-specific config 可以 symlink 到 RoboTwin `task_config/`。共享 `_eval_step_limit.yml` 不能整文件 symlink，否则会覆盖 upstream native-task map。

### 5.2 Maintained seven 的 eval step limit（P1 已实现）

`tasks/envs/_if_eval.py` 是唯一 mapping；七个 maintained env 都在 `super()._init_task_env_` 返回后调用 helper，只在 eval mode 覆盖 limit：

| Task | Limit | Structural analog |
|---|---:|---|
| `bottle_verb` | 700 | longest branch = native `shake_bottle` |
| `pick_diverse_object` | 400 | single grasp/lift |
| `attribute_select` | 400 | single grasp/lift |
| `arm_select` | 400 | single grasp/lift |
| `stack_sequence` | 1200 | native `stack_blocks_three` |
| `place_relative` | 400 | native `place_a2b_left` |
| `grasp_cube_approach` | 400 | single grasp/lift |

这样不修改 external RoboTwin tracked `_eval_step_limit.yml`。Locked Base_Task 可能先打印“不在 step-limit file、fallback 1000”，但 task helper 紧接着覆盖，policy rollout 消费的是表中值。

已有 oracle HDF5 的最大 recorded frames 按表中顺序是 255/103/89/89/479/163/99，只是相对复杂度证据；policy eval 的 `step_lim` 统计 action calls，不能从 oracle frame count 直接校准。后续必须在 CogACT rollout 中记录是否撞 limit；若有 truncation，再同时更新 central map 和 contract test。

---

## 6. Seed：不是简单的“不能跳”，而是不能按单 seed 任意跳

### 6.1 必须区分三层 seed

#### CLI run/shard seed

原生 eval 将 CLI seed 转成：

```python
st_seed = 100000 * (1 + run_seed)
```

所以 CLI `seed=0` 实际从 episode seed 100000 开始，不是从 0 开始。

#### Raw episode seed

这是传入：

```python
TASK_ENV.setup_demo(seed=now_seed)
```

的 seed。

#### Task 内部 scene/mode seed

例如 Place-Relative：

```python
scene_seed = episode_seed // 5
direction = ORDER[episode_seed % 5]
```

相邻五个 raw episode seeds 构成一个完整 same-scene group。

### 6.2 原生 eval 的 expert filtering 会破坏均衡

对每个 candidate seed，原生 eval 先运行 oracle expert-check：

1. `setup_demo(seed)`；
2. `play_once()`；
3. 只有 `plan_success && check_success()` 才接受；
4. 失败、异常或不稳定就递增 seed；
5. 接受后才用同一个 seed 跑 policy；
6. 直到积累 `test_num=100` 个 accepted episodes。

所以 candidate seeds 连续，不代表最终 evaluated seeds 连续。如果某个 mode 的 oracle 成功率较低，它会被过滤更多，最终 denominator 就会偏斜。

### 6.3 Maintained seven 的 balance block 与 same-scene subgroup

“完整 balance block”和“pixel-identical same-scene group”不是同义词。生成器按前者接收/拒绝，contract 另外描述后者：

| Task | Balance block | Same-scene 结构 |
|---|---:|---|
| Bottle pick/shake | 2 | 一组 2-seed pair |
| Pick-Diverse Seen/Unseen | 2 | 两个独立 familiarity scenes |
| Attribute 四 axis × 二 value | 8 | 四组相互独立的 2-seed same-scene pairs |
| Arm left/right | 2 | 一组 2-seed pair |
| Stack-Sequence 六排列 | 6 | 一组 6-seed scene |
| Place-Relative 五方向 | 5 | 一组 5-seed scene |
| Grasp top/side | 2 | 一组 2-seed pair |

因此不能把 Attribute 的八个 seed 描述成同一物理 scene，也不能把 Pick-Diverse 的 seen/unseen 描述成 target-only pixel-identical contrast。`if_benchmark/seed_contracts.py` 是这七项 seed arithmetic 的 canonical simulator-free contract；静态测试要求其 inventory/order 与 `eval_cfg/if_tasks.yml`、bridge inventory 完全一致。

无 oracle filtering 时，100 episodes 对 period 5 可整除，但对 period 6 和 8 先天不能逐 cell 均分。加上 expert filtering 后，即使 period 能整除，accepted set 仍可能失衡。

### 6.4 正式评测规则与已实现 seed pipeline

正确规则不是“任何 seed 都不能跳”，而是：

1. 生成阶段不能任意挑选或跳过单个 episode seed；
2. 以 task 的完整 balance block 为采样单位；
3. block 中任一 mode oracle-invalid，则整组拒绝；
4. 继续寻找下一个完整 valid block，因此 accepted block IDs 可以有 gap；
5. 一次性生成 validated balanced manifest；
6. 所有 policy 重放完全相同的 exact seed list；
7. policy eval 阶段不再重新选择、递增或替换 seeds；
8. episode 数必须是 balance block size 的倍数；
9. rich oracle/provenance/rejection evidence 放在独立 sidecar，不增加 evaluator 的数据协议。

面向其他 evaluator 的 canonical manifest 故意只有四个字段：

```json
{
  "schema_version": 1,
  "task": "place_relative",
  "task_config": "demo_clean",
  "seeds": [100000, 100001, 100002, 100003, 100004]
}
```

其他 repo 的消费边界就是 `task_name + task_config + seed -> one episode`，不需要理解 block ID、scene ID、mode label 或 rejection reason。`<task>.generation.json` 才保存 expected/observed mode、setup/plan/check 结果、accepted/rejected block、source/target commit、linked-source digest 与实际 task-config YAML SHA-256，并以 canonical manifest SHA-256 绑定上述 flat JSON。

当前 `tools/generate_if_seed_manifest.py` 通过 `collect_data.main()` 捕获 task instance 和完整 config，但不进入原生 online skip loop，也不复用会改成 `seed + 1000` 的诊断 helper。它对每个 exact seed 依次执行 setup/play/check/close，逐 block 原子 checkpoint；`--resume` 对 immutable parameters 和 provenance fail closed。`tools/validate_if_seed_manifest.py` 只依赖标准库，可在外部 evaluator 或 CI 中独立验证完整 block、顺序、唯一性、mode denominators 及 sidecar/hash 一致性。

---

## 7. 原生 eval 的能力边界

原生 eval 可以回答：

> 在这批 oracle-valid episodes 中，policy 的 overall binary success 是多少？

但当前不能回答：

- 每个 mode/axis/value 的 denominator 和 success；
- left/right、open/close 等方向性 gap；
- default/non-default gap；
- policy 是否完成了动作但遵循了错误 mode；
- `eval_signals()` 中的 execution/following 分解；
- 哪些 seeds 被 oracle filter 掉以及原因；
- 最终 accepted set 是否均衡。

因此：

- 开发 smoke test：原生 `eval_policy.py` 足够；
- 正式 IF benchmark：必须使用 manifest-aware wrapper/reporter，不能只保存一个 overall success 数。

---

## 8. 当前明确 blocker

### P0：发布前必须完成

1. **Pick-Diverse Unseen production pool（已于 2026-09-03 完成）**
   - `tasks/envs/_pick_diverse_object_pool.py::UNSEEN_POOL` 已锁定四类：dumbbell、speaker、wooden mallet、paintbrush；
   - feature 文档记录了 exact variant confirmation 与 production-seed coexistence/oracle 结果；
   - `tests/pick_diverse_object/test_pool.py` 当前 34/34，通过至少四个 raw-task-Unseen nouns、精确 ID provenance、seed schedule 与 override 默认值检查；
   - `pick_diverse_object` 是七项 maintained suite 的 Noun-Grounding task；pool readiness 已解除，但下一项所述未跟踪 helper 仍必须纳入提交。

2. **提交 Pick-Diverse helper**
   - `_pick_diverse_object_pool.py` 当前未跟踪；
   - `pick_diverse_object.py` 已直接 import 它；
   - 提交时漏掉该 helper 会导致 fresh clone import 失败。

3. **Place-Relative stale test（已于 2026-09-03 修复）**
   - env 和 JSON 使用统一 `{A},{B},{D},{a}` 五方向 schema；
   - 测试已删除旧 `{B}`/`{C}` 双 family 假设，改为验证统一 schema、`{D}` 紧邻 `{B}`、seen/unseen 零重叠，以及五个方向的真实 filtering/rendering；
   - `python tests/place_relative/test_instructions.py` 当前为 25/25；RoboTwin 的真实 `filter_instructions` / `replace_placeholders` 对五个方向均完整通过，无残留 placeholder。

4. **正式维护 task inventory/manifests（已于 2026-09-03 完成）**
   - `eval_cfg/if_tasks.yml` 是唯一机器可读的 maintained IF source of truth，固定为七项：`bottle_verb`、`pick_diverse_object`、`attribute_select`、`arm_select`、`stack_sequence`、`place_relative`、`grasp_cube_approach`；
   - `eval_cfg/all_tasks_plus_if.yml` 原样保留 locked native 50，并按同序追加七项，共 57 个唯一 task；
   - 不再维护重叠的 paper/ext/all-active 三份列表；早期或实验 env 可保留源码，但未列入 `if_tasks.yml` 即为 inactive；
   - suite membership 与 production readiness 分离：Pick-Diverse 属于七项，其四类 Unseen pool 已锁定并由独立 gate 持续约束；
   - `tests/test_task_manifests.py` 静态锁定完整顺序、inactive exclusion、env/class/JSON 及 bridge inventory 契约，当前 56/56 通过。

5. **Task configs 回归主仓库并参与 bridge。**

### P1：达到“外部 repo 好用”（2026-09-03 已完成）

1. `--robotwin-dir` 与 `ROBOTWIN_DIR`：完成；
2. collision preflight / no-force policy：完成；
3. atomic ownership manifest：完成；
4. `bridge --check` / `--dry-run`：完成；
5. manifest stale-link 与 inactive legacy-link cleanup：完成；
6. strict-by-default RoboTwin API/commit compatibility：完成；
7. maintained seven 的 analog-derived fixed eval limits：完成；
8. README nested/external 两种接入模式：完成。

静态/临时 target 验证：`test_task_bridge.py` 24/24、`test_eval_step_limits.py` 18/18、`test_task_manifests.py` 56/56。Policy rollout truncation 检查仍是 limit calibration 的后续实证，不属于本 P1 installer change。

### P2：达到 benchmark-correct

1. balanced seed-manifest generator：**基础设施与七任务 bounded pilot 已完成；6/7 在两组 candidate 内产生完整 manifest，Pick-Diverse bounded exhaustion**；
2. complete-block oracle validation：**已实现**；
3. flat manifest schema 与 simulator-free validator：**已实现**；
4. checkpoint、rejected seeds/reasons、provenance 与 hash sidecar：**已实现**；
5. 所有 policy 共享 manifest：消费规范已定义，production manifest 尚未冻结；
6. eval wrapper 消费 `eval_signals()`：未实现；
7. 输出 per-mode denominator/success：validator 可报 denominator，policy success reporter 未实现；
8. 输出 default/non-default 或 directional gap：未实现；
9. CI 检查 manifest balance 和 instruction routing：seed contract/manifest 单测已实现，frozen release artifact gate 待 production manifest。

---

## 9. 推荐收尾顺序

1. 提交时确保未跟踪的 Pick-Diverse helper、bridge core、eval helper、seed pipeline 和新增 tests 全部纳入；
2. bounded pilot 已完成；基于其 rejection/runtime evidence 复查 Pick-Diverse 当前 source，随后在一个固定 linked-source digest 下扩大 candidate cap，并决定 production accepted-block count；
3. 将可发布的 task configs 回归主仓库（本 P1/P2 seed pipeline 未 bridge 本地 ignored configs）；
4. 冻结 production manifests 后，让 CogACT 按 flat seed list 严格重放，并实现 `eval_signals()`/per-mode/directional reporter；
5. 在 policy rollout 中记录 step-limit hit/truncation，再按实证调整 central map。

当前可以可靠地说“七项 maintained task bridge 后能像 raw task 一样通过原生接口运行”，且“已有生成固定均衡 seed list 的可审计工具，并完成了 1 accepted block / 2 candidate blocks 的七任务 bounded pilot”。该 pilot 中六项成功发布完整 manifest，Pick-Diverse 以两个完整 rejection blocks bounded exhaustion；它不是 production freeze。只有扩大可靠性证据、冻结 production manifests 并完成 policy reporter 后，才可以说“不同 policy 的 IF benchmark 数字具有固定、均衡、可比较的评测语义”。

---

## 10. 本次审计的验证边界

已执行：

- installer/helper/tests Python compile 与 bridge/unbridge shell syntax；
- 临时 compatible targets 的 collision、dry-run、install、adopt、idempotence、check、stale cleanup、safe unbridge、corrupt-state 测试（24/24）；
- locked nested checkout dry-run、真实 bridge、18-link ownership manifest 校验、`--check`、unbridge dry-run（18 removable / 0 modified）；
- nested default、explicit `--robotwin-dir`、`ROBOTWIN_DIR` 三种 target resolution；
- inactive legacy env/JSON links 已从 nested checkout 清除；
- fixed eval-limit map 与七项 post-init AST wiring/inventory contract（18/18）；
- canonical IF 7 + native 50 + exact bridge inventory contract（56/56）；
- simulator-free instruction/routing tests；
- Place-Relative 五方向真实 renderer（25/25）；
- Pick-Diverse pool 静态 gate（34/34，production Unseen=4 nouns）与 reporter（10/10）；
- 七任务真实 SAPIEN bounded seed pilot（每项目标 1 accepted block、最多 2 candidate blocks）：六项成功，Pick-Diverse bounded exhaustion；
- 六份 flat manifest 的 block/mode denominator、sidecar SHA-256/provenance 独立验证；目录级 validator 按设计对 Pick-Diverse orphan exhausted evidence 返回 nonzero；
- post-pilot `--resume --all` 在 linked-source digest 改变后 fail closed，未重跑或改写 artifacts；
- `git diff --check`。

未执行：

- production-scale SAPIEN/GPU oracle sweep；
- CogACT policy-action truncation/step-limit calibration；
- 另一份真实 external RoboTwin checkout 的 compatible-commit bridge（已用临时 API-compatible target 覆盖 mismatch opt-in）；
- 任一 policy 的完整 balanced-manifest evaluation。
