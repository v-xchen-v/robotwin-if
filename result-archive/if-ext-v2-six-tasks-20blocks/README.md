# IF-Ext v2：六任务，20 blocks

2026-09-15 暂时下线 Grasp-Approach 后，按当前六任务范围从已完成的七任务运行中提取结果。
没有重跑模型、替换 seeds 或筛选同一任务内的成功/失败。六个 policies 均已完成
**500/500 回合、120/120 blocks**；全套 **3000/3000 回合、720/720 blocks**。

- [HTML 结果表](results.html) · [Markdown](results.md)
- [逐回合 CSV](episodes.csv) · [分模式 CSV](results.csv)
- [完整统计快照](results.json) · [来源说明](provenance.json)
- [六任务 seed 清单](../../seed-manifests/if-ext-v2-six-tasks-20-per-mode/README.md)

共有 1261 个成功、1739 个已完成的 policy failure。每个任务的 `Task Avg.` 对 modes 等权，
`Overall` 对本版六个 `Task Avg.` 等权；不能与原七任务 Overall 当作同一个指标比较。
`results.json` 同时保留原七任务 source summary，以便追溯；表格和顶层 summary 仅统计当前六项。

原七任务包位于 [`../if-ext-v2-wide-20blocks/`](../if-ext-v2-wide-20blocks/README.md)，未改写。
本目录的 `episodes.csv` 与六份 manifest 均来自该包；checkpoint 身份沿用原版本，VLAct 为 All。
生成时核对原始结果文件 SHA-256 与 provenance，并确认保留任务的每项计数/分数没有变化、
显式七任务汇总仍复现原始 Overall。视频与动作轨迹仍在原运行目录，无需再复制：

`/Data/robotwin-if/evaluations/if-seven-tasks-v2-wide-20blocks-001/<policy>/<task>/`

本包文件可用 `sha256sum -c SHA256SUMS` 校验。
