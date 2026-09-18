# Place-Relative：从五模式收缩到三个模式

2026-09-15，视频复核后决定：当前六任务套件中的 `place_relative` 仅保留 **left、right、on_top**。
`front/back` 暂时退出正式计分，原五模式代码、manifest、结果和视频证据保留。
这是观察结果后的评测范围调整（post-hoc），新旧 Spatial/Overall 不能作为同一指标直接比较；
新分数上升不代表模型变强，也没有重跑模型或修改自动 success 标签。

## 观察、证据与判断边界

用户在视频复核中观察到 policies 对 front/back 的行为不符合指令，认为目前模型不能理解这两个方位，
希望先缩小任务范围。以下数字来自原始自动判定，并不等价于人工逐回合标注：

| Policy | Front | Back | 保留 Left | 保留 Right | 保留 Top |
|---|---:|---:|---:|---:|---:|
| X-VLA | 0/20 | 0/20 | 4/20 | 2/20 | 0/20 |
| LingBot-VA | 0/20 | 0/20 | 12/20 | 7/20 | 7/20 |
| LingBot-VLA | 0/20 | 0/20 | 1/20 | 2/20 | 0/20 |
| VLAct All | 1/20 | 0/20 | 11/20 | 7/20 | 1/20 |
| DM05 | 1/20 | 0/20 | 12/20 | 8/20 | 0/20 |
| Hy-VLA | 0/20 | 0/20 | 2/20 | 5/20 | 0/20 |

Back 总计 **0/120**；Front 总计 **2/120**；此次移除 **240 回合：2 次自动成功、238 次失败**。
因此不应描述成 front/back 全部为零。两个自动成功均为 seed **100077**，分别来自 VLAct All、DM05：
`Lift the blue soap and set it in front of the red tea-box`。
这两例保留原 success，尚未据人工复核改判。

共同失败示例取同一场景的 front seed **100007**、back seed **100008**，六个 policies 都失败：
黑色 remotecontrol 相对红色 tea-box 的放置关系。这样可跨 policy 查看同一场景，而不是只挑某个模型的失败。

- [240 回合明细](../bak/place_relative-five-modes/excluded-episodes.csv)：原 block、seed、mode、指令、判定、record 路径与 SHA-256。
- [视频证据索引](../bak/place_relative-five-modes/evidence.json)：全部被排除回合的 video 路径、SHA-256、review query。
- [14 份示例原始 result](../bak/place_relative-five-modes/records/)：12 个共同失败与两个自动成功。
- 原五模式结果与清单仅保留在 Git 历史中，来源校验见[发布溯源说明](release-provenance.md)。

复核页默认隐藏已下线模式；打开“包含已下线的任务 / 模式”后选择 `place_relative`、`front/back`。
也可在运行中的复核页地址后添加 `?episode=vlact/place_relative/100077` 或
`?episode=dm05/place_relative/100077`，直接打开两个例外。示例证据的哈希已与磁盘视频核对。
视频仍保存在 `/Data/robotwin-if/evaluations/if-seven-tasks-v2-wide-20blocks-001/`，无需复制大文件。

决策时检查到复核数据库中没有已保存的 `place_relative` 逐回合标注，因此“无法理解”的依据是用户的
视频观察，而不是已落盘的人工标签统计。低成功率本身无法区分语言理解、物体/相机参照系歧义、
执行误差和 success checker 的问题；此次不宣称已经证明某种根因，也不宣称修复了 checker。
后续若恢复 front/back，应先明确参照系，收集代表性成功/失败人工标签，核对最终物体位姿与判定阈值，
再独立验证 oracle 正反例及模型表现。不要通过反复筛选“效果好的 seed”恢复该模式。

## 代码、seed 与复用契约

当前任务 `ORDER/PHRASES` 仅包含三个方向；旧实现与几何 helper 仅保留在 Git 历史 `833d496`。
[排除回合证据](../bak/place_relative-five-modes/README.md)继续保留供核对评测范围。
保留当前 left/right/on_top 的几何、物体采样、指令模板和 success 判定阈值。

```text
scene_seed = seed // 5                  # 保持不变
left       = 5k
right      = 5k + 1
on_top     = 5k + 4
front/back = 5k + 2, 5k + 3             # 已下线，运行前拒绝
```

不能改为 `% 3` 或 `// 3`，否则旧 seed 会换方向/场景，已有结果无法复用。
当前 block 大小是 3，但 seed stride 仍是 5；`block_offset` 继续表示原 seed slot（0、1、4），
导出中的 `block` 是 manifest 中的顺序编号 0–19。沿用全部 20 个场景，不新增 seed 或替换失败。

新 Spatial flat manifest 使用 **schema_version 2**。schema 1 继续表示旧五模式，用于只读校验；
另外五项 manifest 字节不变。生成器的新 contract schema 为 2，按完整三模式 block 做 oracle 筛选，
旧 generation evidence 可校验，旧 checkpoint 不允许继续生成。
六个 policy 共用的 seed 入口和 bash launcher 都会在模型调用前拒绝 front/back 清单。

## 当前统计口径

每个 policy 的 Spatial 为 **60 回合、20 blocks**；六任务合计 **460 回合**。
全套为 **2760 回合、720 blocks**。场景范围调整保留 left/right/on_top 的原始记录，
不重新推理，不修改自动成功标签。

`Spatial Avg. = (SR_left + SR_right + SR_on_top) / 3`。
`Overall = 六个 Task Avg. 的等权平均`，使用完整精度计算后显示一位小数。

当前成绩只在[最新结果包](../result/robotwin-if-arm-only-v2-20blocks/README.md)展示；
旧范围的汇总表保留在 Git 历史中。当前 seed 清单见[正式 manifest](../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md)。

## 复现与验证

- `python tools/export_seed_modes.py --check` 验证 460 条 seed/mode 导出。
- 当前完整发布校验见[溯源说明](release-provenance.md)；旧 Spatial 发布工具仅保留在 Git 历史中。
- `python tools/summarize_formal_policy_results.py --run-dir outputs/policy-eval/if-seven-tasks-v2-wide-20blocks-001 --output /tmp/spatial3-results.md` 从原始记录重算当前范围，先核对 source SHA/provenance。
- 上一命令加 `--include-archived-modes` 可复现旧六任务五模式指标；再加 `--include-archived-tasks` 可复现旧七任务指标。

验证仅使用 CPU：seed/场景映射、旧 schema 校验、入口拒绝退休模式、报表完整/不完整 block、
复核页范围与标签隔离、发布文件 SHA。没有启动 GPU simulator 或重跑模型；真实物理 rollout 未重复验证。

本次实际验证：90 项单元测试通过（74 项 seed/评测/报表/复核测试 + 16 项 eval step-limit 测试）；
指令模板 17/17、任务清单 51/51 检查通过；新旧 release verifier 及三份结果包的 SHA 校验通过。
浏览器确认默认 2760 回合、Spatial 筛选 360 回合，打开归档后 Spatial 为 600 回合；
VLAct front seed 100077 的历史 success 视频可解码（960×240，14.8 秒），无页面脚本错误。
当前 CPU 复核服务已加载此范围，刷新网页即可使用，人工标签存储路径不变。
