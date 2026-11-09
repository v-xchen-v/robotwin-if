# Fast-WAM、Motus 与 X-WAM：开源 WAM 推理接入与评测

首次记录：2026-11-04。目标项目：`robotwin-if`。本文件在实现开始前根据用户请求建立，后续沿用本目录更新。

## 1. 最初为什么做

用户希望在现有 RoboTwin IF benchmark 中增加 Fast-WAM 和 Motus 两个开源 WAM 的测试结果，并要求从 release1030 分支创建新的开发分支，开发 inference code。当前项目已提供六个 policy 的推理与正式结果入口，但尚无这两个模型的适配器，无法通过现有入口取得它们的同口径结果。

原始来源：2026-11-04 本次对话，用户明确提出“我想要加另外两个 wam 的 opensource 的 model 的测试结果”，并要求“用 release1030 分支 checkout 一个新的分支，做 inference code 开发”。以下模型与权重地址由用户提供；补全的 Qwen、Wan 官方组织名已从 Motus 官方 README 核对。

| 模型或依赖 | 用户指定来源 | 初始用途与边界 |
| --- | --- | --- |
| Fast-WAM 源码 | <https://github.com/yuantianyuan01/FastWAM> | 核对官方 RoboTwin 推理路径与动作约定 |
| Fast-WAM 官方 RoboTwin 权重 | <https://huggingface.co/yuanty/fastwam> | 指定 `robotwin_uncond_3cam_384.pt` 与 `robotwin_uncond_3cam_384_dataset_stats.json` |
| Fast-WAM LeRobot 格式权重 | <https://huggingface.co/lerobot/fastwam_robotwin_uncond_3cam_384> | 用户提供的另一格式来源；与官方格式的等价性、是否需要两套后端尚待核对 |
| Motus 源码 | <https://github.com/thu-ml/Motus> | 核对官方 RoboTwin 推理路径与动作约定 |
| Motus RoboTwin 权重 | <https://huggingface.co/motus-robotics/Motus_robotwin2> | Stage 3 RoboTwin checkpoint |
| Motus Stage 1 VGM | <https://huggingface.co/motus-robotics/Motus_Wan2_2_5B_pretrain> | 用户明确列为还需下载的依赖 |
| Qwen3-VL-2B-Instruct | <https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct> | Motus 的 VLM 依赖 |
| Wan2.2-TI2V-5B | <https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B> | Motus 的基础模型资源；Fast-WAM 对 Wan 组件的需求待核对 |

期望改善：两个模型能够使用本项目的实际指令、观测与固定 seed 运行推理，按现有任务判据保留成功、失败与基础设施错误的区别，并留下可定位模型版本、配置和逐回合证据的评测结果。用户没有指定预期成功率、相对排名或性能提升阈值，不预设两个模型的效果。

已知范围：在新分支开发推理接入；沿用 release 分支的任务与评测基线。没有提出重新训练或微调模型的需求。完整评测覆盖、执行顺序，以及 Fast-WAM 两种发布格式是否都需要运行，尚未由用户明确指定；实施时先依据现有评测契约和官方加载路径核对。

## 2. 当前问题与结果

当前目标：为 Fast-WAM、Motus 与后来加入的 X-WAM 建立可复现的 inference 接入，按用户已明确要求的完整 seed manifest 运行六任务评测。用户随后要求在全量运行之前先补齐 X-WAM；因此先完成该接入和真实验证，再继续全量评测。2026-11-05 用户进一步要求试跑两套 server/sim 并行；本阶段验证 Fast-WAM/X-WAM 并行，Motus 在前两者结束后分卡运行。

代码基线与开发位置：

- 基线为远端 **分支** `refs/remotes/origin/release-20261030`，提交 `57cb69cf8174cda61a2ecc5d8773b7c79ec36ca6`。
- 开发分支为 `feat/fastwam-motus-inference`，已在现有 checkout 创建并切换。
- 仓库同时存在同名 `release-20261030` tag，指向不同提交；本次使用用户要求的分支，未从 tag 建分支。
- 本文属于独立 notes 仓库的 `notes/vibe-coding` 分支；主项目的 `justfile` 配置为 `notes_dir := "notes"`。记录请求不代表远端推送授权。

| 问题 | 来源 | 期望改善 | 当前判断 | 证据与边界 | 下一步 |
| --- | --- | --- | --- | --- | --- |
| P1：Fast-WAM 尚未接入现有评测 | 最初 | 官方 RoboTwin 权重能够经本项目入口推理并保存结果 | 已解决接入缺口，六任务真实评测完成 | 官方模型完整参数检查和 pilot 通过；原 manifest 的 460 条结果全部保留 | 完整效果与证据见 P3 |
| P2：Motus 尚未接入现有评测 | 最初 | RoboTwin checkpoint 与基础依赖加载完整，能够执行本项目任务 | 已解决接入缺口，六任务真实评测完成 | Stage 3 参数检查和 pilot 通过；所需资源校验完成，原 manifest 的 460 条结果全部保留 | 完整效果与证据见 P3 |
| P3：缺少新增模型的同口径测试结果 | 最初两个模型，随后扩展为三个 | 固定任务、seed、指令与成功判据下取得可复查的逐回合结果 | 已完成本次三模型六任务评测与结果核查 | 11 月 6 日 20:21 UTC 全部完成，11 月 9 日核查 1380/1380；Fast-WAM/Motus/X-WAM Overall 为 51.7361%/53.0556%/42.3264%，详见 [完整结果](investigation/full-results-20261106.md) | 已合并并推送至 release-20261030；当前 result/ 与 Azure 包覆盖九模型、4140 回合，原六模型记录和旧备份保留 |
| P4：解码观测数组不可写 | 实现后首次真实预测发现；本适配器传输引入 | 官方 Torch 预处理获得安全、可写的观测副本 | 已解决 | 初次 Fast-WAM 预测出现不可写 NumPy 警告；服务端改用校验后的自有副本，回归断言及后续两模型完整回合通过 | 无当前阻塞；保留首次运行与修复证据 |
| P5：X-WAM 尚未接入现有评测 | 2026-11-04 用户后续增加 | 在全量评测前，接入官方 RoboTwin SFT 权重及末端位姿动作接口 | 已解决接入缺口，六任务真实评测完成 | 完整 SFT 严格加载、官方 codec 对照及真实 pilot 检查通过；原 manifest 的 460 条结果全部保留 | 完整效果与证据见 P3 |
| P6：固定 seed 的 oracle 偶发失败中断整批，原 launcher 不支持恢复 | 2026-11-05 全量过程中发现；旧 X-VLA 也有同 seed 失败记录 | 无损保留正常结果，使用原 seed 继续评测并保留错误证据 | 本批恢复目标已实现，底层稳定性未解决 | Fast-WAM/Motus/X-WAM 共 10/5/7 次 pre-policy oracle 错误，22 份归档核验通过且原 seed 均完成，含最终通过的尝试数均不超过 8 次；正常 policy failure 保留。EE 状态通路已证实，reset 不足以消除全部波动 | 保留恢复证据；底层独立性与确定性为后续调查范围，不把本批完成当作根因修复 |
| P7：两张 GPU 能否并行评测两套模型以缩短全量耗时 | 2026-11-05 用户询问资源利用后明确要求“试试”；不是已证实的功能故障 | 两套 server/sim 独立绑定设备并稳定执行，保持已有成绩和评测契约 | 已完成并行短跑及两模型剩余全量运行 | 两套剩余任务于 11 月 5 日 17:42/19:23 UTC 完成，无资源中断；590 个原有结果哈希不变。短跑的动作/图像/设备绑定检查通过；不声称严格两倍加速 | Motus 后续分卡运行也已结束，GPU 已释放；资源边界见 [并行调查](investigation/parallel-evaluation.md) |

实际运行环境：两张 RTX A6000（各约 48 GiB 显存），模型 GPU 1、仿真 GPU 0。独立模型环境位于 `/Data/robotwin-if/envs/robotwin-if-{fastwam,motus,xwam}`。Fast-WAM/Motus 的 34 个官方资源文件共 76,556,365,026 字节，以及后续新增的 X-WAM 三个资源文件（主权重约 38.9 GB），位于 `/Data/robotwin-if/checkpoints/wam`，均已校验，历史 receipt 分别保留。三模型观察到的显存占用约 24 / 41 / 27 GiB。首次 X-WAM 全量和第一次恢复均已停止。03:31 UTC 的串行恢复队列在 07:47 UTC 被并行 coordinator 接管；08:22 UTC Fast-WAM/X-WAM 双 server/sim 短跑通过，两套分别于 17:42/19:23 UTC 完成。Motus 于 11 月 5 日 19:35 UTC 开始真实评测，11 月 6 日 20:21 UTC 完成全部 460 回合。11 月 9 日核查时所有评测进程已退出、两张 GPU 已释放；最终报告与审计保存在同一运行目录。

源码契约、真实回合结果和本机证据位置见 [调查与验证入口](investigation/README.md)。推理开发、真实 pilot 与完整六任务评测均已完成，最终审计与报告于 11 月 9 日更新。Fast-WAM 官方与 LeRobot 格式的等价性仍未核对；本轮采用官方 `.pt` 与官方 processor，LeRobot 保留为替代来源，未下载或宣称兼容该格式。

全量评测与动态进度位于 `/Data/robotwin-if/evaluations/wam-full-20261104/`。详见 [X-WAM 接入与全量运行记录](investigation/xwam.md)。原有六模型正式结果包未改动。

2026-11-05 的中断原因、四项完整成绩及恢复过程见 [oracle 恢复记录](investigation/oracle-recovery.md)。原监督进程于 02:16 UTC 停止，第一次恢复于 03:15 UTC 耗尽尝试后停止。03:31 UTC 新监督进程 PID 2422393 开始加载 Fast-WAM，继续同一结果目录。

## 3. 过程与回顾

### 2026-11-04：建立初衷与开发分支

- 根据用户原始请求记录两个 WAM 的来源和预期交付；动因是增加模型评测覆盖，没有已知故障或量化性能目标。
- 核对 notes 目录约定与已有文档，未发现同一 Fast-WAM/Motus feature 的记录，首次建立本目录。
- 明确区分同名 release 分支与 tag；从分支提交 `57cb69c` 创建 `feat/fastwam-motus-inference`，并核对与最新远端分支一致。
- 阅读现有 policy 总览及两份官方 README，确认需要继续核对模型与评测接口。尚未开发新适配器、下载权重或取得模型运行结果。
- 初衷没有调整；目前没有足以确认的新缺陷。上表中的 P1、P2、P3 均保留未解决状态。

### 2026-11-04：初版适配与 CPU 验证

- 在开发分支增加两个 policy 的安装、下载、服务、客户端和 evaluator 入口，沿用 release 的 seed、指令、oracle qualification 与终态判据；扩展结果汇总及视频复核的模型识别。
- 选择 Fast-WAM 官方 `.pt` 推理路径。该选择是本轮实现方案，不代表用户要求已经缩减，也不宣称 LeRobot 格式完成支持。
- 10 项新增 WAM 检查、8 项便携入口检查、4 项结果范围检查、11 项视频复核检查通过；它们使用 CPU/测试模型，不能证明真实模型性能。
- Fast-WAM 官方图像/状态/动作预处理检查通过；通过 meta/FakeTensor 检查确认官方 checkpoint 覆盖当前架构的全部 1649 个 MoT tensors 与 2 个 proprio tensors，形状匹配。模型环境 `pip check` 与官方模块导入通过。
- 本机资源实际沿用 `/Data/robotwin-if`：环境位于 `envs/robotwin-if-fastwam`、`envs/robotwin-if-motus`，模型位于 `checkpoints/wam/<owner>/<repo>`。Fast-WAM checkpoint 已校验；其他下载和 Motus 环境配置仍在进行。
- 新核对到的依赖差异：Motus 推理说明中的“config/tokenizer”不能理解成无需 Wan 权重；加载代码还需要 T5 与 VAE。Stage 3 提供 finetuned backbone，Stage 1 仍按用户资源清单下载。该事实属于接入调查，不是已经证明的模型缺陷。
- 本阶段没有产生新模型的任务成功率，P3 保持未解决；P1/P2 仅按实际完成的工程部分更新为部分解决。

### 2026-11-04：真实模型与配对回合验证完成

- 完成全部官方模型和基础资源下载、对象哈希校验，以及两套环境的依赖和官方模块导入检查。原始资源清单与增加评测覆盖的动因没有改变。
- Fast-WAM 首次真实观测预测返回有限值的 32×14 动作。随后发现并修复 P4 的只读数组传输问题，重新启动服务完成验证；没有改变官方预处理或动作数值约定。
- 使用 release 首个 `press_lift_stapler` block，seeds 110000/110001，分别运行 `Press down on the stapler.` 与 `Lift the stapler.`。Fast-WAM 在 58/79 步成功，Motus 在 29/26 步成功；四个回合均通过 oracle qualification，无 execution error。
- 完整预测、执行前缀、实际动作与视频帧数已核对，结果保存在 `/Data/robotwin-if/evaluations/fastwam-motus-pilot-20261104/`。汇总工具对每个模型显示 2/460，Overall 留空；没有改写原有六模型正式结果包。
- P1/P2 的推理接入缺口已有真实运行证据；P3 只取得局部结果，完整六任务评测与发布仍待后续推进。两套模型服务已停止；本轮没有提交或推送代码及 notes。

### 2026-11-04：用户明确全量评测，并要求先加入 X-WAM

- 用户追加“先跑一下我们 full task 的成绩，follow seed manifest”，已明确全量评测范围。核对 `seed-manifests/20-blocks` 的六任务及 bridge：每模型 460 回合，清单顺序与源码均匹配；尚未启动全量运行。
- 随后用户要求“在跑全部之前”查看并增加 X-WAM inference code。这是原评测目标的范围扩展与执行顺序调整，保留 Fast-WAM/Motus 的全量待办。
- 新来源：<https://github.com/sharinka0715/X-WAM>、<https://huggingface.co/sharinka0715/X-WAM-checkpoints> 的 `robotwin_sft/`、<https://huggingface.co/datasets/sharinka0715/X-WAM-RoboTwin>。
- X-WAM 使用原生 EE 位姿和相对 xyz/axis-angle/gripper 动作，需要独立 codec；不能把 14D delta 动作当成 14D qpos。现已实现坐标变换、逐步累积和 16D EE 执行入口，详细依据见 [X-WAM 接入记录](investigation/xwam.md)。
- 官方 checkpoint 配置已提供归一化统计；本轮推理不依赖完整训练数据，因此只核对数据说明，不下载训练集。SFT 主 checkpoint 约 38.9 GB，正在下载；复用已校验的 Wan 资源。

### 2026-11-04：X-WAM 真实验证完成，开始全量评测

- X-WAM 独立环境、完整 checkpoint 和所需 Wan 资源均已验证；严格加载完整 SFT module 成功。采用 CPU 先转 BF16 再移至 GPU，以及 CPU mmap checkpoint，降低启动内存占用，不改变最终参数精度或推理算法。
- 相同首个 block 的真实结果为 Press failure / Lift success（250 / 85 个动作），两个回合均通过 oracle qualification，无 execution error。全部动作数组、11 个 chunk 的坐标重建和 337 帧视频复核通过。P5 的接入缺口已解决，模型效果仍需完整评测。
- 12:44 UTC 启动 X-WAM → Fast-WAM → Motus 的六任务全量运行，均严格使用 `seed-manifests/20-blocks`。本轮保留独立的新输出目录、源码快照及动态报告；全量目标仍在执行，没有将启动任务视作取得完整成绩。
- 初衷扩展已落实到三个模型；没有因 X-WAM 的单个 Press 失败调整模型或评测判据。当前仍未提交或推送代码与 notes。

### 2026-11-05：全量中断的状态核查与恢复

- 用户查询进度时发现整批于 02:16 UTC 因 Sequence seed 100065 的 oracle 失败停止。X-WAM 已完成四个完整任务，成绩为 Stapler 85%、Pick 72.5%、Attribute 50.625%、Arm 10%；Sequence 另有 45 个有效回合，总计 325。Fast-WAM/Motus 的全量尚未开始。
- 新问题 P6 早于本次接入就曾在 X-VLA 同 seed 出现；当前原配置三次 probe 再次证明 oracle 执行不稳定，不能归为 X-WAM 动作输出错误。
- 保留原中断状态与所有错误产物，核验 325 条正常结果并归档末尾的 pre-policy oracle 错误。新增本机恢复 worker，只对尚未调用模型的同类错误做受限同 seed 重试；正常 policy failure 不重跑，seed/判据/动作预算不变。
- 03:02 UTC 启动恢复监督进程并重新加载 X-WAM。后续仍按 X-WAM → Fast-WAM → Motus 完成原计划；当前全量目标未完成，也尚未确认失败 seed 的真实续跑结果。

### 2026-11-05：用户质疑 oracle 与模型耦合，补做状态隔离实验

- 用户指出 oracle 尝试原则上不应依赖模型。源码与实测证实当前环境跨 episode 复用 CuRobo；EE policy 使用相同 planner，内部采样状态传入后续 oracle。qpos 对照没有改变被监测的采样状态。它是既有环境生命周期问题，不是 X-WAM 输出进入 oracle。
- 相同场景/seed、无模型调用，原样复用 planner 的 4 次 oracle 一成三败；显式 reset 两臂两个 MotionGen 的 4 次仍一成三败，且相同 IK RNG 起点仍产生不同轨迹。状态通路已经证实，但尚未解释全部不稳定性，未将 reset 当作已验证修复。证据见 [oracle 恢复调查](investigation/oracle-recovery.md)。
- 第一次恢复实际上已于 03:15 UTC 耗尽 5 次而停止，修正此前“恢复中”的过期状态。全部 325 个有效回合不重跑；候选 `20261105b` 从未启动。
- 新的 `20261105c` 在 4 项恢复控制测试通过后，于 03:31 UTC 启动。顺序为 Fast-WAM → Motus → 剩余 X-WAM；仅在 pre-policy oracle 错误后重新创建仿真进程，所有模型累计 8 次上限，旧错误计入。原 evaluator、任务判据、seed 与动作预算不变；进程生命周期变化有显式 provenance。
- 全量目标继续；P6 的严格独立性/稳定性仍未解决，当前不生成完整成绩或覆盖原有正式结果。

### 2026-11-05 07:29 UTC：Fast-WAM 三任务完成，首次真实自动恢复通过

- Fast-WAM 的 Press/Lift 为 38/40（95%）、Pick 为 26/40（65%）、Attribute 为 90/160（56.25%）；当前进入 Arm。该快照总计 248/460，X-WAM 保留 325/460，Motus 仍排队，无完整 Overall。
- Arm seed 500007 首次 oracle 失败，模型请求为空。监督进程于 07:27 UTC 自动重启仿真 worker，保持模型服务；新进程同 seed 的 oracle 通过，随后 policy 在 400 动作预算内正常失败。这是可保留的模型结果，没有因为失败再次重跑。
- 该案例证明恢复机制已在真实评测中工作，也进一步说明 oracle 波动不局限于 X-WAM/EE 模型。底层稳定性问题依然存在；详细归档与 provenance 见 [oracle 恢复记录](investigation/oracle-recovery.md)。

### 2026-11-05 07:47 UTC：用户授权尝试两套并行

- 用户要求尝试两个 server、两个 sim。依据实际模型显存与旧仿真采样，选择 Fast-WAM/X-WAM 分别在一张卡上放 server + sim；Motus 保持后续分卡运行。这个调度调整不缩减六任务/460 回合目标。
- 新 coordinator 接管时保存 590 个有效结果的哈希。保留 Fast-WAM 的模型与当前 Arm worker，任务结束后再迁移 sim；X-WAM 服务开始 GPU 0 加载，避免重载已经运行的 Fast-WAM。
- 12 项调度控制测试通过，GPU 1 renderer PCI 绑定实测正确。短跑直接消耗未完成 manifest 回合，保留真实 policy failure；此时仍在模型加载/旧任务收尾阶段，尚未宣称并行共存或加速比通过。

### 2026-11-05 08:26 UTC：并行短跑通过，继续全量

- Fast-WAM/X-WAM 从 08:06 同时运行，08:22 达到两套各至少 2 个有效回合的验收要求；08:26 完成前两个回合的预测请求、动作数组、三路初始相机图像、实际 GPU/renderer 和 provenance 校验。正常成功与失败均保留。
- GPU 0/1 采样最大分别为 32.9/28.3 GiB，启动至短跑结束最低可用主存为 14.3 GiB，无 OOM；590 份接管前的正常结果再次哈希核对一致。P7 的短跑目标达成，长期/全任务稳定性继续由实际运行覆盖，不声称两倍加速。
- X-WAM 原阻塞 seed 100065 的 oracle 已通过，policy 在完整预算内正常失败；原五份错误档案不变。P6 的恢复能力已有两个模型的真实案例，底层确定性仍未解决。
- 继续 Fast-WAM/X-WAM 并行，随后单独运行 Motus。当前快照 285/327/0，共 612/1380；原完整评测目标尚未完成。

### 2026-11-06：两个模型全量完成，Motus 已接续

- Fast-WAM 于 11 月 5 日 17:42 UTC 完成 460/460，X-WAM 于 19:23 UTC 完成 460/460。六任务等权平均 Overall 分别为 51.7361% 和 42.3264%，完整逐任务数据见 [结果记录](investigation/full-results-20261106.md)。
- 两模型共 920 个有效回合的 seed 顺序、mode、result/index、动作预算、task summary 与分数重算通过；64 个原始源码/配置哈希仍匹配，590 份切换前正常结果字节不变。已保存独立 audit JSON，未覆盖原有六模型正式结果包。
- Fast-WAM 共 10 次、X-WAM 共 7 次 pre-policy oracle 失败均有完整归档且同 seed 最终通过，未重跑正常 policy failure。Fast-WAM 的 Sequence/100065 也连续失败 6 次，进一步说明问题不独属于 X-WAM；P6 底层稳定性仍未解决。
- Motus 于 19:35 UTC 自动开始评测；11 月 6 日 01:37 UTC 为 245/460，前三任务 37/40、26/40、84/160，正在 Arm，无 Motus oracle 错误。整体 1165/1380，原三模型全量目标仍未完成。


### 2026-11-09：三模型全量结果核查与收尾

- 用户查询进度时核实本批实际已于 11 月 6 日 20:21 UTC 完成：Fast-WAM、Motus、X-WAM 各 460/460，共 1380 条。原始“增加开源 WAM 的同口径测试结果”目标已实现，没有缩减任务或替换 seed；原六模型发布包保持独立。
- Motus 六任务成功数为 37/40、26/40、84/160、26/40、8/120、22/60，Overall 53.0556%。Fast-WAM/X-WAM 的 51.7361%/42.3264% 及全部 920 个先前结果哈希保持不变。完整数据见 [结果记录](investigation/full-results-20261106.md)。
- 18 个组合逐项匹配原 manifest、mode 和预算，结果与索引/summary/provenance 一致；1055 个恢复标记及 24 份 worker metadata、79 个源码快照文件、590 个并行前结果均核查通过。当前源码差异仅 X-WAM README 补记 pilot，没有运行代码改动。
- Motus 共 5 次模型调用前 oracle 失败，均归档且原 seed 恢复；三模型合计 22 次。正常失败不重跑。P6 的批次恢复目标已实现，底层 oracle 确定性仍未解决。
- 新发现：coordinator 最后退出未重新刷新总计，状态与报告停在 1379，真实结果为 1380。保留旧状态和报告后，重新 snapshot 并刷新四种报告及 batch 总计，保留原完成时间；只修正派生汇总，未修改 episode 结果或扩大任务。
- 结果、核查脚本和证据保存在独立运行目录；代码、notes 均未提交或推送。三模型 Sequence 成功率都低，此处记录现象，不把训练或调参纳入当前任务。


### 2026-11-09：按用户要求合并 release，并发布九模型 Azure 包

- 用户明确要求将 feature 合并回 release，并询问将新增评测产物合并到 Azure。实际远端分支名为 `release-20261030`，已快进合并四个 inference/文档提交，追加发布提交 `777eff4a8839a50c8345326f3b58a1a3cc7505c2` 并推送；远端 HEAD 已核实一致。
- benchmark 定义未变化：相对基线 `57cb69c`，tasks、if_benchmark、seed-manifests、eval_cfg、runtime pins、共享 evaluation lifecycle 和 RoboTwin gitlink 均无差异。修改范围是新增适配器、模型选择/浏览支持、九模型结果和相应校验/文档。
- 原六模型 2760 条 ledger、成绩和 checkpoint 证据逐项不变；当前 result/ 扩展为九模型 4140 回合、1080 blocks，结果校验器相应验证九模型。29 项结果/入口/Azure 浏览回归通过，最终 `tools/verify_benchmark.py` 通过。
- 新 Azure 包为 `https://eaidatashare.blob.core.windows.net/xichen/robotwin-if/results/robotwin-if-20261109`：68605 个文件，8940269840 字节（约 8.33 GiB）。原包 `robotwin-if-20261030` 和日期 tag 保留。新包完整保留旧包 47531 份 evaluation/audit 产物哈希。
- 所有远端文件大小与 Content-MD5 核验一致，下载回来的 SHA256SUMS 与本地一致，本地 inventory 在上传期间未改变。清单 SHA-256 为 `2b2ccc4ac7a9cd3c9832d9e068c1b3ba7770d39eaf7441198205f315d23d5fb0`。实际 Azure viewer 加载全部 4140 条记录且九模型分数一致，并读取核验 X-VLA/Fast-WAM/Motus/X-WAM 各一对 result/video 样本。
- 发布 receipt 位于主项目 `result/azure-backup.json`；本机打包脚本、inventory、上传日志和 viewer 记录保存在 `/Data/robotwin-if/exports/.azure-transfers/robotwin-if-20261109/` 及新包 `audit/wam/`。默认 `just video-review-azure` 与下载说明已指向新包。
- 该次明确授权扩大了结果发布范围，取代之前“尚未发布或合并”的阶段状态。P3 完成；P6 的底层 oracle 确定性仍是独立后续问题。现有 Claude 配置、RoboTwin 本地改动与临时 checkout 未提交；notes 保持本地记录。
