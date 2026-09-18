# Arm-Select cube-v3 dev：12 个完整 blocks

配置：`demo_clean_arm_select_v3`。seeds `300000–300023`，每场景偶数 left、奇数 right。

5 cm cube；世界坐标 x ∈ [−4,4] cm，y ∈ [−8,−6] cm，中心生成 z=0.766 m；yaw ∈ [−15°,15°]。
每个 scene seed 采样不同位姿，配对回合共享场景与句式，只切换 left/right。

- 24/24 正确手臂 oracle 抓取、6/6 复测通过。
- 6/6 错误手臂反例确实抬起物体，但被任务成功判据拒绝。
- 12/12 配对 RGB、位姿、句式一致；复测初始图像一致。
- 含 26 次边界/中心位姿检查，全部通过。
- 2/2 fixed-v1 回归通过，与历史三路初始 RGB 逐像素一致。

`qualification.json` 为完整逐回合证据，`provenance.json` 记录源码/配置哈希，`supervisor.json` 记录退出状态。
原始 NPZ/PNG/日志与源码快照在 `outputs/policy-eval/arm-select-cube-v3-probe-003/`。

这是 oracle 可执行性验证，尚无 cube-v3 policy 成功率。正式 evaluator 仍逐 seed 资格检查，不替换失败 seed。
旧 v1/v2 manifest 不适用于本配置；此目录是独立单任务探索集，没有切换默认六任务发布清单。

[环境设计与验证说明](../../docs/recon/arm-select-cube-v3.md)。
