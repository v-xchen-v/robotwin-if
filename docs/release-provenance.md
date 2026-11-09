# 结果来源与统计边界

当前代码、`seed-manifests/20-blocks/` 与 `result/` 构成同一份六任务交付。
任务设置为 Press/Lift Stapler、Noun、Attribute、Arm、Sequence、Spatial；Attribute Size 为 6 cm / 4 cm。
六份输入 manifest 的 seed 数值和顺序保持不变，不维护版本注册表或 latest 解析。

## 原六模型的评测与复用

原六个公开 checkpoints 共 2760 回合。2026-10-29 在 6 cm 大块设置下重测了全部 240 个 Size 回合；
其余 2520 回合的环境、指令和判据未变化，复用其原始输出。成功与失败均保留。
这不是全部 2760 回合的新一轮运行。

与 8 cm 实验相比，唯一成功标签变化是 VLAct / Big / seed 100174：失败变为成功。
VLAct Overall 从 57.3611% 增至 57.4653%，显示为 57.4 → 57.5；其他五个模型分数不变。
六个模型的新 Size 视频、动作和观测均保留在完整下载包中。
[尺寸实验记录](attribute-size-6cm-ablation.md)保留动作模式分析和逐模型比较。

Checkpoint 身份见 [checkpoints.json](../result/checkpoints.json)。
每条 episode 的记录哈希见 [episodes.csv](../result/episodes.csv)，对应的视频和其他文件由下载包根 `SHA256SUMS` 覆盖。

## 新增三个 WAM 与九模型结果合并

Fast-WAM、Motus、X-WAM 各完成原 manifest 的 460 回合，总计新增 1380 回合，于 2026-11-06 全部完成。
任务定义、seed 数值与顺序、指令、动作预算和成功判据保持原 release 分支的设置。2026-11-09 核查后，`result/` 和新 Azure 包 `robotwin-if-20261109` 扩展为九模型、4140 回合、1080 blocks。
原六模型的分数、逐回合标签与记录哈希逐项保留；原 Azure 包 `robotwin-if-20261030` 及日期 tag 继续可用。

新增回合的 result/index、mode、动作预算、任务汇总和 provenance 已核查一致，证据见 [wam-audit.json](../result/wam-audit.json)。
Fast-WAM / Motus / X-WAM 分别有 10 / 5 / 7 次模型调用前 oracle 资格失败，均保留完整归档并在原 seed 恢复；含最终通过的尝试数每 seed 不超过 8 次。正常 policy failure 不重跑。
跨回合 CuRobo 状态通路已确认，但 oracle 的底层确定性未修复；恢复能力与模型成功率分别记录。
本次最终核查覆盖记录、源文件和归档一致性，未逐帧重解码全量视频或独立重判物理场景。原始运行证据与失败归档位于下载包 `audit/wam/`。

## 资格与初始观测

正式 seeds 按 expert 可执行性选择完整 blocks，不依据模型成败筛选。
Stapler 的 20 对 Press/Lift 通过 expert 和初始 RGB、机器人状态、物体位姿检查。
Size 的 20 对在 6 cm 设置下重新通过 expert；原六模型保存的 120 对初始观测也逐数组一致。

除 Noun 外，同一组对照共享初始画面。原六模型的 2520 份非 Noun 观测构成 960 组对照：
Stapler、Arm、Sequence、Spatial 各 120 组，Attribute 480 对。头部和双腕 RGB、proprio 的不一致组数为零。
Noun Seen/Unseen 属于独立物体池和独立场景，不作 pixel-equal 声明。

仓库保留 [qualification.json](../seed-manifests/20-blocks/qualification.json) 摘要。
完整下载包的 `audit/seed-qualification/` 保留原始资格记录和当时源码；其中旧 Size 快照为 8 cm。
当前 6 cm 的资格与运行证据位于 `audit/size-experiment/`。原始 metadata、schema 和 checker 标识不因目录清理而改写。

## 已知解释边界

- Hy-VLA / Noun seed 100052（coffee-box）的自动标签与用户视频复核有分歧；正式分数保留原始标签，README 演示未选用该回合。
- 某些配对指令的句式不完全相同；pixel-equal 指初始图像和机器人状态，不保证句子仅差一个词。
- Spatial 使用现有几何判据，没有额外的持续稳定时间要求。
- 固定 seed、代码和 checkpoint 有助于复现；渲染、硬件与推理随机性仍可能影响逐回合表现。

[完整结果下载及校验](download-results.md) · [当前使用入口](quickstart.md)

## Arm 配置命名

当前配置为 `demo_clean_arm_select.yml`，原 `release-20261030` 使用 `demo_clean_arm_select_v3.yml`。
本次配置改名同步更新了 Arm manifest 的 `task_config`、seed-mode 导出与校验哈希；seed 数值与顺序未改，其他五份输入保持原字节。
任务只保留当前 5 cm 方块场景，删除旧长方体场景分支和 YAML 的场景版本选择字段。
尺寸、位置/yaw 采样顺序、抓取参数、动作预算与成功判据保持一致；Arm 配对指令直接按 `seed // 2` 选择模板。
旧版本选择参数会明确报错，避免过期配置被静默接受。

2026-11-02 完成等价检查：40 个正式 seeds 的三路初始 RGB、proprio、关节状态和物体位姿逐数组一致，
40 条指令与场景/抓取参数一致；左右臂各自的直接正确抓取和先错后对共 4 个物理案例均通过预期判定。
181 项通用 CPU 测试、16 项 Arm 测试，以及 bridge、采集和六模型评测入口预览通过。
清理前后连跑到 seed `500007` 时均出现 expert 规划失败，分别冷启动该 seed 后通过；失败记录保留，seed 未替换。

上述 11 月 2 日配置整理保留了原六模型真实评测时的配置名、原始记录和哈希，未重跑模型或重新上传推理输出。
11 月 9 日的九模型合并继续保留这些原始记录；完整原始代码、配置和结果仍可从冻结的 tag 与下载包定位。
