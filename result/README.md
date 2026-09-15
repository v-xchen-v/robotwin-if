# 正式评测结果

不同任务范围分别保存报表、逐回合计数、seed manifest 和来源证据。

| 版本 | 覆盖范围 | 完成回合 | 入口 |
|---|---|---:|---|
| 当前：IF-Ext v2，六任务，20 blocks | 6 policies × 6 tasks × 20 blocks | 3000/3000 | [结果说明](if-ext-v2-six-tasks-20blocks/README.md) · [HTML](if-ext-v2-six-tasks-20blocks/results.html) · [Markdown](if-ext-v2-six-tasks-20blocks/results.md) |
| 历史：IF-Ext v2 wide，七任务，20 blocks | 6 policies × 7 tasks × 20 blocks | 3240/3240 | [结果说明](if-ext-v2-wide-20blocks/README.md) · [HTML](if-ext-v2-wide-20blocks/results.html) · [Markdown](if-ext-v2-wide-20blocks/results.md) |

2026-09-15 暂时下线 Grasp-Approach，六任务结果从已完成的七任务运行中提取，没有重跑或改写旧结果。
当前 `Overall` 按六个任务的 `Task Avg.` 等权平均；历史版本按七项计算，两者的评测范围不同。
每个 `Task Avg.` 对 modes 等权，使用完整精度计算后显示一位小数。

逐回合记录保留成功和已完成的 policy failure。视频、动作轨迹等原始产物的位置见各版本 README。
