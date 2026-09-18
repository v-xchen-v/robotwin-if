# 正式评测结果

不同任务范围分别保存报表、逐回合计数、seed manifest 和来源证据。

**2026-09-18 Arm 判据修正：** 代码已禁止“先用错误臂拿起，再换指定臂”的成功判定。
下列已发布包中的 Arm/Overall 仍按旧终态规则统计，尚未按新规则重跑，原始文件与计数保留。
见[规则与验证说明](../docs/arm-select-target-arm-only.md)。

最新结果保存在 [`robotwin-if-attribute-v2-20blocks/`](robotwin-if-attribute-v2-20blocks/README.md)：
Attribute-Select 按 `target-only-lift-v2` 重跑六个 policies 的 960 回合，其余五任务复用 cube-v3 的 1800 回合。
[HTML 报表](robotwin-if-attribute-v2-20blocks/results.html) · [分模式 CSV](robotwin-if-attribute-v2-20blocks/results.csv) ·
[逐回合 CSV](robotwin-if-attribute-v2-20blocks/episodes.csv) · [结果 JSON](robotwin-if-attribute-v2-20blocks/results.json) ·
[校验证据](robotwin-if-attribute-v2-20blocks/validation.json) · [Attribute 新旧逐回合比较](robotwin-if-attribute-v2-20blocks/attribute-comparison.csv)。

**2026-09-17 判据修正：** 新结果禁止“先抓错再抓对”的假成功。新 Attribute/Overall 已重新评测；
其余旧包中的 Attribute 使用历史判据，原始字节与计数保持不变。
见[新规则与回放证据](../docs/attribute-select-target-only.md)和[三个案例的回放核对包](attribute-select-target-only-v2-review/README.md)。

| 版本 | 覆盖范围 | 完成回合 | 入口 |
|---|---|---:|---|
| 当前：RoboTwin-IF Attribute-v2，保留 Arm cube-v3 / Bottle v6 / Spatial 三模式 | 6 policies × 6 tasks × 20 blocks | 2760/2760 | [结果说明](robotwin-if-attribute-v2-20blocks/README.md) · [HTML](robotwin-if-attribute-v2-20blocks/results.html) · [Markdown](robotwin-if-attribute-v2-20blocks/results.md) |
| 上一版：RoboTwin-IF cube-v3，保留 Bottle v6 / Spatial 三模式 | 6 policies × 6 tasks × 20 blocks | 2760/2760 | [结果说明](robotwin-if-cube-v3-20blocks/README.md) · [HTML](robotwin-if-cube-v3-20blocks/results.html) · [Markdown](robotwin-if-cube-v3-20blocks/results.md) |
| 历史：六任务，Spatial 三模式，Bottle v6 回合末判定 | 6 policies × 6 tasks × 20 blocks | 2760/2760 | [结果说明](if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/README.md) · [HTML](if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/results.html) · [Markdown](if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/results.md) |
| 历史：IF-Ext v2，六任务，Spatial 三模式，旧 Bottle 判定 | 6 policies × 6 tasks × 20 blocks | 2760/2760 | [结果说明](if-ext-v2-six-tasks-spatial3-20blocks/README.md) · [HTML](if-ext-v2-six-tasks-spatial3-20blocks/results.html) · [Markdown](if-ext-v2-six-tasks-spatial3-20blocks/results.md) |
| 历史：IF-Ext v2，六任务，Spatial 五模式，20 blocks | 6 policies × 6 tasks × 20 blocks | 3000/3000 | [结果说明](if-ext-v2-six-tasks-20blocks/README.md) · [HTML](if-ext-v2-six-tasks-20blocks/results.html) · [Markdown](if-ext-v2-six-tasks-20blocks/results.md) |
| 历史：IF-Ext v2 wide，七任务，20 blocks | 6 policies × 7 tasks × 20 blocks | 3240/3240 | [结果说明](if-ext-v2-wide-20blocks/README.md) · [HTML](if-ext-v2-wide-20blocks/results.html) · [Markdown](if-ext-v2-wide-20blocks/results.md) |

当前 Attribute-v2 于 **2026-09-17 22:39 UTC** 完成校验，**960 新回合 + 1800 复用回合，720/720 blocks**。
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
