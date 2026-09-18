# arm_select 场景变化试验

本文及结果属于 6 × 6 × 20 cm 长柱版本。2026-09-16 的 [cube-v3 探索](recon/arm-select-cube-v3.md)
采用独立配置；旧代码与 240 回合结果已[备份](../bak/arm_select-long-v2-20260916/README.md)。

`arm_select` 默认仍使用 `fixed-v1` 中央固定场景。新配置
`demo_clean_arm_select_v2` 通过 `arm_select_scene_version: jitter-v2` 启用位置与朝向变化。
它是单独的试验条件，使用不同 task_config 和重新验证的 seed manifest。

## 场景与指令

- `scene_seed = seed // 2`，偶数 seed 指令为左臂、奇数为右臂。
- x 在 `[-2,2] cm` 内分为左、中、右三个等宽区间，按 scene_seed 循环，每段内部均匀采样。
- y 在 `[10,12] cm` 内均匀采样，绕竖直轴旋转在 `±3°` 内均匀采样。
- 同一 pair 的几何完全相同；采样只依赖 scene_seed，不依赖被命令的手臂。
- 方块尺寸、颜色、质量设置、抬起距离、成功判据和动作上限沿用 v1。
- 六个 policy 的共享评测入口对 v2 使用 scene_seed 选择语言模板，同一 pair 只替换 `left/right`。
  默认 v1 保留原来按 raw seed 选择模板的行为。此配对句式规则针对本仓库的六个 evaluator，
  原生 RoboTwin 离线语言生成器的行为没有修改。
- `env.info['arm_select_scene']` 记录版本、scene_seed、位置分区、生成位置/四元数和 yaw。
  这些诊断字段不进入模板参数 `info['info']`。

每个候选 block 必须验证左右臂都可执行才能保留；所有 policy 使用同一份提前固定的完整 blocks。
候选被剔除后，仍应检查最终 manifest 的左右位置覆盖，不能依赖 policy 成败挑选场景。

## 安装配置与串行预检

在已有 RoboTwin 环境和 task bridge 的仓库根目录执行。配置文件目前单独安装，不属于 bridge 管理的 16 个链接：

```bash
ln -s "$(pwd)/tasks/task_config/demo_clean_arm_select_v2.yml" third_party/robotwin/task_config/demo_clean_arm_select_v2.yml
```

如果该链接已指向本配置，无需重复安装。用 RoboTwin 环境的 Python 执行：

```bash
python tools/probe_arm_select_variation.py \
  --output outputs/policy-eval/arm-select-v2-probe-new \
  --blocks 12
```

预检使用 1 个 simulator、0 个模型 server，默认绑定 GPU 0。包含：

- 两个 v1 回归回合，与已有 `if-seven-tasks-2blocks-001` 三路初始 RGB 逐像素比较。
- 12 个预先固定的候选 blocks，共 24 回合，检查初始 no-op 失败、正确手臂能抬起、配对 RGB/位姿一致、配对句式一致。
- 前三个 blocks（覆盖三个位置区间）各重复两只手，并执行两只手的错误指令反例：物体确实抬起，但成功判据必须拒绝。

`--reference` 可指定包含该 v1 归档的其他路径。输出保存全部失败，不自动替换 seed。
supervisor 每 10 秒记录 GPU 利用率和显存；查询超时、显存超过 40,000 MiB、
180 秒无阶段心跳或超过 30 分钟总时限会停止 worker，不自动重启。监控不能保证驱动永不阻塞。

产物包括 `report.json`、`episodes.json`、`blocks.json`、通过双臂验证的 `arm_select.json`、
三路初始观测 NPZ、初始/结束 PNG、源文件哈希和 GPU 采样。预检成功率是 oracle 的可执行性，
不代表任何 policy 的成功率。

当前正式入口已升级为 [Arm-only-v2 / cube-v3](../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md)。以下保留旧 v2 试验的配置与证据。

## 使用试验 manifest

六个 evaluator 都使用相同的任务名 `arm_select`，显式选择新配置：

```text
--task arm_select
--task-config demo_clean_arm_select_v2
--seed-manifest seed-manifests/if-ext-v2-12-per-mode/arm_select.json
--blocks 12
```

其余模型连接参数沿用各 policy 的配置。旧 `demo_clean` manifest 与新配置不能混用。
当时的 v2 正式评测使用 [六任务 20-block 清单](../seed-manifests/if-ext-v2-six-tasks-spatial3-20-per-mode/README.md)，
其中 arm v2 的 seeds 独立于调试集。已验证的 12-block 开发集和完整 oracle 证据另存于
[v2 manifest 目录](../seed-manifests/if-ext-v2-dev-12-per-mode/README.md)。
当前六个 evaluator 统一使用原生渲染，并在每个新回合执行 oracle qualification。

## 2026-09-09 试验结果

第二轮 `outputs/policy-eval/arm-select-v2-probe-002` 已完成：12 个不同场景（左/中/右各 4 个），
24/24 正确手臂 oracle 抓取成功，6/6 复测成功，6/6 错误手臂反例确实抬起但被成功判据拒绝。
12/12 blocks 的三路初始 RGB、位姿和模板配对一致；两个 v1 回归回合的初始图像与旧归档一致。
8 项 arm_select 单元检查、6 项共享 IF 评测检查、8 项评测优化回归检查通过。

第一轮较宽范围（x ±3 cm、y 8–12 cm、yaw ±10°）仅 7/12 blocks 通过首次双臂检查，且有复测失败。
第一轮原始记录和源码快照保留在 `arm-select-v2-probe-001`。第二轮使用同一批 seeds，收窄了范围，没有替换 seeds。
这是开发阶段的小样本结果；范围据此调过，扩大评测前应验证另一批预先固定的 seeds。

完整报告和预览见 `outputs/policy-eval/arm-select-v2-probe-002/report.md` 与 `scenes.png`。
