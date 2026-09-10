# grasp_cube_approach 平移版试验

`grasp_cube_approach` 默认使用 `fixed-v1`。新配置
`demo_clean_grasp_approach_v2` 通过 `grasp_approach_scene_version: translate-v2`
启用小范围平移，使用独立 task_config 和重新验证的 seed manifest。

## 场景与配对

- `scene_seed = seed // 2`，偶数 seed 为 top，奇数为 side。
- 方块和静态底座一起平移。x 在 `[-1, 1] cm` 内分左、中、右三个等宽区间，
  按 scene_seed 轮换；区间内部均匀采样。y 在 `[-6, -5] cm` 内均匀采样。
- 不施加旋转，生成四元数固定为 `[1, 0, 0, 0]`。
- 两种模式的 oracle 都固定右臂，不再因 x 跨过零而切换手臂。
- 同一 block 的场景完全相同。六个 evaluator 的共享指令入口按 scene_seed 选择模板，
  一对指令只替换 `from the top` / `from the side`；模板使用手臂字段时均为右臂。
  默认 v1 保留原来的 raw seed 模板选择和 `from above` 同义表达。
  此模板配对规则针对本仓库 evaluator，原生 RoboTwin 离线语言生成器未改。
- 方块边长 5 cm、底座高度 2.4 cm、侧面 contact id 6、预抓距离 8 cm、
  oracle 抬升指令 12 cm、评测动作上限 400 均沿用原设置。
- 成功仍要求抬升超过 5 cm 且抓取方向正确：top 的 `|approach_z| >= 0.7`，
  side 的 `|approach_z| <= 0.3`。policy 仍读取首次接触时的方向，后续旋转不能补救错误接近方向。
  固定右臂是 oracle 的执行设置，未新增 policy 手臂成功判据。
- `env.info['grasp_approach_scene']` 保存版本、scene_seed、位置分区、方块和底座生成位置、四元数、yaw 及 oracle 手臂。
  实际仿真稳定后的位姿另存于预检记录。诊断字段不进入模板参数 `info['info']`。

旧 `POSE_JITTER` 开关是不同的历史实验；与 translate-v2 同时开启会报错。

## 安装与串行预检

在仓库根目录、RoboTwin Python 环境中执行。配置独立安装，不在 task bridge 管理的链接范围内：

```bash
ln -s "$(pwd)/tasks/task_config/demo_clean_grasp_approach_v2.yml" third_party/robotwin/task_config/demo_clean_grasp_approach_v2.yml
python tools/probe_grasp_approach_variation.py \
  --output outputs/policy-eval/grasp-approach-v2-probe-new \
  --blocks 12
```

如果链接已指向本配置，无需重复安装。默认候选 seeds 为 `100000..100023`，
可通过 `--seed-start` 指定另一批预先固定的偶数起始 seed。
预检使用一个 simulator、零个模型 server，默认绑定 GPU 0，串行完成 38 回合：

1. 2 个 fixed-v1 回归回合，与旧七任务评测的三路初始 RGB 逐像素比较。
2. 12 个候选 blocks，共 24 回合，分别验证顶抓与侧抓、no-op 失败、右臂执行、
   配对三路 RGB/方块与底座位姿/语言模板一致。
3. 前 3 个 blocks 覆盖三个 x 区间，共 6 次重复抓取和 6 次错误方向反例。
   反例必须实际抬起并采用相反方向，同时被任务成功判据拒绝。
   复测与反例的初始场景必须重建一致。

`--reference` 可指定旧 `if-seven-tasks-2blocks-001` 归档路径。
保留所有候选失败，不自动换 seed；有复测失败的 block 不会标为通过。
只有候选、控制和场景一致性检查全部通过，才导出 `grasp_cube_approach.json` 评测 manifest。
失败时仍输出完整诊断 `report.json`、`blocks.json` 和 `episodes.json`。

supervisor 每 10 秒记录 GPU 状态，查询超时、显存超过 40,000 MiB、180 秒无阶段心跳
或超过 30 分钟总时限时停止 worker，不自动重启。监控不能保证驱动永不阻塞。
输出包含初始三路观测 NPZ、初始/最终 head-camera PNG、源文件快照与哈希、GPU 采样和日志。

## 使用通过预检的 manifest

六个 evaluator 均使用相同任务名，显式指定新配置：

```text
--task grasp_cube_approach
--task-config demo_clean_grasp_approach_v2
--seed-manifest seed-manifests/if-ext-v2-12-per-mode/grasp_cube_approach.json
--blocks 12
```

模型连接参数沿用各 policy 配置。旧 `demo_clean` manifest 与新配置不能混用。
正式评测使用 [七任务 12-block 清单](../seed-manifests/if-ext-v2-12-per-mode/README.md)，
其中 grasp v2 的 seeds 独立于调试集。已验证的 12-block 开发集和完整 oracle 证据另存于
[v2 manifest 目录](../seed-manifests/if-ext-v2-dev-12-per-mode/README.md)。
当前渲染同步/oracle 缓存优化只对 `demo_clean` 启用，此试验配置使用原生执行路径。
小样本 oracle 预检验证的是场景可执行性；扩大到 50 blocks 前应验证另一批预先固定的 seeds，
六个 policy 使用同一份提前确定的完整 blocks，不按 policy 成败挑选场景。

## 2026-09-09 试验结果

首轮 `outputs/policy-eval/grasp-approach-v2-probe-001` 使用 x ±1 cm、y `[-6, -4] cm`。
侧抓 12/12，顶抓 8/12；4 个左侧候选的顶抓规划失败，且预定复测复现了失败。
这轮只输出诊断结果，没有导出评测 manifest，全部失败与源码快照保留。

第二轮只将 y 收窄为 `[-6, -5] cm`，使用同一批 seeds，没有换 seed。
`outputs/policy-eval/grasp-approach-v2-probe-002` 的结果：

- 12 个不同场景，左/中/右各 4 个；顶抓 12/12、侧抓 12/12。
- 6/6 重复抓取成功；6/6 错误方向反例实际抬起但被成功判据拒绝。
- 12/12 配对场景的三路初始 RGB、方块/底座位姿、关节状态完全一致，句式只替换 top/side。
- 2/2 fixed-v1 回归抓取成功，初始三路 RGB 与旧归档逐像素一致。
- 28 项 CPU 检查通过（grasp 6、arm_select 8、共享 IF 评测 6、评测优化 8）。
- 单 sim、零 server，38 回合共 167.1 秒；GPU 0 每 10 秒采样的显存最大值 5,194 MiB。

通过预检的 manifest：
`outputs/policy-eval/grasp-approach-v2-probe-002/grasp_cube_approach.json`。
完整报告 `report.md`、机器可读记录 `report.json`、独立文件核验 `checks.json` 和预览 `scenes.png`
保存在同目录。范围依据这批开发 seeds 调整，本批不能视为独立泛化验证。
尚未运行六个 policy 的平移版评测；扩大到 50 blocks 前需另取预先固定的 seeds 做预检。
