# X-VLA inference environment

首个 checkpoint 为 [`2toINF/X-VLA-RoboTwin2`](https://huggingface.co/2toINF/X-VLA-RoboTwin2)，面向 Agilex 双臂，采用 20D EE6D。这里维护独立的模型服务环境；RoboTwin 仿真和后续客户端使用原有 `RoboTwin` 环境。

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
python -m deploy \
  --model_path 2toINF/X-VLA-RoboTwin2 \
  --host 127.0.0.1 \
  --port 8010 \
  --disable_slurm \
  --output_dir ./logs/raw-click-bell-001
```

首次加载会下载权重到 Hugging Face cache；也可以将 `--model_path` 指向已下载的本地 checkpoint 目录。正式记录验证证据前应固定 HF revision，并使用对应的本地 snapshot 路径。

客户端请求地址为 `http://127.0.0.1:8010/act`。上游会在 `--output_dir` 下写入 `info.json`，每次启动使用一个新的 run 目录。自定义安装时将上述环境名和 checkout 路径换成 setup 时的值。模型服务与客户端在不同机器时，按部署需要设置 `--host` 和客户端地址。

## 验证状态与下一步

2026-09-06 已在本地完成环境验证：Python 3.10.21、PyTorch 2.1.2+cu121、torchvision 0.16.2+cu121、Transformers 4.51.3；`pip check`、模型/processor 导入和 20D EE6D 检查通过，RTX A6000 上的 CUDA 小张量运算通过。X-VLA checkout 与固定 revision 一致，且没有本地修改。

本次检查时，默认 Hugging Face cache 中没有该 checkpoint 的 snapshot。模型下载/加载、真实动作预测和任务 rollout 验证仍待完成。

1. 先确认服务能用真实 checkpoint 返回动作，再成功完成 raw `click_bell`。
2. 然后接入 IF `arm_select`，重放完整 left/right balance block，记录结果和视频。
3. 两项任务通过后才标记该策略 inference 验证完成。

后续 adapter 需要将 20D EE6D 转换为 RoboTwin 的 16D EE action，并核对四元数、夹爪、反馈及 action chunk 处理。环境脚本没有实现这层适配，也没有安装 external RoboTwin policy bridge。

官方评测入口见 [`evaluation/robotwin-2.0/README.md`](https://github.com/2toinf/X-VLA/blob/6bc2513f5f1cbec715cc668b414392a6cae5c671/evaluation/robotwin-2.0/README.md)。
