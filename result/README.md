# 评测结果

**当前：[Attribute Size 6 cm 的完整成绩](robotwin-if-press-lift-stapler-v2-size6cm-20blocks/README.md)**。
仍为六模型 × 六任务 × 每任务 20 blocks，共 2760 回合、720 blocks。

相对原 8 cm 结果，正式成功标签只有一处变化：VLAct 的 Big seed `100174` 失败 → 成功，
Attribute 从 108/160 到 109/160，Overall 从 57.4% 到 57.5%。其他五模型的成绩数值不变。

- [当前分模式成绩](robotwin-if-press-lift-stapler-v2-size6cm-20blocks/results.md) · [HTML](robotwin-if-press-lift-stapler-v2-size6cm-20blocks/results.html)
- [当前逐回合 CSV](robotwin-if-press-lift-stapler-v2-size6cm-20blocks/episodes.csv)
- [原 8 cm 完整结果](robotwin-if-press-lift-stapler-v1-20blocks/README.md)
- [Azure 下载与网页查看](../docs/download-results.md)

继续使用原 [Stapler v1 seed manifest](../seed-manifests/robotwin-if-press-lift-stapler-v1-20-per-mode/README.md)。
不另建清单或 latest 注册机制。Size 的 240 条 6 cm 重测输出与未变化的 2520 条旧回合组成完整视频集；
成绩不变的模型仍保留新尺寸视频，具体行为差异见[实验记录](../docs/attribute-size-6cm-ablation.md)。
