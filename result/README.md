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
全部 2760 条视频、动作、观测和运行证据可从 Azure 授权下载，完整目录约 8.19 GiB。
见[完整备份下载与校验](../docs/download-results.md)，其中也提供独立视频查看器的启动步骤。
冻结结果包内的原机器路径保留为历史来源记录；下载后的文件使用备份内 `episode-index.csv` 的相对路径定位。

```bash
(cd result/robotwin-if-press-lift-stapler-v1-20blocks && sha256sum --check --quiet SHA256SUMS)
```

## 复用来源与判据证据

`result/` 只保留上述 Stapler v1 包。旧 [Arm-only-v2 结果](https://github.com/v-xchen-v/robotwin-if/blob/ac582a75267126c7a8fe17c220475d517b73882b/result/robotwin-if-arm-only-v2-20blocks/README.md)及
[Arm/Attribute 判据验证证据](https://github.com/v-xchen-v/robotwin-if/blob/ac582a75267126c7a8fe17c220475d517b73882b/result/robotwin-if-arm-only-v2-20blocks/evidence/README.md)已移至 Git 历史，
可从备份分支 `master-261027-staper-v1` 查阅。当前包的 2520 条复用记录、checkpoint、来源哈希与完整成绩保持原样。
复用和发布脚本从固定提交读取旧证据，方法见[发布溯源说明](../docs/release-provenance.md)。
