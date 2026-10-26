# 正式评测结果

当前结果包为 **[robotwin-if-press-lift-stapler-v1-20blocks](robotwin-if-press-lift-stapler-v1-20blocks/README.md)**：
六个 policies × 六任务 × 每任务 20 blocks，已于 **2026-10-26 11:53 UTC** 完成校验，
共 **2760/2760 回合、720/720 blocks**。

Verb 改为订书器 Press/Lift，新增 240 回合；其余五任务的 2520 回合原样复用 Arm-only-v2，
包含成功和已完成的 policy failure。六个模型保留原 checkpoint 和推理参数。

- [HTML 报表](robotwin-if-press-lift-stapler-v1-20blocks/results.html) · [Markdown](robotwin-if-press-lift-stapler-v1-20blocks/results.md)
- [分模式 CSV](robotwin-if-press-lift-stapler-v1-20blocks/results.csv) · [逐回合 CSV](robotwin-if-press-lift-stapler-v1-20blocks/episodes.csv)
- [Press/Lift 配对统计](robotwin-if-press-lift-stapler-v1-20blocks/stapler-summary.json) · [来源](robotwin-if-press-lift-stapler-v1-20blocks/provenance.json)
- [校验证据](robotwin-if-press-lift-stapler-v1-20blocks/validation.json) · [Checkpoint](robotwin-if-press-lift-stapler-v1-20blocks/checkpoints.json)
- [执行恢复记录](robotwin-if-press-lift-stapler-v1-20blocks/execution-recoveries.json) · [当前 seed manifest](../seed-manifests/robotwin-if-press-lift-stapler-v1-20-per-mode/README.md)

`Overall` 对六个任务的 `Task Avg.` 等权平均；各任务内部对 modes 等权。
本次替换了 Verb，Overall 与旧版的变化不代表同一任务上的模型能力提升。
视频、动作轨迹等原始产物的位置见结果包 README；本机完整视频目录为 <http://127.0.0.1:8897/>。

```bash
(cd result/robotwin-if-press-lift-stapler-v1-20blocks && sha256sum --check --quiet SHA256SUMS)
```

## 复用来源与判据证据

[Arm-only-v2 结果包](robotwin-if-arm-only-v2-20blocks/README.md)保留其原有 Bottle Verb 成绩，
也是本版其余五任务的复用来源。其 [Arm/Attribute 验证证据](robotwin-if-arm-only-v2-20blocks/evidence/README.md)
继续用于解释当前成功判据。更早版本的来源与历史哈希见[发布溯源说明](../docs/release-provenance.md)。
