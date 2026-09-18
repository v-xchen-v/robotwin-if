# 历史 seed manifests

当前正式入口在 [seed-manifests/robotwin-if-arm-only-v2-20-per-mode](../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md)。
本目录的 12 份清单用于历史结果追溯、oracle 资格验证与回归检查，不作为默认评测入口。

2026-09-18 从 `seed-manifests/` 原样迁入：148 个原文件逐字节保留，未改变 seeds、配置、
资格报告、复用索引或历史验证程序。旧路径通过相对软链接继续读取，历史结果包保持不变。
部分旧 README 中的“当前”“尚未提交”等描述属于当时的发布记录；现在的状态以本索引为准。

| 归档版本 | 用途 |
|---|---|
| [robotwin-if-attribute-v2-20-per-mode](robotwin-if-attribute-v2-20-per-mode/README.md) | 上一版六任务；Attribute 判据更新，Arm 判据尚未更新 |
| [robotwin-if-cube-v3-20-per-mode](robotwin-if-cube-v3-20-per-mode/README.md) | 六任务；Arm 换为 5 cm cube-v3 场景 |
| [arm-select-cube-v3-20-per-mode](arm-select-cube-v3-20-per-mode/README.md) | 当前 40 个 Arm seeds 的 oracle 资格证据，不能当重复文件丢弃 |
| [arm-select-cube-v3-dev-12-per-mode](arm-select-cube-v3-dev-12-per-mode/README.md) | Cube-v3 场景开发及边界检查 |
| [arm-select-cube-v3-validation-12-per-mode](arm-select-cube-v3-validation-12-per-mode/README.md) | Cube-v3 独立验证集 |
| [if-ext-v2-six-tasks-spatial3-20-per-mode](if-ext-v2-six-tasks-spatial3-20-per-mode/README.md) | 六任务；Spatial 缩为三个 modes |
| [if-ext-v2-six-tasks-20-per-mode](if-ext-v2-six-tasks-20-per-mode/README.md) | 移除 Grasp 后的六任务；Spatial 仍为五个 modes |
| [if-ext-v2-wide-20-per-mode](if-ext-v2-wide-20-per-mode/README.md) | 七任务宽范围场景，每项 20 blocks |
| [if-ext-v2-wide-12-per-mode](if-ext-v2-wide-12-per-mode/README.md) | 七任务宽范围场景，每项 12 blocks |
| [if-ext-v2-12-per-mode](if-ext-v2-12-per-mode/README.md) | 七任务初版 v2，每项 12 blocks |
| [if-ext-v2-dev-12-per-mode](if-ext-v2-dev-12-per-mode/README.md) | Arm/Grasp v2 开发集 |
| [if-ext-v1-100-per-mode](if-ext-v1-100-per-mode/README.md) | 最初七任务的 100-block seed 池及生成证据 |

版本依赖沿 Arm-only-v2 → Attribute-v2 → cube-v3 → Spatial3 → 六任务 → 七任务演进；
cube-v3 另外绑定 Arm oracle 资格证据。旧校验还会读取开发集或前一批 seeds，
因此归档时整体保存，没有按 policy 成败筛选或删除旧结果。

```bash
(cd seed-manifests-archive && sha256sum --check --quiet SHA256SUMS)
```

该校验不需要 simulator 或 `/Data`；148 个文件的 SHA-256 与迁移前一致。

部分原校验脚本会把实体目录的相对路径与冻结证据比较。兼容入口会在临时目录还原旧目录布局，
执行原脚本并返回其退出码，结束后删除临时副本；历史文件和哈希均不改写：

```bash
python tools/verify_archived_seed_release.py if-ext-v2-six-tasks-20-per-mode
python tools/verify_archived_seed_release.py if-ext-v2-six-tasks-spatial3-20-per-mode
```

各版本仍保留历史环境要求；有些需要原机结果与冻结源码，且可能不接受现行任务判据。
七任务 `if-ext-v2-wide-20-per-mode/verify.py` 在现行 Spatial 三模式代码下存在 block-size 断言冲突；
归档前的 Git 版本也复现了相同错误，需使用配套历史代码进行完整运行校验。
