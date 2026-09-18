# Attribute-v2 六策略重评

本轮使用修正后的 `target-only-lift-v2` 判据，重跑六个 policies 的 Attribute-Select。
干扰物在回合内任一物理子步抬升严格超过 5 cm 后，本回合永久失败；之后抓起目标不能恢复成功。
规则和三个历史动作回放案例见[判据说明](attribute-select-target-only.md)。

- Taskset：[robotwin-if-attribute-v2-20-per-mode](../seed-manifests/robotwin-if-attribute-v2-20-per-mode/README.md)
- 原始运行：`/Data/robotwin-if/evaluations/robotwin-if-attribute-v2-20blocks-001`
- 实时进度：[report.md](../outputs/policy-eval/robotwin-if-attribute-v2-20blocks-001/report.md)
- 工作流状态：[workflow.json](../outputs/policy-eval/robotwin-if-attribute-v2-20blocks-001/workflow.json)
- 完成后结果目录：`result-archive/robotwin-if-attribute-v2-20blocks/`
- 父结果：[cube-v3 六任务结果](../result-archive/robotwin-if-cube-v3-20blocks/README.md)

每项任务 20 blocks；每个 policy 的 Attribute 有 8 modes × 20 = 160 回合。
六个 policies 共 **960 新回合 + 1800 复用回合 = 2760 回合、720 blocks**。
队列顺序为 X-VLA、LingBot-VA、LingBot-VLA、VLAct All、DM05、Hy-VLA。
2026-09-17 12:10 UTC，04 的 GPU 0 在 VLAct 长回合内达到 86°C，触发硬保护，
停止队列。当时已有 **314 个新回合**，X-VLA 全部 160 回合完成；三个未完成回合为
LingBot-VA 100102、LingBot-VLA 100043、VLAct 100017。
仅在回合边界等待降温不足以防止长回合继续升温，因此恢复时在部署控制器加入动作间降温：
每 3 秒以内检查一次本卡温度，达到 80°C 后在调用下一个完整动作前等待，降至 74°C 后继续。
等待不调用物理步、不改动作、不重置模型；单次等待最多 10 分钟，86°C 硬保护保持不变。
每回合 `_thermal_pacing.json` 记录等待时间，原耗时指标包含这部分墙钟时间。
冻结的任务、evaluator、400-action 预算、初始场景检查和最终校验均保持原版。
此次恢复保留全部 2114 个完成结果的 provenance marker，只重启三个尚无完成结果的原 seed。
修复和恢复证据见
[`support/transitions/thermal-recovery-v1/`](../outputs/policy-eval/robotwin-if-attribute-v2-20blocks-001/support/transitions/thermal-recovery-v1/)。
恢复后三个原 seed 均完整运行到 400 步，初始观测全部字段、文件哈希、动作解码和 401 帧视频
均通过校验；原有 2114 个 marker 保持不变。VLAct 100017 实际触发了一次 80→74°C 降温，
等待约 11.2 秒后完成回合。对应 `first-results-validation.json`；温控与调度单元测试共 23 项通过。

2026-09-17 11:03 UTC 按用户要求将并发从两路增至最多 **3 个 server + 3 个 sim**。
04 的 GPU 0 运行一路仿真，GPU 1 最多运行两路；03 的 GPU 3 保留 X-VLA、LingBot-VA，
GPU 2 的空余显存用于 LingBot-VLA、VLAct、DM05、Hy-VLA 队列中的最多两个模型。
模型按队列逐个加载；每张远端卡的模型保留预算和实际显存准入上限仍为 44 GiB，
实际显存准入包含其他任务的占用。只在明确配置的 GPU 2 上允许与既有外部任务共享显存；
其他任务的进程、服务和文件不受本队列管理。模型固定到卡，仿真 lane 可以接续不同模型。
模型只监听远端 loopback，经 SSH 转发到本地 18010–18015 端口；每回合记录仿真与推理的主机、GPU 和控制器哈希。
原两路在 83°C 时于回合边界等待，降至 78°C 恢复。新增第三路只在低于 78°C 且留有 8 GiB
显存预算时启动，在 81°C 时于回合边界等待、降至 76°C 恢复，优先减轻共享卡负载。
本地单卡仿真的准入预算为 20 GiB；86°C 或显存达到 96% 时停止队列并保留结果。
此次切换保留 **211 个本轮新结果和 1800 个已导入结果**，两路均在回合边界停止后恢复，
未重跑完成结果、未中断回合、未修改任务或 evaluator。证据见
[`support/transitions/remote03-three/`](../outputs/policy-eval/robotwin-if-attribute-v2-20blocks-001/support/transitions/remote03-three/)。
三路首个新结果（X-VLA 100150、LingBot-VA 100085、LingBot-VLA 100000）的文件哈希、
初始观测全部字段、动作解码与视频帧数均通过校验，切换前 2011 个 provenance marker 保持不变。
已观测到第三路在回合边界暂停、降温后自动恢复。对应证据为该目录的
`first-results-validation.json`、`preservation-validation.json` 和 `thermal-observation.json`；
调度相关单元测试共 20 项通过。短时样本包含初始化和不同回合长度，不能据此认定固定加速倍数。

此前在 2026-09-17 10:38 UTC 接入 **msrait-03 推理 + msrait-04 双 GPU 仿真**，
最多 **2 个 server + 2 个 sim**；04 两张 GPU 各运行一路仿真，03 的 GPU 3 运行两路模型服务。

本次使用冻结后的新任务源码重新检查 03 的 Attribute 场景：状态和指令相同，RGB 存在差异，
因此 **不导入 03 上任何旧仿真结果，也不将本次远端场景诊断当作正式评测结果**。
04 的第二张 GPU 已重新验证全部 8 种 Attribute mode，初始 RGB 逐像素一致、状态误差不超过 1e-6。
正式 worker 每个回合继续执行同样的检查；判据、指令、seed、预算和 evaluator 源码保持冻结版本。
03 只复用已有环境和同版本模型权重；校验六个模型的运行库版本、checkpoint identity 和服务元数据。
独立下载的时间戳只作为来源记录，checkpoint revision、权重标识和推理参数仍要求一致。

切换在两个回合完成后进行，保留 **189 个本轮新结果和 1800 个已导入结果**，没有中断未完成回合，
没有重跑已完成的成功或失败。切换前所有 provenance marker 的哈希、原 plan/监督脚本/进程身份、
本轮重新执行的两机场景检查和跨机推理验证见
[`support/transitions/remote03/`](../outputs/policy-eval/robotwin-if-attribute-v2-20blocks-001/support/transitions/remote03/)。
恢复后两路均已完成首个新回合：X-VLA seed 100130、LingBot-VA seed 100075。
逐文件哈希、初始观测全部字段、动作解码和视频帧数均通过校验；切换前 1989 个 provenance marker 保持不变。
证据为该目录的 `first-results-validation.json`；全量校验和打包仍在队列结束后执行。

此前在 2026-09-17 07:07 UTC 按用户要求切为本机最多 **2 个 server + 2 个 sim**：
GPU 0 运行两个 simulator，GPU 1 运行两个模型服务。checkpoint 逐个加载，模型组合的显存预算上限为 44 GiB，
其预算按此前实测峰值向上取整；若组合超限则等待或先选能容纳的下一项。
温度达到 83°C 时，第二路会在下个回合开始前等待降温，降至 80°C 后恢复。
86°C、显存达到 96% 或其他基础设施异常会停止队列，保留已完成结果。

切换时直接接管原 X-VLA server 和 sim，仅替换监督进程，没有重启模型或中断回合。
[切换记录](../outputs/policy-eval/robotwin-if-attribute-v2-20blocks-001/support/transitions/serial-to-parallel2/transition.json)
保留原 plan、监督脚本、进程身份与新拓扑哈希；任务和 evaluator 源码保持 prepare 时的版本。

首次并行启动时，LingBot-VA seed 100000 在推理前因状态编码维度不匹配被拦下，调度器停止了两路。
修正为统一的父 X-VLA 20D 参考后恢复运行；此前 25 个新结果和 1800 个复用结果均保留。
停止时 X-VLA seed 100025 运行到第 204 个动作，尚无完成判定，因此恢复的是该未完成 seed。
错误记录、原调度器源码和恢复原因保存在
[`support/execution-revisions/parallel2-v1/`](../outputs/policy-eval/robotwin-if-attribute-v2-20blocks-001/support/execution-revisions/parallel2-v1/recovery.json)，
并计入结果包 plan 的 `execution_recoveries`。

六份 flat manifest 与 cube-v3 逐字节相同。其他五任务保留所有成功和失败记录、视频与动作文件，
导入时核对全部 artifact SHA-256。Arm 使用 `demo_clean_arm_select_v3` 的 5 cm cube，
Bottle 使用 v6 terminal 判据，Spatial 保留 left/right/on_top。
共享 `_if_grounding.py` 只新增 Attribute monitor，旧代码的 AST 完全不变；
其余任务、策略和运行时文件的哈希保持原版。具体见[复用审计](../seed-manifests/robotwin-if-attribute-v2-20-per-mode/reuse-audit.json)。

Attribute 仍用 `demo_clean`、400-action 预算、unseen 指令，以及原始 checkpoint 和推理参数。
正式运行前执行双目标 oracle gate。普通 oracle-negative 只可在推理开始前用同一 seed 重试，
总计最多三次 setup；不替换 seed，不重跑已完成的 policy 成功或失败。
其他运行错误会停止队列并保留日志。

并行 worker 在推理前核对父结果中 X-VLA 相同 seed 的初始 RGB、指令和位姿，
统一使用其 20D 状态编码作为参考，避免各 adapter 的 16D/14D 编码差异；
只读取父回合的场景证据，不复用旧 Attribute 判定，也无需等待本轮 X-VLA 跑到该 seed。
运行完成后，工作流仍校验所有记录与动作解码、本轮跨 policy 初始 RGB/指令/位姿，以及新视频帧数。
打包时还核对 960 个新回合的初始观测与父结果相同、1800 个复用回合的 CSV 字段与记录哈希相同，
并输出逐回合 Attribute 新旧结果、干扰物抬升信号和 oracle 重试证据。
最后从完成结果生成 HTML/Markdown/CSV/JSON 报表，并更新根 README 与结果索引。
新旧 Attribute/Overall 差异同时包含判据变化与重新推理的影响。

使用 RoboTwin Python，独立目录中的复现入口为：

```bash
python tools/run_formal_policy_suite.py prepare \
  --release seed-manifests/robotwin-if-attribute-v2-20-per-mode \
  --old-run /Data/robotwin-if/evaluations/robotwin-if-cube-v3-20blocks-001 \
  --run-dir /Data/robotwin-if/evaluations/<new-run>
python tools/run_formal_policy_suite.py run --run-dir /Data/robotwin-if/evaluations/<new-run>
python tools/release_attribute_select_v2.py package \
  --run-dir /Data/robotwin-if/evaluations/<new-run> --result result/<new-package>
```

当前队列由运行目录的 `support/run-and-package.py` 管理，评测阶段使用
[`tools/run_remote_attribute_suite.py`](../tools/run_remote_attribute_suite.py)，随后执行打包和 README 更新。
本次部署配置为运行目录的 `support/remote-msrait03.json`，其中锁定控制器哈希、两机路径、SSH socket 和 GPU UUID。
恢复远端队列前需保证配置中的 SSH ControlMaster 连接可用；密码未写入部署配置。
原 [`tools/run_parallel_attribute_suite.py`](../tools/run_parallel_attribute_suite.py) 保留不变，
其 `support/parallel-source-hashes.json` 校验以及所有任务、evaluator 和 manifest 哈希校验继续生效。
上方复现命令保留原串行入口。
`workflow.json` 的 `status=complete` 表示三个阶段均已完成；仅 `status.json` 完成时仍可能在打包。
源码、配置和 manifest 在 prepare 时冻结；不要在运行中修改这些文件。
