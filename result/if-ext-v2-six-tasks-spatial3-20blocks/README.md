# IF-Ext v2：六任务、Spatial 三模式、20 blocks

视频复核后，Spatial 仅计 left/right/on_top，保留原 20 个场景。
每个 policy **460/460 回合、120/120 blocks**；全套 **2760/2760 回合、720/720 blocks**。
共有 **1259 次成功、1501 次已完成的 policy failure**。

- [HTML 结果表](results.html) · [Markdown](results.md)
- [逐回合 CSV](episodes.csv) · [分模式 CSV](results.csv)
- [完整统计快照](results.json) · [来源与投影说明](provenance.json)
- [Checkpoint 版本](checkpoints.json) · [当前 manifest](../../seed-manifests/if-ext-v2-six-tasks-spatial3-20-per-mode/README.md)
- [决策、240 个排除回合与证据](../../docs/place-relative-spatial3.md)

不重跑、不改判、不替换 seed。front/back 统一排除 240 回合，其中 2 个原自动成功；
其余回合与源结果逐行相同，原记录 SHA/provenance 已核对。
Spatial Avg. 对三个模式等权；Overall 对六个 Task Avg. 等权，不是 460 个回合直接合并。
这是评测后的范围调整，新旧指标不可直接视作性能提升。

原 [六任务五模式包](../if-ext-v2-six-tasks-20blocks/README.md) 和
[七任务包](../if-ext-v2-wide-20blocks/README.md) 未改写。
X-VLA 为 clean-only checkpoint，其余五个为 clean+random；无公开 X-VLA clean+random checkpoint。
Hy-VLA pick_diverse_object seed 100052 的 coffee-box 自动成功仍待人工复核，本次未修改。

视频和动作保存在原运行目录：
`/Data/robotwin-if/evaluations/if-seven-tasks-v2-wide-20blocks-001/<policy>/<task>/`。
复核页打开“包含已下线的任务 / 模式”仍可查看 front/back。

本目录内执行 `sha256sum -c SHA256SUMS` 可校验。
