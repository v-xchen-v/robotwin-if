# 六任务正式评测

当前任务为 bottle_verb、pick_diverse_object、attribute_select、arm_select、stack_sequence、place_relative。
Grasp-Approach 已暂时下线，见 [归档说明](../bak/grasp_cube_approach/README.md)。
当前使用 [RoboTwin-IF Arm-only-v2 taskset](../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md)，
各 policy 460 回合，全套 **2760/2760 回合、720/720 blocks** 已于 2026-09-18 05:26 UTC 完成校验。
Arm 按 target-arm-only-lift-v2 重跑 240 回合，其他五任务复用 Attribute-v2 的 2520 回合。
[最新结果](../result/robotwin-if-arm-only-v2-20blocks/README.md)及 [远端推理/并发调度记录](arm-select-target-only-v2-evaluation.md)已归档。
正式 runner 的 `--release` 默认值指向该版本；当前分支只保留这份清单和结果，见[发布溯源说明](release-provenance.md)。
[新的 pick 稳定保持判定](bottle-verb-pick-hold.md)下，prepare 会排除旧 Bottle-Verb 结果并保留原 seed 重测；该轮重测现已完成。
当前 v6 的 pick 允许平移，在完整执行 700 个动作后判断末尾姿态保持和全程旋转摇晃；不再提前成功。shake 及其他任务保留原终止方式。

## 基础入口：单机串行

`tools/run_formal_policy_suite.py` 按 policy、task、seed 依次运行，只启动一个
simulator（GPU 0）和一个模型服务（GPU 1）。同一个模型跑完各任务后释放，再加载下一个模型。
六个 policy 的客户端、模型历史状态、checkpoint 校验与动作解码保持各自的官方协议。
当前 runner 的 Python/模型环境路径及两张 GPU 的配置面向本机，见脚本顶部常量。

每个新回合都执行完整 oracle qualification，通过后关闭场景，再用原 seed 重建 policy
场景。基础 runner 使用 RoboTwin 原生渲染和串行调度；任务本身的配对资格检查仍保留。
需要远端模型、并发 simulator 或 Hy-VLA 双实例时，使用 [Arm 重评说明](arm-select-target-only-v2-evaluation.md) 中的专用 controller。

X-VLA 首先建立参考场景。随后五个 policy 在调用模型前逐回合核对参考文件 SHA-256、
三路 RGB 逐像素相等、机器人状态绝对误差不超过 `1e-6`、指令及步数上限相同。
任何不一致都停止该回合；不会跳过检查或替换 seed。
SAPIEN 的显式设备绑定由仓库内 `tools/sim_device.py` 提供，无需加载旧运行目录中的 Python 适配器。

## 准备、续跑与验证

正式 runner 使用冻结的运行目录。`prepare` 会验证 release，保存源码/config/manifest
哈希及快照，按 release 的 `reusable-results.yml` 校验并复制已有结果。
`--old-run` 提供原来的每 policy/task `run.json`、resolved config 及
`support/services-before-recovery.json`，用于保留模型启动参数与 checkpoint 身份。
同时支持元数据保存在 `provenance/reused/<policy>/<task>/` 的正式归档目录。
这是一条已有正式评测的迁移/续跑入口；单独测试新模型可直接用 [policy evaluator](../policies/README.md)。

```bash
# 新运行需使用不存在的目录、匹配的 release 与模型运行元数据。
python tools/run_formal_policy_suite.py prepare \
  --run-dir /path/to/new-run --release /path/to/qualified-release \
  --old-run /path/to/matching-prior-run

# 启动或显式恢复该运行，使用 RoboTwin Python 环境。
python tools/run_formal_policy_suite.py run --run-dir /path/to/new-run

# 读取进度；验证当前已归档结果（verify 会更新 validation.json）。
python tools/run_formal_policy_suite.py status --run-dir /path/to/new-run
python tools/run_formal_policy_suite.py verify --run-dir /path/to/new-run
```

运行中新完成的文件先复制并校验 SHA-256，最后写入 `_provenance.json` 才计入完成。
成功和 policy failure 都是不可覆盖的完成结果。worker 始终读取完整 manifest，
仅跳过已归档的回合，所以在 block 中间恢复也保持原始 block 序号。
`batches/` 保留每次启动的原始输出、执行错误与 `*-resume.json`。

`summary.json`、`status.json` 和 `report.md` 在运行中每 15 秒更新。
缺任何回合的 block 都不算完整；每项的目标数量来自 manifest，不写死为 12 blocks。
完整校验还会检查动作 traces、跨 policy 的初始场景以及新视频帧数。
只有所有计划回合和完整 blocks 均通过校验，运行才标记 `complete`。

GPU 查询超时、温度达到 87°C、显存超限、日志停止更新或其他基础设施错误会停止运行并
清理本次启动的进程组。启动前要求两张 GPU 空闲，避免与其他任务叠加。
唯一的自动重试是尚未调用模型时明确的 oracle 资格阴性，且 GPU 健康检查通过：
新建 simulator 对同一个 seed 最多再试两次。次数跨重启保留；policy failure 不重跑，
GPU、网络、场景不一致及执行异常不走这个重试。

重构改变了 evaluator 的源码哈希。旧运行目录仍可读取和汇总，但不能直接用新源码继续
旧的冻结运行；重放历史运行应使用其源码/config 快照。新的运行需要新的冻结快照，
且复用结果的 checkpoint、场景、指令与动作配置必须匹配。
不同 evaluator 版本的耗时分开统计。X-VLA 官方接口不控制 server RNG，不能宣称推理逐位确定。

## 历史结果与当前六任务统计

历史七任务版本仅在 Git 历史中保留，六个模型各 540 回合，
全套 **3,240 回合、840 个完整 blocks**。从 12 扩到 20 时保留全部 1,944 条旧成功/失败结果，
新增 1,296 回合；seed 选择不参考 policy 成败。

结果入口在 [`result/`](../result/README.md)。当前 Arm-only-v2 六任务完整数据目录为
`/Data/robotwin-if/evaluations/robotwin-if-arm-only-v2-20blocks-001`，
repo 入口为同名的 `outputs/policy-eval/` 子目录。历史七任务目录
`/Data/robotwin-if/evaluations/if-seven-tasks-v2-wide-20blocks-001` 保留原判定和原始产物。

`tools/summarize_formal_policy_results.py` 读取单次 summary 快照，核对归档结果的 SHA-256、
provenance、mode 和计数，生成 Markdown、HTML、JSON 与分模式 CSV：

```bash
python tools/summarize_formal_policy_results.py \
  --run-dir /Data/robotwin-if/evaluations/robotwin-if-arm-only-v2-20blocks-001 \
  --output outputs/policy-eval/reports/results-current.md
```

每格显示 SR (%) 和成功数/纳入评分回合数，并附完整 blocks 与已完成/计划回合数。
SR 只使用完整、均衡的 blocks；半个 block 中已完成的回合仍计入进度，标为待成组。
未完成的任务均值标 `†`，没有完整 block 时用 `—`；未跑回合不当作 failure。
Attribute 的 Color/Decal/Shape/Size 各平均两个 target values，Task Avg. 对 modes 等权。
默认报告排除 grasp，进度分母为 2,760 回合/720 blocks/36 个 policy-task 组合。
Overall 仅在该 policy 六任务全部完成后显示，按六个 Task Avg. 等权平均。
如需还原原七任务统计，显式传 `--include-archived-tasks`；报告会标明七任务范围，分母恢复为 3,240/840/42。
新旧范围的 Overall 不直接比较；源 summary 与已发布的 `result/` 文件均不改写。

## 历史版本与归档

- 宽范围 grasp v2：x=[0,8] cm、y=[-8.5,-3.5] cm；12-block release 按三个 x 分层
  各选四个完整 blocks，20-block release 的分层数量为 7/7/6。旧窄范围结果仍需配套旧场景源码。
- VLAct All：`StarVLA/VLAct_Qwen3OFT_Robotwin_all_Finetune`，revision
  `999b37d4d7c1bd0f5588f78d72a185f6f052bf83`。2026-09-12 的七任务重跑替换旧 Clean 50K
  模型结果；20-block 扩展沿用 All checkpoint。
- 早期窄范围 12-block 套件复用了 276 条结果；两个已改场景任务的 48 条旧结果未复用。
  宽范围迁移、VLAct 替换和 20-block 扩展各自在对应运行目录保留 provenance。
- 历史加速阶段使用过多机分片、双 sim 与远端模型服务，双队列还有 80/72°C 暂停降温逻辑。
  两台主机曾测出 RGB 差异，因此历史任务的 sim 主机不能任意互换。
  双队列在 2026-09-14 因降温等待超时停止后恢复，全部结果最终于 2026-09-15 完成。

历史部署与代码保存在正式运行的 `support/source-snapshot/`、
`deployment/dual-queues-20blocks-001/code/` 和
`deployment/dual-queues-20blocks-001/recovery-20260914T080009/`。
本次清理前的完整相关源码及未提交 diff 另存于
`/Data/robotwin-if/evaluations/refactor-source-backup-20260915T065847Z/`。
历史工具仅用于还原旧运行，不再作为当前仓库的运行入口。
