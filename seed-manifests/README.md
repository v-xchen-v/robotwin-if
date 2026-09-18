# Seed manifests

当前正式入口为 [RoboTwin-IF Arm-only-v2](robotwin-if-arm-only-v2-20-per-mode/README.md)：
**六任务 × 每任务 20 blocks，460 回合/policy**。它包含完整六任务，不是仅有 Arm。
Arm 使用 cube-v3 场景及 target-arm-only-lift-v2 判据；Attribute 使用 target-only-lift-v2；
Bottle 保留 v6 terminal；Spatial 为 left/right/on_top。

[`scripts/eval.sh`](../scripts/eval.sh)、[`tools/export_seed_modes.py`](../tools/export_seed_modes.py)
和正式 runner 的 `--release` 默认值均指向该版本。新机器运行不需要旧评测产物：

```bash
python tools/export_seed_modes.py --check
bash scripts/eval.sh --policy hy_vla --output-dir outputs/policy-eval/hy-vla-new --dry-run
```

[当前结果](../result/robotwin-if-arm-only-v2-20blocks/README.md)已完成并校验 2760 回合；
Arm 新跑 240 回合，其他五任务复用 Attribute-v2 的 2520 回合。
最近 cube-v3、Attribute-v2 和 Arm-only-v2 的六份 flat seed JSON 逐字节相同，
版本差异主要记录成功判据、重跑范围和结果来源；实际判据由配套任务代码执行。

## 发布与校验

本目录只包含上面的当前正式清单，旧版本和兼容软链接已移除。
新评测无需旧结果或 Git 历史；接入其他 repo 时请固定当前 commit 和上述路径。

```bash
(cd seed-manifests/robotwin-if-arm-only-v2-20-per-mode && sha256sum -c SHA256SUMS)
```

`verify.py` 用于完整历史溯源：从固定 Git commit 在临时目录读取原始资格证据，
并检查原机运行数据，不会将旧版本写回当前目录。
清单中保留的旧路径是来源记录；完整要求见[发布溯源说明](../docs/release-provenance.md)。
