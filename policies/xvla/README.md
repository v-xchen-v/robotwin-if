# X-VLA inference environment

使用公开 checkpoint [`2toINF/X-VLA-RoboTwin2`](https://huggingface.co/2toINF/X-VLA-RoboTwin2)，面向 Agilex 双臂，采用 20D EE6D。这里维护独立的模型服务环境；RoboTwin 仿真和后续客户端使用原有 `RoboTwin` 环境。

## 安装

在已安装 Conda、Git 和 Python 3 的 Linux 主机上，从仓库根目录执行：

```bash
bash policies/xvla/setup_env.sh
```

脚本可以从任意工作目录通过绝对路径调用。它会：

1. 创建或复用 `robotwin-if-xvla`，使用 Python 3.10。
2. 将官方 X-VLA 源码取到 `third_party/xvla/`，固定 revision 为 `6bc2513f5f1cbec715cc668b414392a6cae5c671`。
3. 安装 [`requirements.txt`](requirements.txt) 中的推理依赖，包括 PyTorch 2.1.2 / torchvision 0.16.2 的 CUDA 12.1 wheels 和 Transformers 4.51.3。
4. 执行 `pip check` 和 X-VLA 模型、processor、EE6D action hub 的导入检查，并打印 CUDA 可用状态。

PyTorch/CUDA 版本沿用官方 [`environment.yml`](https://github.com/2toinf/X-VLA/blob/6bc2513f5f1cbec715cc668b414392a6cae5c671/environment.yml) 的系列，其他推理依赖参考其 [`requirements.txt`](https://github.com/2toinf/X-VLA/blob/6bc2513f5f1cbec715cc668b414392a6cae5c671/requirements.txt) 和服务代码。`opencv-python-headless` 提供服务端使用的 `cv2`。此环境面向完整 checkpoint 推理；训练和 LoRA 依赖不在当前安装范围内。直接依赖已固定，传递依赖尚未生成完整 lock。

自定义环境名或 checkout 路径：

```bash
bash policies/xvla/setup_env.sh \
  --env-name robotwin-if-xvla-dev \
  --source-dir /path/to/X-VLA
```

已存在的 checkout 必须处于固定 revision 且没有 tracked changes；脚本不会替换或重置它。已存在的 Conda 环境必须是 Python 3.10，重跑会安装声明的依赖版本。`base`、`root` 和 `RoboTwin` 环境名不可用于此脚本。

安装脚本不下载权重、不启动服务、不执行任务。GPU 推理需要支持上述 CUDA wheels 的 NVIDIA GPU/driver；导入检查本身可在没有 GPU 的节点运行。

## 启动官方服务

以下命令从本仓库根目录开始，使用默认安装路径：

```bash
conda activate robotwin-if-xvla
cd third_party/xvla
CUDA_VISIBLE_DEVICES=1 python -m deploy \
  --model_path 2toINF/X-VLA-RoboTwin2 \
  --host 127.0.0.1 \
  --port 8010 \
  --disable_slurm \
  --output_dir ./logs/benchmark
```

首次加载会下载权重到 Hugging Face cache；也可以将 `--model_path` 指向已下载的本地 checkpoint 目录。正式记录验证证据前应固定 HF revision，并使用对应的本地 snapshot 路径。
上述服务使用 GPU 1；当前六任务统一评测入口在 GPU 0 上运行仿真，安装与首次评测见 [Quickstart](../../docs/quickstart.md)。

客户端请求地址为 `http://127.0.0.1:8010/act`。上游会在 `--output_dir` 下写入 `info.json`，每次启动使用一个新的 run 目录。自定义安装时将上述环境名和 checkout 路径换成 setup 时的值。模型服务与客户端在不同机器时，按部署需要设置 `--host` 和客户端地址。

## 运行 benchmark

从仓库根目录执行，保持模型服务运行，仿真使用 RoboTwin 环境：

```bash
bash scripts/eval.sh --policy xvla --task press_lift_stapler --blocks 1 \
  --output-dir outputs/policy-eval/first-run
bash scripts/eval.sh --policy xvla --output-dir outputs/policy-eval/full-run
```

六任务默认各 20 blocks，固定 seeds。完整结果见 [result](../../result/README.md)，
参数与评分规则见[评测说明](../../docs/formal-policy-evaluation.md)。

### 输出格式

`--output-dir` 指向 task 目录，建议使用 `outputs/policy-eval/<run>/xvla/<task>/`。episode 文件与 `smoke-blocks1/cogact/arm_select/` 的命名和核心字段一致，直接平铺，不再创建 `seed-*` 子目录。以 seed 100000 为例：

```text
arm_select_ep100000.log
arm_select_ep100000_instruction.txt
arm_select_ep100000_step0000.png
arm_select_ep100000_1.mp4
arm_select_ep100000_summary.json
arm_select_ep100000_status.json
arm_select_ep100000_timings.json
arm_select_ep100000_action_logs.json
arm_select_ep100000_result.json
arm_select_ep100000_oracle.json
arm_select_ep100000_initial_observation.npz
arm_select_ep100000_actions.npz
arm_select_ep100000_diagnostics.json
```

- 视频后缀 `_1` 表示任务成功，`_0` 表示未成功；`status.json` 区分 `policy_success`、`policy_failure` 和 `execution_error`。`block` 是本次 run 中从 0 开始的 block 序号，raw task 为 `null`。setup 提前报错时可能没有图像/视频，错误仍写入 summary、status 和日志。
- `summary.json` 包含同名的任务、指令、seed、步数、耗时、成功状态字段；额外保留 task 的 `signals`。未采集的通用 grasp/lift 诊断字段为 `null`，可用性与具体含义记录在 `diagnostics.json`。
- `action_logs.json` 每个预测 chunk 一条，提供 `ROBOT_LEFT/RIGHT_{GRIPPER,ROT_6D,ROT_MAT,TRANS}`。内容保留 X-VLA 的原始预测语义：gripper 是 sigmoid 概率，rot6d/矩阵遵循 checkpoint 的数值约定，详见下节。chunk 末尾可能未执行；`actions.npz` 记录原始输出、真正执行的 16D 动作、实测 EE pose、请求 proprio 和请求延迟。
- `timings.json` 每个执行步一条，字段为 `step`、`inference_time_sec`、`env_step_time_sec`、`total_time_sec`。chunk 推理耗时计入首步，缓存动作的推理耗时为 0；环境耗时仅包含 `take_action()`，总步耗时为二者之和，不含观测和视频 IO。summary 的 `duration_sec` 是完整 episode 墙钟时间，包含 oracle qualification 与场景重建，不能直接与其他 runner 的 FPS 比较。
- 新 run 的 PNG 和视频按 head / left wrist / right wrist 横向拼接；视频包括初始画面和每个执行步之后的画面。历史视频仅录制了 head camera，转换时原样保留；初始 PNG 可从已存三路观测恢复。

同一 task 目录额外保留 `run.json`、`resolved_config.json`、`console.log`、`results.jsonl`、`summary.json`。`console.log` 记录运行初始化和各 episode 状态，具体 episode 输出写入各自 `.log`。

已有旧格式可离线转换到新目录：

```bash
conda run --no-capture-output -n RoboTwin python -m policies.xvla.outputs \
  --legacy-dir outputs/policy-eval/xvla-arm-select-001 \
  --output-dir outputs/policy-eval/smoke-blocks1/xvla/arm_select
```

该命令已用于整理本次验证结果；目标目录存在时拒绝覆盖。原目录保留；新目录中的 `conversion.json` 记录源文件 hash，`run.json` 和详细 result 保持原始内容，仍描述原运行。旧记录没有逐步环境耗时及总步耗时，对应字段为 `null`，请求延迟只分配到各 chunk 的首步。旧共享日志保留为 `console.log`，各 episode `.log` 是明确标注来源的片段。

### 与 checkpoint 一致的动作编码

RoboTwin 原始四元数为 `wxyz`。X-VLA 的官方训练 handler 和评测 client 都把这四个数字直接送入 SciPy 默认的 `xyzw` codec，生成前两列交错排列的 rot6d；解码使用对应逆变换后直接交给 RoboTwin。这里保留这种**数值编码约定**，避免只在推理侧交换四元数分量而改变 checkpoint 输入空间。测试覆盖非对称四元数、左右臂排列及往返转换。

夹爪沿用官方 `1 - 2*(p > 0.7)`；RoboTwin controller 会把负值裁剪为关闭状态。默认 `--feedback commanded` 也沿用官方 client：后续请求的 EE pose 使用上次实际提交的目标 pose，图像和夹爪观测仍来自环境。可显式选择 `--feedback measured` 做独立诊断；设置写入 run metadata。

这是 integration smoke。HTTP API 不提供 checkpoint 身份证明或 RNG seed 控制；`--checkpoint`/`--checkpoint-revision` 是运行者声明，服务端随机性不由 episode seed 控制。当前 runtime/config 的 hash 和 dirty 状态会记录；此次 `arm_select` 初始化修复也改变了 task source hash，因此结果不冒充原有 seed release 下的正式 benchmark。

```bash
conda run --no-capture-output -n RoboTwin python tests/xvla/test_client.py
conda run --no-capture-output -n RoboTwin python tests/arm_select/test_policy_success.py
```

官方评测入口见 [`evaluation/robotwin-2.0/README.md`](https://github.com/2toinf/X-VLA/blob/6bc2513f5f1cbec715cc668b414392a6cae5c671/evaluation/robotwin-2.0/README.md)。

Checkpoint identities and full inference evidence: [results](../../result/README.md) · [download](../../docs/download-results.md).
