# 任务判定与初始化修复：哪些评测结果需要重跑

核对日期：2026-09-16。项目：`robotwin-if`。状态：已完成代码差异与现有结果来源核对；本笔记不启动评测。

## 结论与适用范围

当前分支直接修过三个现役任务的 success check 或初始化逻辑：**Bottle-Verb、Arm-Select、Attribute-Select**。
已下线的 Grasp-Approach 也有类似修复和场景随机化改动。Place-Relative 是评测范围从五模式缩为三模式，保留模式的场景与判定没有改变。

**当前最新六任务、20-block、Bottle v6 结果已覆盖这些修复，不需要因为本次审计发现的分支改动再重跑。**
这不等于所有 success checker 都已经通过逐视频人工验证，也不能推广到任意旧输出目录。

本次比较固定为：

- 分支：`feat/open-source-policy-inference`。
- HEAD：`72d7c36b68d13f7209e0307a8f4e7765cef9740b`。
- `origin/master` 与 merge base：`1685b397a97dc6aee55d60ea4980d9cdacfc0597`。
- 当前结果包：[六任务 Spatial3 / Bottle v6 / 20 blocks](../../result/if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/README.md)。
- 当前原始运行：`/Data/robotwin-if/evaluations/if-six-tasks-spatial3-bottle-v6-terminal-20blocks-001`。
- 历史五任务复用链包含：`/Data/robotwin-if/evaluations/if-seven-tasks-v2-wide-20blocks-001` 及其更早的 12-block 原始批次。

## 按任务判断

| 任务 | 分支实际改动 | 对旧结果的影响 | 当前结果是否需要重跑 |
|---|---|---|---|
| Bottle-Verb / `bottle_verb` | `72d7c36`：旧绝对峰值高度判定改为相对抬升、旋转稳定与摇晃否决；pick 完整动作预算后裁决 | 原始判定及 v3/v4/v5 的 pick 结果不能当作 v6。旧成功回合可能提前结束，缺少之后的轨迹，不能只重算 CSV | **不需要**：240/240 回合均已采用 v6，包含兼容的 2 个 X-VLA 试跑回合及后续补跑的 238 回合 |
| Arm-Select / `arm_select` | `ff4ef3f`：在 `setup_demo()` 后初始化 `_init_box_z`；`95e652b`：v2 位置、yaw 随机化及配对句式 | 修复前直接 policy 评测可能一直判失败；旧 fixed-v1 场景也不能替代 jitter-v2 | **不需要**：240/240 回合的实际任务源码与修复后版本一致，配置均为 `demo_clean_arm_select_v2` |
| Attribute-Select / `attribute_select` | `feaae02`：在 setup 后初始化目标与干扰物的 `_init_z` | 修复前 policy reset 后高度字典为空，`_raw_success()` 返回 False；这类结果需要重跑 | **不需要**：960/960 回合的实际任务源码与修复后版本一致 |
| Place-Relative / `place_relative` | `bf25bc3`：移除 front/back，仅保留 left/right/on_top | 过滤被移除模式并重算 Spatial、Overall；保留模式不用重新执行 | **不需要**：360 回合已保留原结果；新旧源码哈希不同，但保留场景与几何判定等价已单独核对 |
| Pick-Diverse-Object / `pick_diverse_object` | 相对 master，任务初始化和成功判定没有改动 | 没有由本分支产生的重跑要求 | **不需要**：240 回合；人工复核遗留问题另见下文 |
| Stack-Sequence / `stack_sequence` | 相对 master，任务初始化和成功判定没有改动 | 没有由本分支产生的重跑要求 | **不需要**：720 回合 |
| Grasp-Approach / `grasp_cube_approach`，已下线 | `385a786`：初始高度与 policy 抓取接近方向观测修复、平移 v2；`f93ab85`：扩大平移范围；`8950235`：迁入 bak | 旧 oracle 专属初始化/遥测逻辑下的 policy 结果，以及固定场景或窄范围结果，不能替代修复后的 wide-v2 | 不属于正式六任务，目前无需重跑；本次没有逐条审计其全部历史结果来源 |

### Bottle：改变的不只是高度阈值

旧代码只要求历史最高高度超过 `0.95 + table_z_bias`；摇晃跨过高度线也会通过，且首次成功会提前结束回合。
当前 `relative-lift-hold-v6-terminal` 的 pick 在完整执行 700 个动作后判定：

- 末尾至少 3 秒仿真时间，瓶子相对初始静置高度始终抬升至少 3 cm。
- 允许平移；末尾姿态相对窗口起点在 10° 内。
- 保持段最近 3 秒累计转角超过 135°，或首次抬升后同一世界轴出现至少两次达到 10° 的有效旋转反向，锁定为摇晃；随后稳定也不恢复成功。
- 三秒是末尾稳定窗口；整个 700-action 预算都持续观察，避免“先稳定、后摇晃”因早停漏判。

场景实例的物理步观察器负责采样、计时和 reset；六个 evaluator 在最后一个动作执行完后统一调用最终裁决。
因此兼容性要同时核对 task、helper、评测入口、checker 版本与参数，不能只检查高度常量。
shake 仍使用原累计纵向位移条件，此次未改变其定义；本次正式更新按整个 Bottle 任务重新建立了 40 回合/policy 的一致结果集。

依据：[判定说明](../../docs/bottle-verb-pick-hold.md)、[任务入口](../../tasks/envs/bottle_verb.py)、
[旋转保持监测器](../../tasks/envs/_if_bottle_verb.py)、[公共评测接线](../../policies/evaluation.py)。

### Arm / Attribute：policy 初始化路径与 oracle 路径不同

修复前，初始高度基准在 oracle 的 `play_once()` 中建立。policy 通常在资格检查后重建环境，再直接执行模型动作，
不会在这个新环境里先执行 `play_once()`。所以“oracle 成功”不能证明 policy 的成功判定基准已经正确初始化。

Arm 的空基准和 Attribute 的空字典会导致直接 policy 路径一直失败。修复把基准记录移到 setup 后，使用物体静置高度。
这里不是 Attribute 场景采样整体重写，也不是 oracle 演示与 manifest 全部失效。
若某个外部 evaluator 曾自行补过高度基准，应检查其实现，不能一律按修复前 commit 判为不可用。

依据：[Arm setup 与判定](../../tasks/envs/arm_select.py)、[Attribute setup 与判定](../../tasks/envs/attribute_select.py)、
[Arm v2 配置与场景契约](../../docs/arm-select-v2.md)。

### Spatial：减模式不等于改场景

正式 manifest 保留 `left=5k`、`right=5k+1`、`on_top=5k+4`，继续使用 `scene_seed = seed // 5`。
不能因为只剩三个模式就把种子改成连续编号或改为 `seed // 3`，否则会改变场景。

本次将当前实现与历史实际运行的 `support/source-snapshot/tasks/envs/` 对照：
`_if_relative.py` 的函数体没有改变；`place_relative.load_actors()` 除方向查表赋值外 AST 一致。
其他相关差异是拒绝退休模式和维护模式列表。保留方向的采样与成功几何条件没有变化。
因此历史 task hash 与当前不一致是预期情况，应以具体语义差异判断能否复用。

这是观察结果后缩小评测范围，Spatial / Overall 上升不代表模型能力提升。
依据：[三模式决策与证据](../../docs/place-relative-spatial3.md)、[场景一致性检查](../../tests/test_spatial3.py)。

## 当前结果的来源证据

本次从当前包 `episodes.csv` 的 2,760 行逐条出发，递归读取回合 `_provenance.json` 的 `source_directory`，
追到实际 evaluator 写出的目录，而非只读取最新复制目录的 metadata。随后核对：

1. 原始 `_result.json` SHA-256 是否等于 CSV 的 `record_sha256`。
2. 原始目录 `run.json` 的 `task_source_sha256` 和 `arguments.task_config`。
3. 原始 task hash 与当前任务文件是否一致；Spatial 的差异另做语义比较。

| 任务 | 已核对回合 | 每个 policy 回合数 | 实际来源分组数¹ | 原始 result 哈希匹配 | task hash 与当前一致 |
|---|---:|---:|---:|---:|---:|
| Bottle-Verb | 240 | 40 | 7 | 240 | 240 |
| Arm-Select | 240 | 40 | 13 | 240 | 240 |
| Attribute-Select | 960 | 160 | 17 | 960 | 960 |
| Pick-Diverse-Object | 240 | 40 | 18 | 240 | 240 |
| Stack-Sequence | 720 | 120 | 22 | 720 | 720 |
| Place-Relative | 360 | 60 | 20 | 360 | 0；保留模式语义一致 |
| 合计 | **2760** | **460** | **97** | **2760** | **2400** |

¹ 分组由 task、policy、实际来源目录、源码哈希、配置与记录哈希校验状态共同确定，不是 block 数。

完整结果为 720/720 blocks；Bottle 240 回合使用 v6，其他五任务复用 2,520 回合。
Bottle checker / terminal 条件的核对证据另保存在当前结果包的
[validation.json](../../result/if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/validation.json) 和
[provenance.json](../../result/if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/provenance.json)。
本笔记附带 [来源审计快照](source-audit.json)，保存逐任务计数、源码哈希、配置与 97 个来源分组，不复制视频。

## 以后怎样判断复用、重算还是重跑

| 变化 | 处理方式 | 必须满足的条件 |
|---|---|---|
| 仅缩小任务或模式集合 | 过滤原记录并重算统计 | 保留的 seed→场景映射、指令、判定和模型配置不变；注明新统计范围 |
| 仅修复汇总公式或展示 | 从原始结果重算报告 | 原始逐回合记录本身可靠；不要把新公式误写成新评测 |
| 判定修改，但原始完整轨迹足以重新判定 | 可考虑离线重判 | 有精确物理状态、仿真时钟及所需完整时间段，且验证重判与在线判定一致；本次旧 Bottle 不满足 |
| 初始化、场景分布、指令、模型 checkpoint 变化，或轨迹因旧判定提前终止 | 重跑受影响回合或任务 | 固定新契约，保留历史结果，避免把不同版本拼成同一正式结果 |
| 仅 commit 不同或文件 hash 不同 | 先检查具体差异 | 不能仅凭 commit 时间判失效，也不能仅凭相同 seed 判兼容 |

当前没有待补跑项。若审计更早的目录，优先检查 Bottle checker、Arm 初始化与 v2 配置、Attribute 初始化，
不要把当前目录已经核对通过的结论直接套到旧目录。评测身份还包括 checkpoint、推理参数、instruction、seed、mode、
场景配置、动作预算及实际任务/评测代码；来源记录缺失时应标为待核实，而非默认可复用。

## 可复查操作与证据边界

以下命令在主仓库根目录执行，只读代码或结果，不启动模型或 simulator：

```bash
git diff 1685b397a97dc6aee55d60ea4980d9cdacfc0597 72d7c36b68d13f7209e0307a8f4e7765cef9740b -- tasks/envs bak/grasp_cube_approach policies
git show ff4ef3f -- tasks/envs/arm_select.py
git show feaae02 -- tasks/envs/attribute_select.py
sha256sum tasks/envs/{bottle_verb,arm_select,attribute_select,pick_diverse_object,stack_sequence,place_relative}.py
```

输出的任务哈希可与本笔记 `source-audit.json` 的 `tasks.*.current_task_sha256` 对照。
未来代码变化后产生不同哈希需要重新解释差异，不应修改本次审计快照来掩盖版本变化。
结果包完整性可用以下命令检查；它只验证发布文件未改变，不能替代回合来源和判定语义核对：

```bash
(cd result/if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks && sha256sum -c SHA256SUMS)
```

本次分析实际完成了逐回合来源及哈希核对、任务差异检查和 Spatial 场景/函数体比较。
没有为写笔记重跑 GPU 评测，也没有新增人工标签。注意以下边界：

- 主仓库当前还有上一轮结果发布文档的未提交改动，审计时没有未提交的任务源码修改；来源判断依据实际文件 hash，不只依据 HEAD。
- 六个现役任务的动作预算在 master 已存在：Bottle 700、Noun/Attribute/Arm/Spatial 各 400、Sequence 1200；本分支没有另改这些预算。Bottle 新增的是预算末判定语义。
- 提速逻辑的增删不是额外的任务成功谓词修复；不同运行环境的耗时也不能直接比较。
- VLAct 从 clean checkpoint 换成 All（clean+random）的重跑是独立的模型版本变化，当前结果已使用 All。
- Hy-VLA coffee-box seed 100052 的历史人工复核问题尚未改判；Noun 源码没变不能证明该问题已修复。
- `operate_stapler`、`operate_tabletop`、`operate_mic_drawer`、`laptop_verb` 的任务源码在本分支未修改；本次没有重新评测它们。
- Grasp-Approach 历史实现保留在 [bak](../../bak/grasp_cube_approach/tasks/envs/grasp_cube_approach.py)，不计入当前六任务分数。

## 笔记存储与同步

本文件位于独立 `notes/` 仓库的 `notes/vibe-coding` 分支，目前仅本地写入，未 commit / push。
以后同步可在主仓库根目录使用 `just vibe-notes-push`；该 recipe 会提交 notes 内全部改动。
当前 notes 还存在其他结果笔记的未提交修改，若只发布本篇，应在 notes 仓库按本目录定向提交，再推送。
