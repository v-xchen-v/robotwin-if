# 三模型六任务完整结果

最后核查：2026-11-09 02:17 UTC。沿用首次结果记录，不另建同用途文档。

## 后续发布：2026-11-09 03:00 UTC

用户随后要求合并到 release 并将评测结果合并到 Azure。代码已合并并推送至 `release-20261030`，发布提交为 `777eff4`。当前主项目 `result/` 包含九模型 4140 回合、1080 blocks；原六模型记录与成绩逐项保留。

新备份地址：<https://eaidatashare.blob.core.windows.net/xichen/robotwin-if/results/robotwin-if-20261109>。68605 个文件、8940269840 字节全部通过远端大小/MD5 校验及 SHA256SUMS 下载比对；清单 SHA-256 为 `2b2ccc4ac7a9cd3c9832d9e068c1b3ba7770d39eaf7441198205f315d23d5fb0`。默认 Azure 视频入口已切换九模型；旧包与日期 tag 保留。

[当前结果包](https://github.com/v-xchen-v/robotwin-if/blob/release-20261030/result/README.md) · [上传与浏览验证记录](https://github.com/v-xchen-v/robotwin-if/blob/release-20261030/result/azure-backup.json)。以下 02:17 UTC 审计内容保留当时范围；该时刻尚未更新原六模型发布目录，之后按此次用户授权完成九模型合并。


## 最终结果

三模型均完整覆盖原 `seed-manifests/20-blocks`：各 460 回合，总计 **1380/1380**，18 个 task-policy 组合全部完成。Fast-WAM / X-WAM 分别于 11 月 5 日 17:42:30 / 19:23:37 UTC 完成；Motus 于 **11 月 6 日 20:21:04 UTC** 完成。11 月 9 日现场核查时评测进程均已退出，两张 GPU 显存占用仅 18 / 17 MiB。

| 任务 | Fast-WAM | Motus | X-WAM |
| --- | ---: | ---: | ---: |
| Press/Lift | 95.00%（38/40） | 92.50%（37/40） | 85.00%（34/40） |
| Pick | 65.00%（26/40） | 65.00%（26/40） | 72.50%（29/40） |
| Attribute | 56.25%（90/160） | 52.50%（84/160） | 50.625%（81/160） |
| Arm | 47.50%（19/40） | 65.00%（26/40） | 10.00%（4/40） |
| Sequence | 8.3333%（10/120） | 6.6667%（8/120） | 5.8333%（7/120） |
| Place | 38.3333%（23/60） | 36.6667%（22/60） | 30.00%（18/60） |
| **Overall** | **51.7361%** | **53.0556%** | **42.3264%** |

Overall 为六任务分数等权平均，各任务先按 mode 等权平均；本次每个 mode 都有 20 个 seed。它不是 460 个回合合并后的成功率。Motus 在这三模型中 Overall 最高，比 Fast-WAM 高约 1.32 个百分点；这里仅报告本次固定清单的实测差值，不推断统计显著性。三模型 Sequence 都较弱，Motus 的 8 个成功全部来自默认 RGB 顺序，其余五个顺序均为 0/20。

## 最终审计与证据

运行根目录：`/Data/robotwin-if/evaluations/wam-full-20261104/`。

- [最终 HTML 报告](/Data/robotwin-if/evaluations/wam-full-20261104/progress.html)；同目录 `progress.json` / `.csv` / `.md` 保留精确分数、每个 mode 的计数与纳入的 seeds。
- [最终审计 JSON](/Data/robotwin-if/evaluations/wam-full-20261104/final-audit-20261109.json)：1380 个 result JSON 的哈希、六任务 manifests、分数独立重算、归档清单及核查边界。
- 可复核脚本：`finalization-20261109/audit-wam-full-20261109.py`；刷新前的状态和四种报告保存在 `finalization-20261109/pre-refresh/`。

核查通过：18 个组合逐项匹配原 manifest 的顺序和 mode，无缺失、替换、重复或残留 error；result 与 JSONL 一致，所有动作预算正确，任务 summaries 和每 mode 的 20 条计数一致。1055 个恢复 worker 的 provenance 标记及其引用的 24 个 worker metadata 通过哈希检查；最初 X-WAM 的 325 条来自原 evaluator，没有后加恢复标记。1380 条结果均有非空 requests、动作归档、初始观测、视频及日志文件。

原始 source-snapshot 的 79 个文件全部通过哈希校验，当前 checkout 78 个仍一致；唯一变化是 `policies/xwam/README.md` 补记此前真实 pilot。排除 Markdown 与 seed-manifests 后的 62 个源码/配置/依赖文件全部一致；manifest 另行验证。此前已审计的 Fast-WAM/X-WAM 920 条结果，以及并行前的 590 条结果，哈希均未变化。

三模型共 **22 次 pre-policy oracle 错误**：Fast-WAM 10、X-WAM 7、Motus 5。Motus 的五次分别是 Arm/500007、Sequence/100113、Sequence/100163、Place/100030、Place/100046，各一次；它的 Sequence/100065 一次通过 oracle，模型正常失败。所有错误均满足 instruction=null、actions=0、chunks=0、requests=[]，归档哈希完整，最终同 seed 已有正常 policy 结果。每 seed 连同最终通过均未超过 8 次尝试，正常 policy failure 保留。该恢复机制完成本批评测，未修复或证明 oracle 底层确定性。

发现并修正最后一条完成后的报告刷新滞后：coordinator 退出分支将各 lane 设为完成，但总计仍来自前一次 30 秒快照的 1379。实际已保存 1380 条结果；本次经 `snapshot()` 重新核查后刷新四种报告，将 `batch-status.json` 总计改为 1380，并记录刷新时间。原 `finished_at` 与最后 heartbeat 保留，未重跑 episode 或修改结果。

本轮审计覆盖记录和归档一致性；没有逐帧解码全部视频、重新检查全部动作数组数值或独立重判物理场景。原有 pilot 和并行短跑的详细检查仍保留。原有六模型正式 `result/` 包、`tools/verify_benchmark.py` 未改动，没有提交或推送。

## 历史快照：2026-11-06 01:37 UTC

Fast-WAM 于 11 月 5 日 17:42:30 UTC 完成 460/460，X-WAM 于 19:23:37 UTC 完成 460/460。两者都覆盖 `seed-manifests/20-blocks` 的六任务。Motus 随后自动启动，11 月 6 日 01:37 UTC 快照为 245/460，正在 Arm；它的完整 Overall 尚未产生。该快照共 1165/1380 个有效回合，原三模型全量目标未完成。

| 任务 | Fast-WAM 成功数 / 回合 | 分数 | X-WAM 成功数 / 回合 | 分数 |
| --- | --- | --- | --- | --- |
| Press/Lift | 38/40 | 95.00% | 34/40 | 85.00% |
| Pick | 26/40 | 65.00% | 29/40 | 72.50% |
| Attribute | 90/160 | 56.25% | 81/160 | 50.625% |
| Arm | 19/40 | 47.50% | 4/40 | 10.00% |
| Sequence | 10/120 | 8.3333% | 7/120 | 5.8333% |
| Place | 23/60 | 38.3333% | 18/60 | 30.00% |
| **Overall** | **460 回合完整** | **51.7361%** | **460 回合完整** | **42.3264%** |

Overall 沿用项目定义：先对每个 task 的 mode 成功率等权平均，再对六个 task 等权平均。各 mode 均有 20 个 seed，故本次 task 分数也等于该 task 的成功回合比例。Overall 不是把 460 个回合直接合并的成功率。

Motus 当前完成的三个任务：Press/Lift 37/40（92.5%）、Pick 26/40（65%）、Attribute 84/160（52.5%）。Arm/Sequence/Place 未全部完成，不给出 Motus Overall。实时进度以运行根目录 `batch-status.json` / `progress.json` 为准。

### 当时的结果核查

运行根目录：`/Data/robotwin-if/evaluations/wam-full-20261104/`。11 月 6 日新增证据：`completed-models-audit-20261106.json`，保存两模型全部 920 个结果 JSON 的 SHA-256、逐任务 manifest SHA-256、计数、Overall 与错误归档清单。

本轮检查通过：

- 12 个 task-policy 组合各自完整覆盖原 manifest，seed 顺序和 mode 匹配，没有漏项、替换或重复；索引与逐回合 result JSON 一致。
- 920 个有效回合均 oracle 通过，status 为正常 success/failure，动作数在预算内、chunk 数非零；summary 计数和完成标志一致。
- 当前 64 个原始运行源码/配置文件的哈希与首次运行快照一致；model/task/evaluator 实现没有因恢复或并行切换而改变。
- 590 份并行切换前的正常结果哈希仍逐项一致。
- 两模型共 17 份 oracle 错误档案均为模型调用前失败：instruction=null、actions=0、chunks=0、requests=[]；归档文件哈希完整，最终同 seed 已有 oracle 通过的正常 policy 结果。
- 按六任务定义独立重算的 Overall 与 `tools/summarize_formal_policy_results.py` 的汇总一致。

本轮是 seed、结果、源文件与归档的一致性审计；未逐帧重解码全量视频，也未用独立物理仿真重新判分。先前真实 pilot 与并行短跑的动作、图像和请求链路核验仍保留。原有六模型正式 `result/` 包和 `tools/verify_benchmark.py` 未改动，本次新结果仍在独立运行目录。

### 当时的恢复与资源运行边界

Fast-WAM 累计 10 次 oracle 失败：Arm/500007 1 次、Sequence/100065 6 次、Sequence/100083 1 次、Place/100046 2 次。X-WAM 累计 7 次：Sequence/100065 5 次、Place/100030 2 次。所有错误均归档并在相同 seed 恢复，不计作 policy failure；所有正常 policy failure 保留、不重跑。没有超出统一的每 seed 累计 8 次尝试上限。

这进一步证明 oracle 波动也会发生在 qpos 模型：Fast-WAM 的 Sequence/100065 也连续失败 6 次后通过。新进程恢复保证了本批继续推进，但不是底层确定性修复。

Fast-WAM/X-WAM 并行完成后已停止各自服务，Motus 当前采用 GPU 1 模型、GPU 0 仿真。01:37 UTC 的 Motus 显存采样约 41.1 GiB，仿真约 5.5 GiB，进程和最新动作日志正常；至该快照 Motus 无 oracle 错误。
