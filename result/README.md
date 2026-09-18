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

## 当前判据证据

[Arm/Attribute 验证证据](robotwin-if-arm-only-v2-20blocks/evidence/README.md)
随最新版保留，用于解释当前成功判据，不是另一套模型成绩。

本目录只提供上面的最新结果包。旧成绩、归档目录及兼容软链接已从当前分支移除；
原始来源记录和历史哈希仍保留，详见[发布溯源说明](../docs/release-provenance.md)。
