# 2026-11-05：完整评测的 oracle 中断与同 seed 恢复

## 已有结果与中断

首次恢复停止时的有效结果快照：X-WAM 共 325/460 回合，Fast-WAM/Motus 尚未开始完整运行。下文成绩是该时点快照；后续动态进度读取完整运行目录的 `batch-status.json` 和 `progress.json`。

| 已完成任务 | 成功数 / 回合 | Task Avg. |
| --- | --- | --- |
| press_lift_stapler | 34/40 | 85% |
| pick_diverse_object | 29/40 | 72.5% |
| attribute_select | 81/160 | 50.625% |
| arm_select | 4/40 | 10% |

`stack_sequence` 有 45/120 个有效回合，`place_relative` 尚未开始；不能给出六任务 Overall。Sequence 已完成回合的耗时中位数为 448 秒，动作数中位数为 1200，长耗时主要对应完整动作预算，不等同于挂起。

11 月 5 日 02:16:49，`stack_sequence/100065` 在 `episode_setup` 阶段抛出 `Exact seed failed oracle qualification; no seed substitution`。模型 instruction 为 null，动作数、chunk 数均为 0，requests 为空。02:16:58 监督进程发现无效回合后停止整批并关闭模型服务。该项是基础设施 / oracle 错误，不是 X-WAM 的 policy failure。

原始中断状态、报告和错误产物均保存在 `/Data/robotwin-if/evaluations/wam-full-20261104/recovery-20261105/`。旧的进度快照为 324 个回合；最后一个正常回合结束后有效总数实际为 325。

## 首次恢复前的排查证据与边界

- 当前 task、task config、共享 evaluator 与原始运行的 SHA-256 一致；完整源码快照中所有 Python、Shell、JSON、YAML 文件的哈希也一致。没有用本次修复修改模型推理、动作转换、任务判据、动作预算或 manifest。
- 用同一环境和原配置，在新进程内对 seed 100065 连续重建场景并运行三次 oracle。三次初始物体位置逐项一致，结果分别为 `(plan=True, success=False)`、`(False, False)`、`(True, True)`。记录见 [三次 probe](oracle-seed100065-probe.json)；原日志为 `/Data/robotwin-if/tmp/stack-seed100065-probe-20261105.log`。
- 旧 X-VLA 运行 `/Data/robotwin-if/evaluations/if-seven-tasks-v2-12blocks-001/batches/20260910T063929/` 的同一 seed 也曾在模型调用前失败；`20260910T063929-retry-002/` 中同 seed 的 oracle 通过，随后 policy 正常失败。旧运行有不同的 render-sync 实现，仅作为该现象早于本次 WAM 接入的证据，不用于复用其资格或成绩。
- 证据说明同 seed 的 oracle 执行不稳定。尚未将底层原因进一步归于规划器随机性、缓存状态或物理仿真的某个具体组件，不声称已修复底层 oracle。

## 首次恢复规则（已停止，5 次上限）

本机恢复入口为 `/Data/robotwin-if/tmp/run-wam-recovery-20261105.py`，worker 为 `/Data/robotwin-if/tmp/wam-recovery-20261105.py`，两份执行源码已复制到上述 recovery 目录。

1. 检查已有记录必须是 manifest 的精确前缀，逐条与结果 JSON、任务 mode、oracle qualification 对齐；保留全部正常 success/failure。
2. 仅允许特定的 oracle qualification 错误、且 instruction 为 null、动作/chunk 数为 0、没有 policy request 时重试。每个固定 seed 最多 5 次 oracle 尝试，包含已归档的第一次失败；所有模型使用相同限制。
3. 错误产物移动到 `oracle-errors/<policy>-<task>-<seed>-attempt-NN/`，保存原索引/summary/run、逐文件哈希和事件索引。错误不计入成功率，也不冒充 policy failure；保留完整历史供追踪。
4. 从第一个未完成的 seed 继续。当时为 X-WAM `stack_sequence/100065`，原有 325 个有效结果全部保留，不重跑已完成的模型失败，不换 seed、不跳过后续 mode。
5. 其他错误或 oracle 尝试耗尽仍然停止；任务与模型只有收齐完整原始 manifest 才标记完成。每个新回合的 provenance 指向本次 worker 元数据和结果哈希。

CPU 验证覆盖前缀/顺序拒绝、禁止重试 policy failure、连续两次 oracle 错误的无损归档、有效失败字节不变、summary 的未完成语义，以及已调用模型时拒绝重试。原始 325 个有效结果已通过哈希核对，索引为 `retained-results-sha256.json`。

03:02 UTC 首次恢复监督进程 PID 2416800 启动。X-WAM 服务成功加载，但 seed 100065 连同原失败累计 5 次 oracle 均失败，03:15:27 整批再次停止，模型和 worker 已退出。5 份错误产物完整保存在 `recovery-20261105/oracle-errors/xwam-stack_sequence-100065-attempt-01` 至 `-05`；均没有 policy 请求。有效结果仍为 325 个，Sequence 索引只含 45 个有效回合。

## 用户追问：oracle 为什么看起来与模型有关

用户指出 oracle 应独立于被评测模型。该判断正确：oracle 的目标、场景与成功判据没有使用 X-WAM 输出，但当前实现没有隔离跨回合规划器状态。

代码链路：

1. `envs/_base_task.py:384` 的 `load_robot()` 在首轮构建 Robot，后续只调用 `Robot.reset()`。
2. `envs/robot/robot.py:124` 在单进程 CuRobo 路径重建 articulation，但复用已有 planner，不调用其 reset。运行时实测 `communication_flag=False`。另一条 planner 子进程路径虽然 reset `motion_gen`，也没有 reset `motion_gen_batch`；本次使用的不是该路径。
3. `envs/_base_task.py:1559` 的 EE 动作调用与 oracle 相同的左右 `plan_path()`；qpos 使用 TOPP。X-WAM 使用 EE，Fast-WAM/Motus 使用 qpos。
4. CuRobo 的 IK 采样器维护独立 `torch.Generator`，在 `curobo/util/sample_lib.py:414` 定义；仅设置 Python/NumPy/Torch 全局 seed 不会复原该 generator 的当前状态。

因此存在 **前一轮 policy 的 EE 规划 → 持久化的 planner 状态 → 下一轮 oracle** 的依赖链。它不是模型直接参与 oracle，也不是当前 adapter 按模型名更改 oracle 判据。

### 本轮实验

- 先前独立的新进程直接调用真实共享 `setup_episode()`，100065 首次通过 oracle 和 policy scene setup，无模型请求。证据：`/Data/robotwin-if/tmp/stack-seed100065-shared-setup-20261105/results.json`。
- 新诊断使用当前完整运行的相同 resolved config，无模型服务、无 policy 请求、不写成绩目录。执行 seed 100065 的 8 次 oracle，初始三个物体的位置和姿态逐项相同。
- 原样复用 planner 的 4 次结果：成功、失败、失败、失败。
- 每轮 oracle 前显式 reset 左右两臂的 `motion_gen` 与 `motion_gen_batch` 的 4 次结果：失败、失败、成功、失败。记录到的 IK generator 初始状态哈希一致，但规划轨迹哈希不一致。**不能声称 reset 已恢复完全确定性，也不能将全部失败归因于已证实的状态串扰。** 尚有未隔离的数值/规划/仿真状态来源。
- 实际调用一次保持当前目标的 qpos 动作：四个被监测的 IK generator 均未改变。调用一次 EE 动作：左右 `motion_gen` 的 IK generator 均改变；随后重建 scene，两个变化后的状态完整保留。它直接证明执行器到下一轮 oracle 的状态通路，尚不能量化该通路对完整成功率的贡献。
- 旧 X-VLA 同 seed 也曾 oracle 失败、后续重试通过，因此“其他模型都没这个问题”不符合已有日志。旧运行有不同 render-sync 代码，不当作完全相同环境的对照。

可复用证据：[诊断脚本](oracle-planner-isolation-probe.py)、[结果摘要](oracle-planner-isolation-summary.json)。完整原始状态/轨迹哈希：`/Data/robotwin-if/tmp/oracle-planner-isolation-20261105/results.json`；日志在同名前缀 `.log`。诊断没有修改 RoboTwin、共享 evaluator、模型输出或 manifest。

## 后续恢复：新仿真进程，不宣称底层已修复

`20261105b` 的候选脚本没有启动。根据状态串扰证据，改为 `20261105c`：

- 先 Fast-WAM → Motus，再补 X-WAM，继续相同 manifest 与相同输出根目录。
- 每次指定的 pre-policy oracle 错误归档后，worker 以 75 退出；监督进程保持模型服务，创建新的仿真进程，从精确 manifest 前缀继续。其他错误仍停止，正常 policy failure 不重跑。
- 全模型统一每 seed 累计最多 **8 次** oracle 尝试，包含旧的归档失败；100065 已使用 5 次，最多再尝试 3 次。这个上限是本次本机恢复的操作限制，不是新的任务判据，也不是解决非确定性的证据。
- 保留原 evaluator/任务/动作预算，未将诊断中的 planner reset 补丁用于成绩。该恢复改变了失败后的进程生命周期，记录在每个 worker 的 metadata/provenance；不能描述为完全相同执行历史。
- 新增 4 项恢复控制测试通过：pre-policy 错误后退出/精确续跑且保留旧 policy failure 字节；跨进程累计次数上限；存在模型请求时禁止重试；policy 执行错误禁止重试。测试使用替身，不证明真实 oracle 稳定性。

入口：`/Data/robotwin-if/tmp/run-wam-recovery-20261105c.py`；worker：`/Data/robotwin-if/tmp/wam-recovery-20261105c.py`。源码、启动前快照及新保留结果 receipt 在 `recovery-20261105c/`；错误档案仍追加到原 `recovery-20261105/oracle-errors/`，没有重置历史次数。

新监督进程 PID 2422393 已启动。实时阶段和是否仍存活以 `batch-status.json`、实际进程和 `progress.html` 为准；启动恢复不等于已取得剩余结果。P6 的底层稳定性与严格模型独立性仍未解决。

## 07:29 UTC：第一次真实自动恢复通过

Fast-WAM 已完成前三任务：Press/Lift 38/40（95%）、Pick 26/40（65%）、Attribute 90/160（56.25%）。Arm 前 8 个有效回合中 4 次成功。Fast-WAM 总计 248/460，X-WAM 保留 325/460，Motus 尚未开始。

Arm seed **500007** 在旧 worker PID 2491828 中 oracle 失败：instruction=null、actions=0、chunks=0、requests=[]。错误归档到完整运行根目录下 `recovery-20261105/oracle-errors/fastwam-arm_select-500007-attempt-01/`，11 份归档文件的 SHA-256 已重新核对。

监督进程 07:27:00 收到退出码 75，07:27:03 创建新 worker PID 2493919，模型服务 PID 2422395 未更换。相同 seed 的 oracle 在 35.93 秒后通过；随后 policy 执行 400 个动作、17 个 chunk，最终是正常 `failure/action_limit`，已计入有效结果且没有重跑。

新结果：`fastwam/arm_select/arm_select_ep500007_result.json`；相邻 `_provenance.json` 记录 `oracle_errors_before_policy=1`，指向 `recovery-20261105/workers/fastwam-arm_select-20261105T072705/run.json`。此时索引严格保留 seeds 500000–500007 的顺序。

这个真实案例支持“仅恢复模型调用前错误且保留模型正常失败”的机制已经工作，并进一步证明 qpos 模型也会遇到 oracle 波动；不证明规划/物理仿真的底层非确定性已经解决。

## 08:14 UTC：X-WAM 原阻塞 seed 已恢复为正常 policy 结果

用户随后授权 Fast-WAM/X-WAM 两套并行短跑，详见 [并行调查](parallel-evaluation.md)。新的 X-WAM Sequence worker `2504124` 在 GPU 0 对原 seed **100065** 重新执行 oracle，此次通过；随后 policy 执行完整 1200 动作/38 个 chunk，结果为正常 `failure/action_limit`，总耗时 503.57 秒。

结果位于 `xwam/stack_sequence/stack_sequence_ep100065_result.json`，相邻 provenance 指向 `recovery-20261105/workers/xwam-stack_sequence-20261105T080605/run.json`，并记录 `oracle_errors_before_policy=5`。旧五份错误档案保留；这次是第六次 oracle 尝试、第一次 policy rollout。没有因模型最终失败而重跑。原中断 seed 的恢复已得到真实证据，底层 oracle 确定性仍未修复。

## 11 月 6 日：两模型完整结果中的 oracle 恢复汇总

Fast-WAM 最终 460/460，累计 10 次 pre-policy oracle 失败；X-WAM 最终 460/460，累计 7 次。Fast-WAM 的 Sequence/100065 连续 6 次失败后，第七次 oracle 通过；X-WAM 的 Place/100030 也曾连续两次失败。每个错误的请求记录均为空、归档哈希完整，所有相关 seed 最终均产生 oracle 通过后的正常 policy 结果，统一 8 次累计上限未被突破。

这些恢复保留了原 seed 清单和全部正常 policy failure，支持全量完成；它们不证明底层规划/仿真完全可复现。详细 seed/次数清单和核验结果见 [完整结果](full-results-20261106.md) 及运行根目录 `completed-models-audit-20261106.json`。
