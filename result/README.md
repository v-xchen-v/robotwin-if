# 正式评测结果

不同任务范围分别保存报表、逐回合计数、seed manifest 和来源证据。

| 版本 | 覆盖范围 | 完成回合 | 入口 |
|---|---|---:|---|
| 当前：六任务，Spatial 三模式，Bottle v6 回合末判定 | 6 policies × 6 tasks × 20 blocks | 2760/2760 | [结果说明](if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/README.md) · [HTML](if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/results.html) · [Markdown](if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/results.md) |
| 历史：IF-Ext v2，六任务，Spatial 三模式，旧 Bottle 判定 | 6 policies × 6 tasks × 20 blocks | 2760/2760 | [结果说明](if-ext-v2-six-tasks-spatial3-20blocks/README.md) · [HTML](if-ext-v2-six-tasks-spatial3-20blocks/results.html) · [Markdown](if-ext-v2-six-tasks-spatial3-20blocks/results.md) |
| 历史：IF-Ext v2，六任务，Spatial 五模式，20 blocks | 6 policies × 6 tasks × 20 blocks | 3000/3000 | [结果说明](if-ext-v2-six-tasks-20blocks/README.md) · [HTML](if-ext-v2-six-tasks-20blocks/results.html) · [Markdown](if-ext-v2-six-tasks-20blocks/results.md) |
| 历史：IF-Ext v2 wide，七任务，20 blocks | 6 policies × 7 tasks × 20 blocks | 3240/3240 | [结果说明](if-ext-v2-wide-20blocks/README.md) · [HTML](if-ext-v2-wide-20blocks/results.html) · [Markdown](if-ext-v2-wide-20blocks/results.md) |

最新结果于 **2026-09-15 22:44 UTC** 完成校验：Bottle-Verb 按 v6 完成 **240 回合**（含 2 个已验证的 X-VLA v6 回合，本队列补跑 238 回合），其他五项复用 **2520 回合**。
全套完成 **720/720 blocks**；其他任务的原始结果哈希和统计保持一致。
pick 完整执行 700 个动作后判断末尾姿态保持与旋转摇晃，允许平移。该判定变化不能解释为模型能力提升，详见 [判定与结果说明](../docs/bottle-verb-pick-hold.md)。

2026-09-15 暂时下线 Grasp-Approach 时，六任务历史结果从已完成的七任务运行中提取；旧版本独立保留。
当前 `Overall` 按六个任务的 `Task Avg.` 等权平均；历史七任务版本按七项计算，六任务五模式版本的 Spatial 范围也不同。
每个 `Task Avg.` 对 modes 等权，使用完整精度计算后显示一位小数。

逐回合记录保留成功和已完成的 policy failure。视频、动作轨迹等原始产物的位置见各版本 README。

Spatial 三模式版统一排除 front/back（240 回合，其中 2 次自动成功），不改写任何原始判定。
详见 [决策与证据](../docs/place-relative-spatial3.md)。新旧 Spatial/Overall 口径不同。
