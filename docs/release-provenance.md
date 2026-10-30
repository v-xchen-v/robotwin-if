# 结果来源与统计边界

当前代码、`seed-manifests/20-blocks/` 与 `result/` 构成同一份六任务交付。
任务设置为 Press/Lift Stapler、Noun、Attribute、Arm、Sequence、Spatial；Attribute Size 为 6 cm / 4 cm。
六份输入 manifest 保持原字节，不维护版本注册表或 latest 解析。

## 评测与复用

六个公开 checkpoints 共 2760 回合。2026-10-29 在 6 cm 大块设置下重测了全部 240 个 Size 回合；
其余 2520 回合的环境、指令和判据未变化，复用其原始输出。成功与失败均保留。
这不是全部 2760 回合的新一轮运行。

与 8 cm 实验相比，唯一成功标签变化是 VLAct / Big / seed 100174：失败变为成功。
VLAct Overall 从 57.3611% 增至 57.4653%，显示为 57.4 → 57.5；其他五个模型分数不变。
六个模型的新 Size 视频、动作和观测均保留在完整下载包中。
[尺寸实验记录](attribute-size-6cm-ablation.md)保留动作模式分析和逐模型比较。

Checkpoint 身份见 [checkpoints.json](../result/checkpoints.json)。
每条 episode 的记录哈希见 [episodes.csv](../result/episodes.csv)，对应的视频和其他文件由下载包根 `SHA256SUMS` 覆盖。

## 资格与初始观测

正式 seeds 按 expert 可执行性选择完整 blocks，不依据模型成败筛选。
Stapler 的 20 对 Press/Lift 通过 expert 和初始 RGB、机器人状态、物体位姿检查。
Size 的 20 对在 6 cm 设置下重新通过 expert；六模型保存的 120 对初始观测也逐数组一致。

除 Noun 外，同一组对照共享初始画面。完整结果的 2520 份非 Noun 观测构成 960 组对照：
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
