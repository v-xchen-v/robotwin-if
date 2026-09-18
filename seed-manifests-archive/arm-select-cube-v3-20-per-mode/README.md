# Arm-Select cube-v3：20 个完整 blocks

配置：`demo_clean_arm_select_v3`。固定 seeds `500000–500039`，共 **20 blocks / 40 episodes**，
left、right 各 20 回合。每个 block 的偶数 seed 指定 left，奇数 seed 指定 right。

5 cm cube；世界坐标 x ∈ [−4,4] cm，y ∈ [−8,−6] cm，中心生成 z=0.766 m；yaw ∈ [−15°,15°]。
20 个不同初始场景覆盖 x 的左/中/右分区各 6/7/7 个。同一 block 的两回合共享位姿和句式，
只切换指令中的手臂词。此批 seeds 与先前的开发集、独立验证集无重叠，未替换任何候选 seed。

- 40/40 正确手臂 oracle 抓取、6/6 复测通过。
- 6/6 错误手臂反例抬起物体，但被任务成功判据拒绝。
- 20/20 blocks 的三路初始 RGB、位姿、句式一致；复测初始图像一致。
- 2/2 fixed-v1 回归通过，与历史三路初始 RGB 逐像素一致。
- 合计 54/54 检查回合通过，supervisor 正常退出；源码及快照哈希一致。
- 六个 policy evaluator 的 `select_seeds` 均接受本清单和 `--blocks 20`。

几何范围沿用已完成 26/26 边界检查的[开发集](../arm-select-cube-v3-dev-12-per-mode/README.md)。
本清单的资格验证检查 oracle 可执行性；六个 policies 的 cube-v3 评测已随后完成，
共 240 回合，见[六任务合并结果](../../result/robotwin-if-cube-v3-20blocks/README.md)。

可复现生成命令（在仓库根目录执行，输出目录必须不存在）：

```bash
/home/xichen6/miniconda3/envs/RoboTwin/bin/python tools/probe_arm_select_variation.py \
  --scene-version cube-v3 --blocks 20 --seed-start 500000 \
  --sim-gpu 0 --output outputs/policy-eval/arm-select-cube-v3-20blocks-001
```

六个 policy evaluator 使用以下参数，模型连接参数见对应 policy README：

```text
--task arm_select
--task-config demo_clean_arm_select_v3
--seed-manifest seed-manifests/arm-select-cube-v3-20-per-mode/arm_select.json
--blocks 20
--output-dir <新的独立结果目录>
```

`qualification.json` 保存完整逐回合证据，`provenance.json` 记录生成命令与源码/配置哈希，
`supervisor.json` 记录退出状态，`verification.json` 记录清单结构、分区覆盖及六个 evaluator 的加载检查。
原始 NPZ/PNG、日志和源码快照在 `outputs/policy-eval/arm-select-cube-v3-20blocks-001/`。

[环境设计与验证说明](../../docs/recon/arm-select-cube-v3.md)。
