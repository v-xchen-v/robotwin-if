# Attribute Size 6 cm：当前六模型成绩

大块边长从 8 cm 改为 6 cm，小块仍为 4 cm。继续使用原
[Stapler v1 的六份 seed manifest](../../seed-manifests/robotwin-if-press-lift-stapler-v1-20-per-mode/README.md)，不生成新清单。
checkpoint、指令、其他任务设置和成功判据保持原样。

**只有 VLAct 的 Big seed 100174 从失败变为成功**：Attribute 108/160 → 109/160，
Overall 57.4% → 57.5%。其余五模型各 mode、任务平均分和 Overall 均不变。
完整结果仍为 2760 回合、720 blocks；Overall 按六任务等权平均。

- [成绩表](results.md) · [HTML](results.html) · [分模式 CSV](results.csv) · [JSON](results.json)
- [逐回合 CSV](episodes.csv) · [原 8 cm 成绩及 checkpoint 身份](../robotwin-if-press-lift-stapler-v1-20blocks/README.md)
- [尺寸实验与动作现象](../../docs/attribute-size-6cm-ablation.md)
- [Azure 备份校验记录](azure-backup.json) · [下载 / 网页](../../docs/download-results.md)

视频集使用已完成的 240 条 6 cm Size 重测输出，其余 2520 回合直接复用旧输出。
本机运行 `just video-review`，或运行 `just video-review-azure` 按需读取 Azure。
两者展示同一组正式回合。Hy-VLA Noun seed 100052 保留原自动标签。

仓库只保留成绩表、回合索引和 Azure 地址/校验记录。完整视频、动作、观测、资格证据和源码快照
保存在 Azure 的 `opensource-eval-stapler-v2-size6cm-20blocks-20261030` 包中。
`azure-backup.json` 的哈希描述完整远端备份，备份内的历史 manifest/报告快照保持上传时原样，
不要求当前精简目录复制这些文件。
