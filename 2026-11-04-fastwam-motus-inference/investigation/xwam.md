# X-WAM：RoboTwin SFT 接入

2026-11-04，作为同一 WAM 评测 feature 的后续扩展。用户要求在全量评测之前先增加其 inference code；原初衷及全量待办见 [intent.md](../intent.md)。

## 固定来源

| 资源 | revision / 入口 | 用途 |
| --- | --- | --- |
| [X-WAM 源码](https://github.com/sharinka0715/X-WAM) | `72cfb86b33fc5060963ef63412f16439fcfa472f` | `evaluation/policy_server.py`、`evaluation/X-WAM/deploy_policy.py`、`runners/xwam_runner.py` |
| [SFT 权重](https://huggingface.co/sharinka0715/X-WAM-checkpoints) | `bb6fd1643cfa8bdc751612a7ace0bd8062a8917a` | `robotwin_sft/config.yaml` 与 `robotwin_sft/checkpoints/last.ckpt/checkpoint/mp_rank_00_model_states.pt` |
| [RoboTwin 训练数据](https://huggingface.co/datasets/sharinka0715/X-WAM-RoboTwin) | `383c3bb7db3ba1e3baa44c1bd33f0bc94d69a20f` | 核对三相机、EE pose 和 action schema；未下载训练集 |
| Wan2.2-TI2V-5B | `921dbaf3f1674a56f47e83fb80a34bac8a8f203e` | 复用已下载基础 DiT、T5、VAE 和 tokenizer |

SFT 主权重大小为 38,892,887,211 字节，SHA-256 为 `7d38fbd7ee7f9dcdbdee33dcdae622077279a3e9f680e76f4e0e000c4dca88f0`。原始资源清单保存在 `/Data/robotwin-if/tmp/xwam-inspection-20261104/`；运行用资产清单在主项目 `policies/wam/assets.json`。

## 官方推理契约

- 三路 240×320 RGB（head/left/right），先归一化到 [-1, 1]，再分别 resize 到 256×320、中心裁剪比例 0.95、resize 回原目标尺寸。复用官方图像 helper，不拼成单幅三视图。
- 每臂状态为 xyz + wxyz quaternion + gripper，按官方 base 坐标与 EE 轴变换后合成 16D，再使用 SFT 配置的 q01/q99 统计归一化；不额外裁剪。
- 原样传递任务实际指令。模型输出 32×14 双臂相对动作，包含 xyz、axis-angle、gripper 增量；逐步累积，旋转增量左乘，随后反变换为 RoboTwin 原生 32×16 absolute EE 动作。
- 以 `action_type="ee"` 执行最多 32 步，每步检查任务成功与动作预算。保留完整 delta 预测、解码 absolute chunks 和实际执行序列。
- 保留官方 ANS 路径：video schedule 50 steps、action 10 steps、CFG 0、`early_stop=True`、`run_depth=False`。无需深度观测；不运行后续视频/深度解码。服务采用 eager BF16，未启用官方 server 的 `torch.compile`。
- 每回合 reset；官方 `compute_seed(0, rollout_id, step_id)` 的 MD5 算法保持一致，`rollout_id` 明确映射为 manifest seed，`step_id` 为已执行动作数，避免分批调度改变噪声 seed。
- 官方 runner 先加载 Wan 基础权重，再严格加载完整 SFT `module`。适配器用 CPU mmap 避免额外常驻约 39 GB 的 checkpoint 副本，严格参数键与形状检查仍由 `load_state_dict(strict=True)` 执行。

## 实现与验证

- 入口：主项目 `policies/xwam/`，服务端口 8018；`scripts/eval.sh --policy xwam` 使用同一六任务 seed manifest。
- 模型环境：`/Data/robotwin-if/envs/robotwin-if-xwam`；源码：`third_party/xwam`；资产：`/Data/robotwin-if/checkpoints/wam/sharinka0715/X-WAM-checkpoints/robotwin_sft`。
- 已安装独立环境：Python 3.10、Torch 2.7.1/cu128、Transformers 4.51.3、Diffusers 0.38.0、NumPy 1.25.2、FlashAttention 2.7.4.post1；`pip check` 和官方模块导入通过。官方报告的测试版本 Torch 2.8.0/FlashAttention 2.8.3 与此不同；当前版本位于其声明的支持范围。完整安装版本见 `xwam-inspection-20261104/environment.json`。
- 新增 6 项 CPU 检查通过：坐标逆变换、非交换旋转顺序、gripper 累积、协议/seed/reset、异常输入/输出、成功或预算导致的 chunk 中途停止及证据语义。WAM 共用服务的 10 项、launcher 的 8 项、结果范围的 4 项、视频复核的 11 项也通过。
- 直接执行固定 revision 的官方 `deploy_policy.eval`（mock transport/environment）与本地 codec 对照 20 组随机双臂位姿和动作：state 最大误差 0，absolute action 最大误差 `2.220446049250313e-16`，seed hash 一致。记录：`/Data/robotwin-if/tmp/xwam-inspection-20261104/codec-parity.json`。
- GPU 上执行官方图像 helper、读取 SFT 统计、调用 FlashAttention CUDA kernel 均通过；图像产物为 BF16 `[1,3,3,256,320]`，状态/动作统计为 16/14D，记录在 `xwam-inspection-20261104/preprocessing-environment.json`。
- 已从下载中的 checkpoint 索引只读提取 1555 个 module tensor 的形状/类型，均为 BF16，module 共 13,060,510,746 个元素；完整文件还包括 DeepSpeed 其他状态。入口先在 CPU 转 BF16 再移至 GPU，以避免启动时无必要的 FP32 显存副本。仍严格加载完整 module，未删除参数或更改推理精度。
- 主权重和配置均已下载并校验，receipt 为 `/Data/robotwin-if/checkpoints/wam/xwam-download-verification-20261104.json`。服务启动时另行完整校验 X-WAM 与 Wan 资源；完整 SFT module 的严格加载通过，服务身份记录为主项目 `outputs/policy-eval/servers/xwam-001/server.json`。

## 真实配对 pilot

2026-11-04，使用 release manifest 首个完整 block，模型 GPU 1、仿真 GPU 0，RTX A6000。输出位于 `/Data/robotwin-if/evaluations/xwam-pilot-20261104/`。

| Seed | 实际指令 | 终态 | 实际动作 / chunks | 视频帧 |
| --- | --- | --- | --- | --- |
| 110000 | `Press down on the stapler.` | policy failure，达到 250 步预算 | 250 / 8 | 251 |
| 110001 | `Lift the stapler.` | success | 85 / 3 | 86 |

两个回合均通过 oracle qualification，无 execution error。Press 未产生有效 press/lift 首动作事件；这是一条有效失败记录，未据此修改权重、推理参数或判据。Lift 成功不代表其他任务已验证。

复核了全部 NPZ 的有限值与形状、执行序列等于预测 absolute chunks 的实际前缀，并从每个 chunk 起始的实测原生 EE 位姿重新解码 delta，与保存的 absolute 动作一致（atol 1e-13）。逐帧解码视频通过，帧数为动作数加初始帧。含逐文件 SHA-256 的复核 receipt 为 `verification.json`；本 notes 的 `xwam-pilot-results.json` 保存副本。没有将接入检查通过写成任务全成功。

首个预测 10.75 秒，后续 10 次预测的服务端中位数为 1.6615 秒 / 32 步。采样观察到模型显存 27,741 MiB，进程启动 RSS high-water mark 为 40,814,324 KiB（约 38.9 GiB）；该显存数是采样值，不声称是所有瞬时峰值。资源采样为 `/Data/robotwin-if/tmp/xwam-resources-20261104.jsonl`，服务与 pilot 日志在相同 tmp 目录。

## 后续

2026-11-04 12:44 UTC 已启动完整六任务 / 20 blocks，顺序为 X-WAM、Fast-WAM、Motus，每模型 460 回合，共 1,380 回合。X-WAM 复用已验证的服务，其余两个模型在前一个完成后依次加载。全部模型均从各自 manifest 首个 seed 开始，不复用 pilot 结果，不更改 seed 顺序。

- 全量目录：`/Data/robotwin-if/evaluations/wam-full-20261104/`。
- `progress.md` / `progress.html` / `progress.json` 每分钟更新；单模型六任务跑齐前 Overall 为 null。
- `batch-status.json` 记录当前模型、进程与终态；监督进程 PID 2255460，当前 X-WAM 服务 PID 2249851。PID 只对应本轮运行，应以状态文件与进程实际状态为准。
- `source-snapshot/`、`source-sha256.json`、`base-commit.txt`、`batch-runner.py` 保留本轮代码、manifest、执行方式；逐模型 server metadata、日志和逐回合产物单独保存。
- 正常 policy failure 计入结果；基础设施错误停止整批并保留现场，不跳过或替换 seed。全量运行仍未完成，不能给出最终排名或完整成绩。

2026-11-05：原批次于 02:16 UTC 因 Sequence seed 100065 的 oracle qualification 失败停止；首次恢复累计 5 次失败，03:15 UTC 再次停止。325 个有效回合已保留。新实验已证实 EE 动作的 planner 状态被下一轮 oracle 继承，但 reset 仍不足以保证稳定。03:31 UTC 启动 Fast-WAM → Motus → 剩余 X-WAM 的新进程恢复；当前状态与详细证据见 [恢复记录](oracle-recovery.md)。上述原监督进程 PID 已失效，应读取当前 `batch-status.json`。
