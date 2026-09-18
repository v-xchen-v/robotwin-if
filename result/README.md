# 正式评测结果

当前结果包为 **[robotwin-if-arm-only-v2-20blocks](robotwin-if-arm-only-v2-20blocks/README.md)**：
六个 policies × 六任务 × 每任务 20 blocks，已于 **2026-09-18 05:26 UTC** 完成校验，
共 **2760/2760 回合、720/720 blocks**。

Arm 按 `target-arm-only-lift-v2` 重跑 240 回合；其余五任务逐字节复用 Attribute-v2 的 2520 回合，
包含成功和已完成的 policy failure。先用错误臂抬起物体、随后换指定臂仍算失败，
见 [Arm 判据与验证](../docs/arm-select-target-arm-only.md)。

- [HTML 报表](robotwin-if-arm-only-v2-20blocks/results.html) · [Markdown](robotwin-if-arm-only-v2-20blocks/results.md)
- [分模式 CSV](robotwin-if-arm-only-v2-20blocks/results.csv) · [逐回合 CSV](robotwin-if-arm-only-v2-20blocks/episodes.csv)
- [Arm 新旧比较](robotwin-if-arm-only-v2-20blocks/arm-comparison.csv) · [来源](robotwin-if-arm-only-v2-20blocks/provenance.json)
- [校验证据](robotwin-if-arm-only-v2-20blocks/validation.json) · [Checkpoint](robotwin-if-arm-only-v2-20blocks/checkpoints.json)
- [当前 seed manifest](../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md)

`Overall` 对六个任务的 `Task Avg.` 等权平均；各任务内部对 modes 等权。
视频、动作轨迹等原始产物的位置见结果包 README。

```bash
(cd result/robotwin-if-arm-only-v2-20blocks && sha256sum --check --quiet SHA256SUMS)
```

## 历史包与验证证据

其余 **6 个历史成绩包和 2 份判据验证证据**已移入 [result-archive/](../result-archive/README.md)。
本目录中对应的旧名字是兼容软链接，保留已发布证据中的路径和哈希，不是重复的结果数据。
所有 119 个归档文件及当前结果包逐字节保持原样，原始仿真输出未移动。

- [历史成绩与版本差异](../result-archive/README.md#历史成绩)
- [当前判据的验证证据](../result-archive/README.md#当前判据的验证证据)
- [归档校验清单](../result-archive/SHA256SUMS)

在代码托管网站查旧结果，请从归档索引进入实体目录；本地旧路径继续支持读取与校验。
历史任务范围或判据不同的成绩不能直接当作当前分数比较。
