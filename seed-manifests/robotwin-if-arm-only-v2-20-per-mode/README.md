# RoboTwin-IF Arm-only-v2：六任务 × 20 blocks

每个 policy 460 回合；六个 policies 合计 2760 回合、720 blocks。
全部六份 flat manifest 与上一版 Attribute-v2 逐字节一致。
本轮重跑 Arm-Select 的 240 回合（每 policy 左右臂各 20 回合）；其余五任务的 2520 回合逐字节复用 Attribute-v2，包含成功和失败。
Arm 保留 5 cm cube-v3 场景，Attribute 保留 target-only-lift-v2，Bottle 保留 v6 terminal，Spatial 保留 left/right/on_top。

Arm 使用 target-arm-only-lift-v2：指定臂当前抬升超过 5 cm，且错误臂整回合从未完成该抬升。
沿用 20 cm 最近 TCP 归属、配对指令、400-action 预算、checkpoints 和推理参数。

- [套件配置](suite.yml) · [seed/mode JSON](seed-modes.json) · [CSV](seed-modes.csv)
- [复用索引与 SHA-256](reusable-results.yml) · [源码复用审计](reuse-audit.json)
- [新判据与验证](../../docs/arm-select-target-arm-only.md)

校验：`python seed-manifests/robotwin-if-arm-only-v2-20-per-mode/verify.py`。
