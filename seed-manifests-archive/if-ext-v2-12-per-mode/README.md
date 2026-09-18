# 七任务正式评测 manifest：每项 12 blocks

本目录用于固定七任务评测，`arm_select` 和 `grasp_cube_approach` 使用 v2，其余任务使用 `demo_clean`。
任务名称保持不变，由每份 manifest 的 `task_config` 区分场景版本。所有 mode 均有 12 个 episodes。

| Task | task_config | Blocks | Episodes / policy | 可复用旧 episodes / policy |
|---|---|---:|---:|---:|
| [bottle_verb](bottle_verb.json) | `demo_clean` | 12 | 24 | 4 |
| [pick_diverse_object](pick_diverse_object.json) | `demo_clean` | 12 | 24 | 4 |
| [attribute_select](attribute_select.json) | `demo_clean` | 12 | 96 | 16 |
| [arm_select](arm_select.json) | `demo_clean_arm_select_v2` | 12 | 24 | 0 |
| [stack_sequence](stack_sequence.json) | `demo_clean` | 12 | 72 | 12 |
| [place_relative](place_relative.json) | `demo_clean` | 12 | 60 | 10 |
| [grasp_cube_approach](grasp_cube_approach.json) | `demo_clean_grasp_approach_v2` | 12 | 24 | 0 |
| **合计** | | **84** | **324** | **46** |

六个 policy 共 1,944 episodes。按原 checkpoint 和 rollout 设置继续评测时，
可复用 276 条完整旧结果（105 成功、171 失败），还需运行 1,668 条。
本次只生成并验证 manifest，没有启动新的 policy rollout。

## Seeds 的来源

五个原配置任务使用 `if-ext-v1-100-per-mode` 中最先通过 oracle 验证的 12 个完整 blocks，
保留原始 rejected blocks 的证据。它们包含 `if-seven-tasks-2blocks-001` 已完成的前 2 个 blocks。
选择顺序只依据原 oracle 资格，与六个 policy 的成功率无关。

两个 v2 任务使用从 `200000` 起的新候选 seeds，与开发集 `100000..100023` 不重叠。
验证期间未调整场景参数；每个最终任务保留左、中、右位置各 4 个 block。

- arm_select：先检查 12 个候选 blocks，其中 `200014/200015` 的左臂抓取失败，整组剔除。
  随后串行检查 `200024..200029` 的 3 个候选，均通过；按每区 4 个的覆盖要求纳入 `200026/200027`。
  另外两组通过但超过区域配额，保留记录、不纳入清单。合计 15 个候选，最终 12 个。
- grasp_cube_approach：`200000..200023` 的 12 个 blocks 全部通过，顶抓、侧抓各 12/12。
- 每次预检还包含旧版回归、重复抓取和错误指令反例。被选 block 的预定复测/反例必须全部通过，
  错误反例必须实际抬起物体且被判据拒绝。初始场景与句式配对检查通过。

arm v2 场景为 x ±2 cm、y 10–12 cm、yaw ±3°；grasp v2 为 x ±1 cm、y −6～−5 cm，
方块与底座一起平移、不旋转，oracle 固定右臂。正式清单冻结后，各 policy 都使用相同 exact seeds，
不再根据 policy 成败更换 seed。基础设施错误标记 incomplete。

## 文件与证据

- `<task>.json`：evaluator 直接读取的 flat manifest。
- 五份 `.generation.json`：从原 100-block oracle 记录截取的完整证据，包含派生来源、哈希和兼容性说明。
- 两份 `.probe.yml`：新 v2 预检的全部候选、失败、复测、反例、选择决策、源码哈希及 GPU supervisor 结果。
- [suite.yml](suite.yml)：七任务配置映射、manifest 哈希、总数、可复用和待跑 seed 列表。
- [reusable-results.yml](reusable-results.yml)：276 条旧结果的路径、SHA-256、状态，以及各 policy 的原运行参数/checkpoint 信息。

原 oracle 证据的兼容性复核：五任务源码除 attribute_select 在 setup 初始化高度基线外保持一致，
其 oracle 的 play_once 仍在抓取前重设基线；`demo_clean` 的 `episode_num` 从 50 改为 2，
只影响采集数量，不改变按 exact seed 执行的单回合；语言工具仅增加显式 UTF-8 编码。
这些差异保留在派生证据中，未将旧运行标成当前源码的新验证。

旧 policy 结果复用时已核验任务/config 哈希、任务指令/helper、模型 client/codec/server 源码、
完成状态和无 runtime error；使用当前语言函数重建的 276 条指令逐条一致。
后续新增的 evaluator 改动为共享 setup/cache/render 同步优化和两项 v2 分支。
复用以继续使用索引记录的 checkpoint revision、模型输入输出、指令 split 和 rollout 选项为前提。
原失败结果保留；运行耗时应按优化设置分开统计。

## 使用与续跑

完整评测示例，其余模型参数沿用对应 policy：

```text
--task arm_select
--task-config demo_clean_arm_select_v2
--seed-manifest seed-manifests/if-ext-v2-12-per-mode/arm_select.json
--blocks 12
```

其他任务读取自身 JSON 中的 `task_config`，不要对七项统一硬编码为 `demo_clean`。
v2 配置安装方式见 [arm v2](../../docs/arm-select-v2.md) 和 [grasp v2](../../docs/grasp-approach-v2.md)。

复用旧结果续跑时，以 `suite.yml` 的 `pending_seeds_per_policy` 为待跑清单；
五个原任务还需后 10 个 blocks，两个 v2 任务需全部 12 个 blocks。
evaluator 的 `--blocks 10` 表示取前 10 个，**不能用它跳过已完成的前 2 个**；
续跑器应从待跑 seeds 导出临时的完整 block manifest，再合并旧结果并核对正式完整分母。

## 校验

在 RoboTwin Python 环境下执行，无需 GPU：

```bash
python seed-manifests/if-ext-v2-12-per-mode/verify.py
```

它检查七份 manifest、每 mode 分母、五项原 oracle 证据、两项 v2 配对和控制证据、
开发集不重叠、场景覆盖、复用清单以及总数。
通用 `tools/validate_if_seed_manifest.py` 也能校验本目录的 flat JSON 和五份 `.generation.json`，
但其 `--require-evidence` 只识别 `.generation.json`，不读取 v2 的 `.probe.yml`。

原始新预检记录保留在 `outputs/policy-eval/arm-select-v2-formal-12blocks-001`、
`arm-select-v2-formal-12blocks-002` 和 `grasp-approach-v2-formal-12blocks-001`。
构建与复用核验脚本位于 `outputs/policy-eval/if-seven-formal-v2-12blocks-build-001/`。
