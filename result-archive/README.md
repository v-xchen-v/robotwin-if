# 历史结果与判据验证证据

当前完整成绩见 [Arm-only-v2 结果包](../result/robotwin-if-arm-only-v2-20blocks/README.md)，
当前入口及使用方法见 [result/](../result/README.md)。

2026-09-18 将 **6 个历史成绩包 + 2 份判据验证证据**从 `result/` 原样归档至本目录，
共 **119 个原文件**，逐字节保留。各包自己的 `SHA256SUMS`、成绩、逐回合记录、
来源、seed manifest 和校验记录均未改写；原始仿真视频与动作目录未迁移。
旧路径保留相对软链接，兼容本地结果引用和 seed release 中绑定的路径及哈希。
归档与原目录处于相同层级，包内的相对文件、文档和图片链接保持可用。
在代码托管网站浏览旧版本时，请使用本索引中的实体目录链接。

## 历史成绩

归档包保留当时的任务范围和成功判据；README 中的“当前”“尚未重跑”属于当时的发布记录。
当前状态以 [最新版](../result/robotwin-if-arm-only-v2-20blocks/README.md) 为准。

| 版本 | 覆盖范围 | 完成回合 | 入口 |
|---|---|---:|---|
| 上一版：RoboTwin-IF Attribute-v2，保留 Arm cube-v3 / Bottle v6 / Spatial 三模式 | 6 policies × 6 tasks × 20 blocks | 2760/2760 | [结果说明](robotwin-if-attribute-v2-20blocks/README.md) · [HTML](robotwin-if-attribute-v2-20blocks/results.html) · [Markdown](robotwin-if-attribute-v2-20blocks/results.md) |
| 历史：RoboTwin-IF cube-v3，保留 Bottle v6 / Spatial 三模式 | 6 policies × 6 tasks × 20 blocks | 2760/2760 | [结果说明](robotwin-if-cube-v3-20blocks/README.md) · [HTML](robotwin-if-cube-v3-20blocks/results.html) · [Markdown](robotwin-if-cube-v3-20blocks/results.md) |
| 历史：六任务，Spatial 三模式，Bottle v6 回合末判定 | 6 policies × 6 tasks × 20 blocks | 2760/2760 | [结果说明](if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/README.md) · [HTML](if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/results.html) · [Markdown](if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/results.md) |
| 历史：IF-Ext v2，六任务，Spatial 三模式，旧 Bottle 判定 | 6 policies × 6 tasks × 20 blocks | 2760/2760 | [结果说明](if-ext-v2-six-tasks-spatial3-20blocks/README.md) · [HTML](if-ext-v2-six-tasks-spatial3-20blocks/results.html) · [Markdown](if-ext-v2-six-tasks-spatial3-20blocks/results.md) |
| 历史：IF-Ext v2，六任务，Spatial 五模式，20 blocks | 6 policies × 6 tasks × 20 blocks | 3000/3000 | [结果说明](if-ext-v2-six-tasks-20blocks/README.md) · [HTML](if-ext-v2-six-tasks-20blocks/results.html) · [Markdown](if-ext-v2-six-tasks-20blocks/results.md) |
| 历史：IF-Ext v2 wide，七任务，20 blocks | 6 policies × 7 tasks × 20 blocks | 3240/3240 | [结果说明](if-ext-v2-wide-20blocks/README.md) · [HTML](if-ext-v2-wide-20blocks/results.html) · [Markdown](if-ext-v2-wide-20blocks/results.md) |

## 当前判据的验证证据

以下两包是诊断与控制实验，不是六任务成绩，也不计入成功率。归档仅调整存放位置，
它们仍被当前 Arm/Attribute 判据及 release 校验引用，不能作为无用旧成绩删除。

| 证据包 | 用途 |
|---|---|
| [Arm target-arm-only-v2](arm-select-target-arm-only-v2-review/README.md) | 四组真实仿真，验证指定臂直接抓取及“错误臂后换指定臂”的判定 |
| [Attribute target-only-v2](attribute-select-target-only-v2-review/README.md) | 三个原动作回放，验证错误物体抬升历史及正确抓取对照 |

## 归档校验

```bash
(cd result-archive && sha256sum --check --quiet SHA256SUMS)
```

该清单覆盖全部 119 个原文件，包括各包原有的 `SHA256SUMS`。
也可进入任意包单独执行 `sha256sum --check SHA256SUMS`。
这些检查不需要模型、GPU 或原机 `/Data` 目录；原始视频与动作的位置见各包 README。

迁移验证：22 项相关 CPU 测试通过；全部 9 个结果/验证包的原 `SHA256SUMS` 通过，
当前结果的 19 个文件及归档的 119 个文件与迁移前逐字节一致。
seed release 中绑定的结果路径与哈希仍匹配，历史 Spatial 三模式校验经兼容入口通过。

## 版本记录

历史 Attribute-v2 于 **2026-09-17 22:39 UTC** 完成校验，**960 新回合 + 1800 复用回合，720/720 blocks**。
五个复用任务的原始记录哈希、逐回合字段与统计完全一致；新 Attribute 初始观测与 cube-v3 一致，checkpoint 和推理参数保持原版。
1 次推理前 oracle 初始化失败均使用原 seed 恢复；[重试审计](robotwin-if-attribute-v2-20blocks/oracle-setup-retries.json)随包保留。

上一版 cube-v3 结果于 **2026-09-16 17:59 UTC** 完成校验：Arm-Select 重新运行 **240 回合**，其余五任务逐字节复用 **2520 回合**，合计 **720/720 blocks**。
五个复用任务的记录哈希与统计完全一致，checkpoint 和推理参数保持原版本；详见[来源证明](robotwin-if-cube-v3-20blocks/provenance.json)。
4 次推理前 oracle 初始化失败均用原 seed 在新 simulator 中恢复，policy 回合没有重跑；[重试记录](robotwin-if-cube-v3-20blocks/oracle-setup-retries.json)随包保留。

历史 Bottle-v6 结果于 **2026-09-15 22:44 UTC** 完成校验：Bottle-Verb 按 v6 完成 **240 回合**（含 2 个已验证的 X-VLA v6 回合，本队列补跑 238 回合），其他五项复用 **2520 回合**。
全套完成 **720/720 blocks**；其他任务的原始结果哈希和统计保持一致。
pick 完整执行 700 个动作后判断末尾姿态保持与旋转摇晃，允许平移。该判定变化不能解释为模型能力提升，详见 [判定与结果说明](../docs/bottle-verb-pick-hold.md)。

2026-09-15 暂时下线 Grasp-Approach 时，六任务历史结果从已完成的七任务运行中提取；旧版本独立保留。
当前 `Overall` 按六个任务的 `Task Avg.` 等权平均；历史七任务版本按七项计算，六任务五模式版本的 Spatial 范围也不同。
每个 `Task Avg.` 对 modes 等权，使用完整精度计算后显示一位小数。

逐回合记录保留成功和已完成的 policy failure。视频、动作轨迹等原始产物的位置见各版本 README。

Spatial 三模式版统一排除 front/back（240 回合，其中 2 次自动成功），不改写任何原始判定。
详见 [决策与证据](../docs/place-relative-spatial3.md)。新旧 Spatial/Overall 口径不同。
