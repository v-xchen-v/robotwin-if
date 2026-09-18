# Arm-Select target-arm-only-v2：六个 policies 重评

本轮重跑 X-VLA、LingBot-VA、LingBot-VLA、VLAct、DM05、Hy-VLA 的全部 Arm-Select 回合。
每个 policy 左右臂各 20 回合，共 **240 个新回合**。其余五任务的 **2520 回合**逐字节复用
已完成的 Attribute-v2 包，包含成功和失败，最终汇总 2760 回合、720 blocks。

- [独立 taskset](../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md)
- [复用源码审计](../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/reuse-audit.json)
- [新 Arm 判据与真实仿真验证](arm-select-target-arm-only.md)
- [发布来源与完整溯源校验](release-provenance.md)

运行目录（msrait-04）：

```text
/Data/robotwin-if/evaluations/robotwin-if-arm-only-v2-20blocks-001/
```

`status.json` / `report.md` 为评测进度，`workflow.json` 为评测、校验打包、README 更新状态。
完成后写入 `result/robotwin-if-arm-only-v2-20blocks/`，包含 HTML、逐回合 CSV、
新旧 Arm 比较表、来源、checkpoint 和校验证据；历史包仅保留在 Git 中。

## 不变项与新判据

六份 manifest 与 Attribute-v2 逐字节一致。Arm 使用原 cube-v3 场景、seeds 500000–500039、
unseen 指令、400-action 预算、同样的 checkpoint 和推理参数。
新判据 `target-arm-only-lift-v2` 要求指定臂当前抬升超过 5 cm，且非指定臂本回合从未完成该抬升。
归属沿用严格小于 20 cm 且比另一 TCP 更近的判定。

共享 `_if_grounding.py` 仅增加 ArmPickMonitor：去掉新增类后 AST 与父快照一致。
Attribute 继续使用 target-only-lift-v2；Bottle 保留 v6 terminal；Spatial 保留三模式。
每条复用记录、provenance、视频和动作均核对哈希。

## 执行与恢复

初始调度由 03 提供独立的模型服务；04 最多三个 simulator，GPU 0 一路、GPU 1 两路。
03 的环境和 checkpoint 安装复用，服务及源码快照位于新的隔离目录
`/Data/robotwin-if-xichen/arm-only-v2-20260918/`。
模型顺序加载、GPU 显存准入、温度暂停和每动作降温策略沿用上一轮已验证配置。
模拟暂停不推进物理、不修改动作或重置策略。03 不承担本轮仿真。

所有新回合在推理前逐像素对齐父运行的同 seed X-VLA 三路初始 RGB，核对状态与原指令。
GPU 1 另外做前 8 个 seeds 的新判据初始化预检。
最终打包逐数组核对每个 policy 自己的初始 NPZ，并核对动作解码、视频帧数和最终计数。

完成的成功和 policy failure 不重跑；纯推理前 oracle 失败可在全新 simulator 中用原 seed
重试，最多 3 次初始化。其他运行错误停止队列，不替换 seed 或改写旧结果。

运行入口为 `support/run-and-package.py`，按顺序执行 controller、最终打包和 README 更新。
只有全部校验完成后才发布新统计。

## Hy-VLA 双实例分片

本次运行已完成；以下保留独立模型实例与 simulator 分片的执行契约。
切换分片前先让原 worker 完成当前回合并停止领取新回合，完成的成功和失败均不重跑。

新入口为 [`run_sharded_remote_suite.py`](../tools/run_sharded_remote_suite.py)：

- 原 Hy-VLA 使用 03 GPU 2 推理、04 GPU 1 仿真。
- 第二个 Hy-VLA 使用 03 GPU 3 推理、04 GPU 0 仿真。
- 当时的 DM05 worker 与第二个 Hy-VLA 共用 04 GPU 0，仍受 GPU 准入限制。
- 两份 Hy-VLA 使用独立服务端口和客户端历史。按原 manifest 的 block 分组，
  两组 seed 不重叠；已完成半个 block 的剩余回合只分给一个 worker。
- 保留完整原 manifest 的哈希、全局 block 编号、checker、动作预算和推理参数。
  每个新回合仍执行父场景逐像素检查；初始化失败仍仅允许原 seed 的有限次重试。
- 显存准入、80°C 暂停至 74°C 的动作间降温，以及最终全量校验继续生效。

运行目录内 `support/hy-vla-sharding/` 保存分片配置、控制器快照、切换前后证据、
原 provenance 哈希、独立模型服务记录及新工作流。`plan.json` 记录此次调度变更，
每个分片回合另有 `_execution_shard.json`，可追溯 seed 所属实例。
新工作流在所有分片完成后继续调用原有校验、打包和 README 更新工具。

共享实现位于 [`remote_eval_support.py`](../tools/remote_eval_support.py)，保留 PID 身份核对、
显存预算、源码冻结和父场景检查。原 Attribute 单机双路 scheduler 已移除。
当前控制器与历史源码快照的哈希不同；新调度使用新配置和相应源码哈希，
历史冻结运行须使用原快照，不能绕过版本检查直接续跑。
