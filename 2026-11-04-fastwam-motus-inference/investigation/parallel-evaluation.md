# 2026-11-05：Fast-WAM / X-WAM 双 server、双 sim 并行验证

## 动因与容量依据

用户先询问两张卡能否并行运行两个 server 和两个 sim，随后明确要求“试试”。此前每次只运行一套评测，模型 GPU 1、仿真 GPU 0，三个模型串行。

硬件为两张 RTX A6000，每张约 48 GiB；24 个物理 CPU 核 / 48 线程；主存约 62 GiB。模型采样显存：Fast-WAM 约 24 GiB、X-WAM 约 27 GiB、Motus 约 41 GiB。旧 X-WAM 完整运行的 4962 次资源采样中，仿真侧最高 11333 MiB（约 11.1 GiB），P95 8219 MiB，P99 10588 MiB。这些是已采样值，不是所有瞬时峰值的上界。

因此 Fast-WAM + sim、X-WAM + sim 分别约 35/38 GiB，有并行试跑空间。Motus + sim 可能超过单卡容量，本次仍安排在前两套结束后，模型和仿真分卡运行。X-WAM 旧启动主存 high-water mark 约 38.9 GiB，不能同时冷启动两个大模型；本次保留已加载 Fast-WAM，只启动 X-WAM。

## 执行方式与不可变条件

- 目标布局：GPU 0 为 X-WAM server + sim，GPU 1 为 Fast-WAM server + sim。
- 直接使用未完成的 manifest 回合；不为测试重跑已有 policy failure，不变更模型精度、checkpoint、动作解码、任务判据、动作预算或 seeds。
- 继承 [oracle 恢复规则](oracle-recovery.md)：仅对无模型请求的指定 oracle 错误换新仿真进程，每 seed 累计最多 8 次，旧归档错误继续计数。
- 每个模型/任务单独加 worker 文件锁；错误事件追加加文件锁；报告由唯一 coordinator 写入。
- 仿真按进程设置 `CUDA_VISIBLE_DEVICES`，检查 SAPIEN 实际 renderer 的 PCI 地址。GPU 1 的独立探针已返回 `0000:d8:00.0`，与 `nvidia-smi` 物理 GPU 1 一致；GPU 0 为 `0000:af:00.0`。
- 新 worker 支持回合边界停止。容量短跑的验收为两套实际同时运行后，各新增至少 2 个有效回合，记录显存/主存、保留结果哈希与逐回合 provenance。这个标准验证共存与资源使用，不证明 oracle 确定性或两倍吞吐。

## 调度接管与当前状态

07:47:42 UTC 新 coordinator **2499790** 接管。旧 coordinator **2422393** 单独停止，Fast-WAM server **2422395** 和旧 Arm worker **2493919** 保留原 PID，当前任务自然继续；没有杀掉正在执行的 policy episode。

接管时共 **590** 个有效回合已核对并生成 SHA-256 receipt。Fast-WAM 当前 Arm 任务自然结束后，新 sim 切到 GPU 1。X-WAM server **2499797** 开始在 GPU 0 加载；旧 Fast-WAM sim 仍在 GPU 0 时不会再启动 X-WAM sim，避免该卡同时驻留两个 sim。

初始状态是模型加载/旧任务收尾；尚不能宣称并行短跑已经通过。实时证据为：

- `/Data/robotwin-if/evaluations/wam-full-20261104/batch-status.json`：各 lane 的 server/worker PID、设备、进度及错误。
- 同目录 `parallel-20261105/trial.json`：短跑状态和验收数据。
- `parallel-20261105/resources.jsonl`：每 10 秒 GPU 显存/利用率/温度及可用主存采样。
- `parallel-20261105/takeover.json` 和 `retained-results-sha256.json`：接管来源和保留结果哈希。
- 执行源码：`/Data/robotwin-if/tmp/run-wam-parallel-20261105.py`、`wam-parallel-worker-20261105.py`，副本保存在 audit 目录。

## 控制测试

12 项测试通过：worker 的精确前缀续跑、policy failure 保留、模型请求/执行错误禁止重试、累计 oracle 上限、边界停止/恢复、每次新增回合限制、重复 worker 排斥、错误 renderer 绑定拒绝；coordinator 的 adopted worker 完成凭据检查、异常退出拒绝、oracle 重启凭据校验、停止后的 worker 不再启动。

测试文件和日志为 `/Data/robotwin-if/tmp/test-wam-parallel-{worker,coordinator}-20261105.{py,log}`；这些控制测试使用替身。真实两套同时执行是否可行，以 trial 与原始结果为准。

## 08:06 UTC：两套实际开始并行

旧 Arm worker 自然完成，Fast-WAM Arm 最终为 19/40（47.5%）。新 Sequence worker **2503819** 已绑定 GPU 1（renderer `0000:d8:00.0`），保留原 Fast-WAM server **2422395**。X-WAM 严格加载完成，server **2499797** 与 Sequence worker **2504124** 均绑定 GPU 0（renderer `0000:af:00.0`）。`nvidia-smi` 核对四个进程确实分布在上述两张卡，证据为 audit 目录的 `verified-placement.json`。

08:06:04 开始短跑计数，基线 Fast-WAM 280/X-WAM 325。Fast-WAM 首两回合为 100008 success（435 动作、144.83 秒）与 100009 failure（1200 动作、256.17 秒）。X-WAM 原阻塞 seed 100065 此次 oracle 通过，随后 policy 完整执行 1200 动作、38 个 chunk 后正常失败，耗时 503.57 秒；之前 5 次 oracle 错误仍保留，新的 provenance 显式记录这 5 次历史。

此阶段已经证实两套真实推理和仿真可同时执行；完整短跑验收仍需 X-WAM 第二个有效回合及产物复核。初始采样最大 GPU 0/1 为 33690/28958 MiB，启动至此最少可用主存 14673 MiB；正式短跑汇总以 `trial.json`、`validation.json` 为准。

## 08:22 UTC：短跑通过，08:26 UTC 产物核验完成

从 08:06:04 到 08:22:19，两套同时执行后新增 Fast-WAM **4** 个、X-WAM **2** 个有效回合，达到每套至少 2 个的验收要求。08:26 对两套最初各 2 个回合完成产物检查：

| 模型 | Seed | Policy 结果 | 动作数 | Chunk 数 | 回合耗时 |
| --- | --- | --- | --- | --- | --- |
| Fast-WAM | 100008 | success | 435 | 19 | 144.83 秒 |
| Fast-WAM | 100009 | failure | 1200 | 50 | 256.17 秒 |
| X-WAM | 100065 | failure | 1200 | 38 | 503.57 秒 |
| X-WAM | 100066 | failure | 1200 | 38 | 461.66 秒 |

四回合 oracle 均通过，无执行错误。动作数组长度与实际动作数一致、所有值有限；prediction 请求数与 chunk 数一致；三路初始相机图像为 240×320 RGB uint8 且非恒定图像。metadata 的 sim GPU、server GPU、实际 renderer PCI 均匹配分配，结果哈希与 provenance 一致。这里进行了数组/图像统计检查，没有宣称人工观看视频或逐像素对照旧画面。

切换前的 **590** 份有效 result JSON 再次核对 SHA-256，全部字节不变。短跑期间指定 oracle 错误档案没有新增，旧 X-WAM 5 次错误与 Fast-WAM Arm 的 1 次错误仍完整保留；正常 policy failure 不重跑。

资源采样：GPU 0 最大 **33690 MiB（32.9 GiB）**，GPU 1 最大 **28958 MiB（28.3 GiB）**；启动至验收时最低可用主存 **14673 MiB（14.3 GiB）**。没有 OOM 或触发资源保护。这些是本次采样边界，不是全任务的显存峰值保证。

前两个并行回合的推理 chunk 耗时中位数：Fast-WAM **0.694 秒**，X-WAM **1.729 秒**。先前串行样本分别约 0.678/1.694 秒。Fast-WAM 对照来自 Arm、当前为 Sequence，且 episode/模型结果不同；这里只支持单次推理没有明显退化，不用于声称严格两倍端到端加速。

**决定：继续 Fast-WAM/X-WAM 并行完成各自剩余 manifest，随后 Motus 分卡单独运行。** 08:26 快照为 Fast-WAM 285/460、X-WAM 327/460、Motus 0/460，共 612/1380；完整三模型 benchmark 仍未完成，oracle 底层稳定性仍未修复。

验收产物：audit 目录的 `trial.json`、`validation.json`、`resources.jsonl`、`verified-placement.json`、`serial-timing-baseline.json`。核验入口：`/Data/robotwin-if/tmp/assess-wam-parallel-20261105.py`，脚本和输出已归档；它只读评测产物，不生成替代成绩。

## 11 月 6 日：两模型剩余全量完成

Fast-WAM 于 11 月 5 日 17:42:30 UTC 完成 460/460，X-WAM 于 19:23:37 UTC 完成 460/460，期间没有资源保护中断。恢复 worker 处理了额外的 pre-policy oracle 失败；正常模型失败保留。两个服务随后退出，Motus 于 19:35 UTC 自动接续，使用 GPU 1 模型 / GPU 0 仿真。

11 月 6 日对两模型 920 条完整结果、64 个源文件/配置和 590 条切换前结果哈希完成核查；Overall 为 51.7361% / 42.3264%。完整分数、错误恢复次数、核验范围及未完成的 Motus 目标见 [完整结果](full-results-20261106.md)。并行可行性的验证已覆盖本次剩余任务，而不是只停留在短跑。
