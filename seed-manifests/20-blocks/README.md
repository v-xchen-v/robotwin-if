# 六任务固定 seeds

每个 `<task>.json` 是 evaluator 直接读取的输入，六份文件的 seeds 和字节沿用已完成评测的清单。
每任务 20 个完整 blocks，每模型 460 回合。seed 顺序不可排序、替换或跳过。

- `suite.yml`：任务、配置、模式数量、动作预算与当前设置。
- `seed-modes.json` / `seed-modes.csv`：从六份输入导出的 block、mode、scene 对照。
- `qualification.json`：expert 与同场景初始观测校验摘要；Size 大块为 6 cm，小块为 4 cm。
- `SHA256SUMS`：本目录所有交付文件的校验值，自身除外。

在仓库根目录运行 `python tools/verify_benchmark.py`，核对清单、成绩及校验值，无需模型或仿真。
完整资格生成记录和原始源码快照在[结果下载](../../docs/download-results.md)的 `audit/seed-qualification/`；
6 cm Size 的复核证据在 `audit/size-experiment/`。原始快照保留其生成时的设置，不能替代当前 Size 资格证据。

[采集 expert 预览](../../docs/expert-review.md) · [评测入口](../../docs/formal-policy-evaluation.md) · [生成新的候选 seeds](../../docs/seed-manifest-usage.md)
