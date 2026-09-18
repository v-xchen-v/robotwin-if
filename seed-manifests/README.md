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

## 历史归档

其余 **12 份**实体目录已集中到 [`seed-manifests-archive/`](../seed-manifests-archive/README.md)，
包含旧正式套件及开发/验证清单。旧位置保留相对软链接，兼容本地已发布结果的相对链接、
资格证据中的固定路径及旧校验脚本；这些软链接不是重复的 manifest 数据。
历史文件逐字节保留，归档校验清单见 [SHA256SUMS](../seed-manifests-archive/SHA256SUMS)。
归档单独放在仓库根目录，与原目录保持相同层级，保留旧文档相对链接。
需要运行历史校验时，使用 `python tools/verify_archived_seed_release.py <版本名>`；
该入口临时还原旧实体目录布局，避免旧脚本的固定路径检查被归档位置影响。

日常选用上面的当前入口；历史版本按归档索引查找。清理软链接前仍需迁移其引用，
不能只按目录名删除父版本或 Arm oracle 资格证据。Git checkout 需保留符号链接（评测环境为 Linux）。
在代码托管网站浏览历史清单时，请从归档索引进入实体目录。

`seed-modes.json/csv` 的便携校验只依赖仓库文件；各 release 的 `verify.py` 还可能需要
原机运行目录、源码快照和原始产物，用于验证历史复用来源。
