# RoboTwin-IF Attribute-v2：六任务 × 20 blocks

每个 policy 460 回合；六个 policies 合计 2760 回合、720 blocks。
全部六份 flat manifest 与上一版 cube-v3 逐字节一致。
本轮重跑 Attribute-Select 的 960 回合；其他五任务的 1800 回合逐字节复用 cube-v3，包含成功和失败。
Arm 保留 5 cm cube-v3，Bottle 保留 v6 terminal 判据，Spatial 保留 left/right/on_top。

Attribute 使用 `target-only-lift-v2`：目标当前抬升严格超过 5 cm，且干扰物整回合从未越过该阈值。
位置、指令、400-action 预算、双目标 oracle gate、checkpoints 与推理参数均保持原版。
诊断回放不能替代本轮新的模型推理。

- [套件配置](suite.yml) · [seed/mode JSON](seed-modes.json) · [CSV](seed-modes.csv)
- [复用索引与 artifact SHA-256](reusable-results.yml) · [源码复用审计](reuse-audit.json)
- [判据修复与回放证据](../../docs/attribute-select-target-only.md)

校验：`python seed-manifests/robotwin-if-attribute-v2-20-per-mode/verify.py`。
正式入口：`tools/run_formal_policy_suite.py prepare/run`，prepare 指定本目录、独立 `--run-dir` 和上一版 cube-v3 的 `--old-run`。
