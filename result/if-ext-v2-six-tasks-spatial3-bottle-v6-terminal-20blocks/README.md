# 六任务、Spatial 三模式、Bottle v6 回合末判定，20 blocks

六个 policy 均完成 20 blocks 的 Bottle-Verb v6 重测，共 240 回合：保留已验证的 2 个 X-VLA v6 回合，本队列补跑 238 回合；其他五项复用 2520 个原始结果。
全套完成 **2760/2760 回合、720/720 blocks**。原 seed、checkpoint、推理参数与其他任务结果保持一致。
正式校验完成时间：**2026-09-15 22:44 UTC**；本结果包的 Markdown / HTML 与仓库 README 同步更新。
本次改变成功判定，不能将与旧分数的差异视作模型能力提升。

| Policy | Pick 成功 | Shake 成功 | Bottle 成功 | 完成 blocks | 六任务 Overall (%) |
|---|---:|---:|---:|---:|---:|
| X-VLA | 0/20 | 20/20 | 20/40 | 20/20 | 37.1 |
| LingBot-VA | 0/20 | 20/20 | 20/40 | 20/20 | 60.9 |
| LingBot-VLA | 0/20 | 20/20 | 20/40 | 20/20 | 32.5 |
| VLAct All | 16/20 | 20/20 | 36/40 | 20/20 | 47.9 |
| DM05 | 20/20 | 20/20 | 40/40 | 20/20 | 61.8 |
| Hy-VLA | 0/20 | 20/20 | 20/40 | 20/20 | 35.2 |

- [HTML](results.html) · [Markdown](results.md) · [分模式 CSV](results.csv) · [逐回合 CSV](episodes.csv)
- [统计快照](results.json) · [来源](provenance.json) · [正式校验](validation.json)
- [Checkpoint](checkpoints.json) · [运行计划与判定参数](plan.json)
- [Bottle 判定说明](../../docs/bottle-verb-pick-hold.md) · [旧判定结果](../if-ext-v2-six-tasks-spatial3-20blocks/README.md)

判定版本 `relative-lift-hold-v6-terminal`：pick 完整执行 700 个动作后裁决。允许平移，末尾需保持抬升至少 3 cm、连续 3 秒旋转稳定（10° 姿态容差）；保持段最近三秒累计转角超过 135°，或首次抬升后同一世界轴出现至少两次达到 10° 的旋转反向，均锁定为摇晃，之后静止也不能恢复 pick 成功。
shake 仍使用原累计纵向位移规则。Overall 对六个任务均值等权；Spatial 仅含 left/right/on_top。
X-VLA 为 clean checkpoint，其余五个为 clean+random。Hy-VLA coffee-box 的历史人工复核问题未改判。

原始视频及动作目录：`/Data/robotwin-if/evaluations/if-six-tasks-spatial3-bottle-v6-terminal-20blocks-001/<policy>/<task>/`。
复核：`python tools/policy-video-review/server.py --run-dir /Data/robotwin-if/evaluations/if-six-tasks-spatial3-bottle-v6-terminal-20blocks-001`。
本目录内执行 `sha256sum -c SHA256SUMS` 可校验。
