# 安装与首次运行

本文对应当前六任务，从新 clone 到 expert 场景预览，再到一个开源 policy 的小规模评测。
以下命令从仓库根目录执行。完整成绩见[当前结果](../result/README.md)。

## 1. 准备环境

需要 Linux、Bash、Git、Conda 和 NVIDIA GPU/驱动。安装器使用 `sudo apt-get` 安装 Vulkan、图形库与 FFmpeg；
模型安装所需的 CUDA/驱动版本见[各 policy 文档](../policies/README.md)。
Expert 采集使用一张 GPU；当前 `scripts/eval.sh` 使用两张 GPU，默认仿真 GPU 0、模型 GPU 1。
为 RoboTwin 资产预留约 16 GB，另外为所选模型的环境与权重预留空间。

```bash
git clone --branch release-20261030 --recurse-submodules https://github.com/v-xchen-v/robotwin-if.git
cd robotwin-if
nvidia-smi

bash setup_robotwin.sh
conda activate RoboTwin
bash scripts/bridge_tasks.sh
bash scripts/bridge_tasks.sh --check
```

安装器创建或复用 `RoboTwin` Conda 环境、获取固定版本的 RoboTwin/CuRobo、安装依赖、下载资产并生成机器人路径配置。
版本来自 [`runtime_pins.json`](../scripts/runtime_pins.json)。已有源码版本不符时会停止并保留文件。
Bridge 安装六任务、helper、instruction 和 Arm cube-v3 配置，共 **19 个软链**；检查应输出 `check passed: 19 owned links`。

可用以下选项复用资产或单独准备源码：

```bash
bash setup_robotwin.sh --assets-cache /absolute/path/to/assets
bash setup_robotwin.sh --sources-only
```

`--sources-only` 不安装依赖或资产，不能单独完成仿真环境准备。
资产路径应是包含 `objects/`、`embodiments/` 等内容的 RoboTwin 资产目录。
安装时会生成含绝对路径的机器人配置，安装后移动目录需重新配置，可重新运行安装器配置资产路径。

已有 checkout 更新后，重新运行 `bridge_tasks.sh` 和 `--check`。
旧版手工创建、指向当前仓库 Arm 配置的软链会被接管；同名真实文件或其他来源的软链会报冲突并保留。
外部 runtime 或已修改原生源码的接入规则见 [task bridge](task-bridge.md)。

## 2. 查看六任务 expert 场景

先查看计划，再实际采集；不需要下载模型：

```bash
bash scripts/collect.sh --dry-run
bash scripts/collect.sh --output-dir outputs/expert-review/first-review
```

默认每任务采集 **1 个完整 block，共 23 条成功演示**。从 seed 0 开始尝试，失败则跳过整个 block，直到采够。
打开 `outputs/expert-review/first-review/index.html`，查看每个 mode 的初始画面、instruction 和 expert 视频。
在远程机器上可通过 SSH 文件传输整体下载该目录后打开页面。

可使用当前已筛选 seeds 加快首次检查：

```bash
bash scripts/collect.sh \
  --seed-manifest seed-manifests/20-blocks \
  --output-dir outputs/expert-review/manifest-review
```

每次使用新的输出目录。数量、单任务和尝试上限参数见 [expert review](expert-review.md)。

## 3. 安装并启动一个 policy

从[六个 policy](../policies/README.md)中选择一个，按其 README 完成独立环境安装、权重下载和服务启动，
同时将其 `requirements-client.txt` 安装到 `RoboTwin` 环境（X-VLA 的客户端依赖已由仿真安装器提供）。

权重示例统一使用可配置的存储根目录：

```bash
export ROBOTWIN_IF_HOME="${ROBOTWIN_IF_HOME:-$HOME/.local/share/robotwin-if}"
# 也可以改成有写权限、空间充足的数据盘绝对路径。
```

| 内容 | 默认位置 | 自定义方式 |
|---|---|---|
| RoboTwin | `third_party/robotwin`；Conda 环境 `RoboTwin` | 外部 runtime 见 bridge 文档 |
| 模型源码 | `third_party/<model>` | 模型 setup 的 `--source-dir` |
| X-VLA / LingBot-VA / LingBot-VLA / VLAct 环境 | Conda 管理的 `robotwin-if-<model>` | 模型 setup 的 `--env-name`；`CONDA_ENVS_PATH` 可指定存储目录 |
| DM05 / Hy-VLA 环境 | `$ROBOTWIN_IF_HOME/envs/robotwin-if-<model>` | 模型 setup 的 `--env-prefix` |
| 下载的权重 | `$ROBOTWIN_IF_HOME/checkpoints/<checkpoint>` | downloader 的 `--output-dir`；服务用相同的 `--checkpoint-dir` |
| 采集和评测产物 | `outputs/expert-review/`、`outputs/policy-eval/` | 运行入口的 `--output-dir` |

X-VLA 默认由官方服务下载到 Hugging Face cache，也可使用本地 checkpoint，见其 README。
DM05/Hy-VLA 的 Conda 包缓存和临时下载默认放在环境父目录下，可用 `CONDA_PKGS_DIRS`、`TMPDIR` 覆盖。
已有 `/Data/robotwin-if` 安装可设置 `ROBOTWIN_IF_HOME=/Data/robotwin-if` 继续使用；安装器不会自动迁移环境或权重。

在独立终端启动所选模型，**模型 GPU 设为 1**；保持该服务运行。下面以 VLAct All 为例，
其安装、固定版本下载和启动命令见 [VLAct README](../policies/vlact/README.md#setup-and-serve)。

## 4. 跑小规模评测

回到仿真终端，确认已激活 `RoboTwin`：

```bash
conda activate RoboTwin

# 六任务默认计划；不连接服务、不启动 GPU、不写输出。
bash scripts/eval.sh --policy vlact \
  --output-dir outputs/policy-eval/vlact-first --dry-run

# 先跑一个 Stapler block（Press/Lift 两回合）。
bash scripts/eval.sh --policy vlact --task press_lift_stapler --blocks 1 \
  --sim-gpu 0 --model-gpu 1 --output-dir outputs/policy-eval/vlact-first

# 接入正常后，六任务各 20 blocks，共 460 回合。
bash scripts/eval.sh --policy vlact --sim-gpu 0 --model-gpu 1 \
  --output-dir outputs/policy-eval/vlact-full
```

输出按 `<output-dir>/<policy>/<task>/` 保存，含 `summary.json`、逐回合结果、instruction、视频和动作。
正常执行后的模型失败是有效评测结果；初始化或基础设施错误会停止，不替换 seed。
更多运行参数和成绩汇总见[评测说明](formal-policy-evaluation.md)。
