# RoboTwin-IF cube-v3：六任务合并评测

新 taskset：[robotwin-if-cube-v3-20-per-mode](../seed-manifests/robotwin-if-cube-v3-20-per-mode/README.md)。
六个 policies、六项任务、每任务 20 blocks；每个 policy 460 回合，总计 2760 回合、720 blocks。

**2026-09-16 17:59 UTC 已完成并通过校验：2760/2760 回合、720/720 blocks。**
[新结果包](../result/robotwin-if-cube-v3-20blocks/README.md)提供[完整 HTML](../result/robotwin-if-cube-v3-20blocks/results.html)、
[逐回合 CSV](../result/robotwin-if-cube-v3-20blocks/episodes.csv)与[正式校验](../result/robotwin-if-cube-v3-20blocks/validation.json)。
共 1292 次成功、1468 次 policy failure；本轮重跑 Arm 240 回合，复用另外五任务 2520 回合。

| Policy | Arm Left | Arm Right | Arm Avg. (%) | 六任务 Overall (%) |
|---|---:|---:|---:|---:|
| X-VLA | 5/20 | 3/20 | 20.0 | 30.0 |
| LingBot-VA | 18/20 | 20/20 | 95.0 | 61.4 |
| LingBot-VLA | 7/20 | 11/20 | 45.0 | 33.7 |
| VLAct All | 16/20 | 13/20 | 72.5 | 60.0 |
| DM05 | 9/20 | 16/20 | 62.5 | 56.0 |
| Hy-VLA | 7/20 | 12/20 | 47.5 | 39.8 |


| 任务 | 配置 | 回合/policy | 本轮处理 |
|---|---|---:|---|
| bottle_verb | demo_clean | 40 | 复用最新 v6 回合末判定结果 |
| pick_diverse_object | demo_clean | 40 | 原样复用 |
| attribute_select | demo_clean | 160 | 原样复用 |
| arm_select | demo_clean_arm_select_v3 | 40 | cube-v3，重新运行 |
| stack_sequence | demo_clean | 120 | 原样复用 |
| place_relative | demo_clean | 60 | 原样复用 left/right/on_top |

复用源为 `/Data/robotwin-if/evaluations/if-six-tasks-spatial3-bottle-v6-terminal-20blocks-001`，
对应[上一轮已完成结果包](../result/if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/README.md)。
新运行目录为 `/Data/robotwin-if/evaluations/robotwin-if-cube-v3-20blocks-001`，
仓库入口为 `outputs/policy-eval/robotwin-if-cube-v3-20blocks-001/`。

五任务的 2520 回合逐文件复制，保留成功和 policy failure；旧记录、动作、视频均核对 SHA-256。
清单中的 `reusable-results.yml` 绑定每条来源记录及 provenance，`reuse-audit.json` 记录源码差异。
与上一轮冻结快照相比，五个复用任务及其依赖源码一致；共享 evaluator 仅扩展 cube-v3 的配对指令选择，
正式 runner 的变更仅为默认运行路径与默认 taskset。

新 Arm-Select 使用预先固定的 seeds 500000–500039，不复用旧长柱回合；
5 cm cube 的[几何与 oracle 资格证据](recon/arm-select-cube-v3.md)已保存。
每个 policy 重跑 40 回合，动作预算 400。六个 checkpoint 和各自推理参数沿用上一轮。
GPU 0 串行仿真、GPU 1 串行加载模型；X-VLA 建立参考，其他模型逐回合核对初始 RGB、状态与指令。

构建与运行命令：

```bash
/home/xichen6/miniconda3/envs/RoboTwin/bin/python tools/release_arm_select_cube_v3.py build
/home/xichen6/miniconda3/envs/RoboTwin/bin/python tools/run_formal_policy_suite.py prepare \
  --run-dir /Data/robotwin-if/evaluations/robotwin-if-cube-v3-20blocks-001 \
  --release seed-manifests/robotwin-if-cube-v3-20-per-mode \
  --old-run /Data/robotwin-if/evaluations/if-six-tasks-spatial3-bottle-v6-terminal-20blocks-001
/home/xichen6/miniconda3/envs/RoboTwin/bin/python tools/run_formal_policy_suite.py run \
  --run-dir /Data/robotwin-if/evaluations/robotwin-if-cube-v3-20blocks-001
```

build/prepare 均要求目标不存在；恢复只执行 run，已归档的成功和 policy failure 不再运行。
完整状态见运行目录中的 `status.json` / `report.md`。本轮自动执行了以下打包命令：

```bash
/home/xichen6/miniconda3/envs/RoboTwin/bin/python tools/release_arm_select_cube_v3.py package
```

结果包已写入 `result/robotwin-if-cube-v3-20blocks/`，含 HTML/Markdown、分模式与逐回合 CSV、
checkpoint、运行计划、资格校验和哈希。打包时再次核对五任务的结果记录和统计与上一轮完全一致。
Overall 对六个 Task Avg. 等权；新旧 Arm/Overall 的差异包含环境变化的影响。

正式校验逐条覆盖 2760 个回合：artifact SHA-256、动作解码与执行轨迹、跨 policy 的初始 RGB/指令/机器人状态，
以及全部 240 个新视频的帧数。打包再次确认五任务的统计行及逐回合字段不变（只有来源 `origin` 标为 `reused`），
并核对 checkpoint 证据哈希。新旧结果包的 `SHA256SUMS` 均通过。

本轮有 **4 次推理前 oracle 初始化失败**，分别发生于 LingBot-VA、LingBot-VLA、VLAct、DM05 的 seed `500007`。
四次都在新 simulator 中用同一 seed 的第二次初始化通过；失败尝试均为 0 次动作、0 次模型 chunk。
已完成的 policy 成功或失败回合没有重跑，也没有替换 seed。
[重试审计](../result/robotwin-if-cube-v3-20blocks/oracle-setup-retries.json)包含原始失败记录、重试决定和最终回合的哈希。

Hy-VLA 的 20 对场景中，19 对仅一个臂指令成功、1 对两个指令均失败；没有左右臂都成功的 pair。
这只是配对结果的观察：21 个失败回合中，20 个终态未满足抬升条件，不能仅凭成功率把所有失败归因为用错机械臂。
进一步区分抓取问题与指令跟随需要结合逐回合视频。

任务页已换为 [LingBot-VA cube-v3 左右臂演示](assets/task-demos/arm_select_cube_v3.mp4)（seeds 500000/500001），
源视频、记录和导出文件哈希见 [sources.json](assets/task-demos/sources.json)；旧长柱演示原样保留。
