# Benchmark 核心模块

这里保留当前六任务共用的纯 CPU 逻辑，不导入模拟器或模型。

| 模块 | 当前用途 |
|---|---|
| [seed_contracts.py](seed_contracts.py) | 六任务的 mode、scene seed、完整 block 规则；退休任务的只读标识。 |
| [seed_manifest.py](seed_manifest.py) | Flat manifest 读写、完整性校验和规范化 SHA-256。 |
| [seed_generation.py](seed_generation.py) | Expert 筛选状态、完整 block 接受/拒绝、断点续跑和资格证据校验。 |
| [seed_modes.py](seed_modes.py) | 从发布清单导出并核对人可读的 seed/mode JSON 与 CSV。 |
| [__init__.py](__init__.py) | 对外导出常用接口。 |

历史格式兼容仍有当前用途：最新 Stapler 发布中的 Arm、Attribute、Noun、Sequence flat manifests 使用 schema v1；
继承的资格证据也使用旧 contract schema。Spatial 的旧五模式证据用于证明当前三模式 seeds 的来源，
因此保留原始 `seed // 5` 和 offsets `0, 1, 4` 的身份映射。

Bottle/Bell/Grasp 的简短 seed 元数据供历史清单、结果和报告读取使用；`new_generation_state` 与 `run_generation`
拒绝已退休任务，policy 入口也不会重新启用它们。旧 Bottle 的轨迹判据和测试已移除，原文件见[清理记录](../docs/archive/obsolete-benchmark-scripts.md)。

当前使用方法见 [seed manifest 指南](../docs/seed-manifest-usage.md)和[发布溯源](../docs/release-provenance.md)。
