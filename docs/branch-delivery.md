# 分支交付说明

本分支交付三部分：六个模型的推理适配与 bash 评测入口、六任务 20-block 的 seed/mode 清单、已完成的结果包。
Grasp-Approach 暂时下线，保存在 `bak/`，不进入当前默认评测。

## 1. Policy inference code 与 eval

| Policy 参数 | 推理代码、环境安装、权重下载及服务启动 | 当前 checkpoint | 默认服务地址 |
|---|---|---|---|
| `xvla` | [policies/xvla](../policies/xvla/README.md) | `2toINF/X-VLA-RoboTwin2` | `http://127.0.0.1:8010` |
| `lingbot_va` | [policies/lingbot_va](../policies/lingbot_va/README.md) | `robbyant/lingbot-va-posttrain-robotwin` | `ws://127.0.0.1:8011` |
| `lingbot_vla` | [policies/lingbot_vla](../policies/lingbot_vla/README.md) | `robbyant/lingbot-vla-4b-posttrain-robotwin` | `ws://127.0.0.1:8012` |
| `vlact` | [policies/vlact](../policies/vlact/README.md) | `StarVLA/VLAct_Qwen3OFT_Robotwin_all_Finetune` | `ws://127.0.0.1:8013` |
| `dm05` | [policies/dm05](../policies/dm05/README.md) | `Dexmal/DM05-robotwin2` | `http://127.0.0.1:8014` |
| `hy_vla` | [policies/hy_vla](../policies/hy_vla/README.md) | `tencent/Hy-Embodied-0.5-VLA-RoboTwin` | `ws://127.0.0.1:8015` |

各目录提供 `setup_env.sh`、依赖声明、`client.py`、`eval.py` 和输出适配；五个模型还有本仓库的
`serve.py` 包装，X-VLA 使用 setup 获取的固定上游 server。模型权重由各 README 的下载流程获取。
实际用于已交付结果的 checkpoint revisions 记录在 [checkpoints.json](../result/robotwin-if-arm-only-v2-20blocks/checkpoints.json)。
VLAct 使用 All 100K，不能用旧 Clean 50K 代替。

运行需要 Linux、NVIDIA GPU、Bash、`setsid`、`flock`、`timeout`、`nvidia-smi`，以及已安装的
RoboTwin 环境/资产和所选模型的独立环境。默认 sim 用 GPU 0、模型用 GPU 1，单次只启动一个模型服务。
环境和权重大小因模型而异，具体版本与要求见各 policy README。
同时按该 README 在 RoboTwin 环境安装 `requirements-client.txt` 中的通信依赖。
模型文档中的 `/Data/robotwin-if/...` 是示例存储路径，可改为接收方有写权限的位置，
并在下载与服务启动参数中保持一致。

先准备 RoboTwin、任务 bridge 和 arm_select cube-v3 配置：

```bash
# 从仓库根目录执行；首次安装按根 README/setup_robotwin.sh 完成环境与资产准备。
git submodule update --init third_party/robotwin
conda activate RoboTwin
bash scripts/bridge_tasks.sh

# cube-v3 config 不属于 bridge 的 env/instruction 链接；目标不存在时安装。
ln -s "$PWD/tasks/task_config/demo_clean_arm_select_v3.yml" \
  third_party/robotwin/task_config/demo_clean_arm_select_v3.yml

python tools/export_seed_modes.py --check
```

配置已正确安装时无需重复 `ln -s`。外部/不同 commit 的 runtime 按根 README 使用
`--robotwin-dir` 和经审阅的 `--allow-compatible-commit`；不应跳过 bridge 的静态 API 检查。
不同机器的 renderer 可能产生不同初始像素，本脚本记录新运行，不宣称逐像素重现历史结果。

在独立终端按所选模型 README 启动服务，服务 GPU 设为 1。随后用 RoboTwin 环境的 Python 执行：

```bash
# 查看默认六任务、20 blocks 的命令；不连接模型、不调用 GPU、不创建输出。
bash scripts/eval.sh --policy vlact --output-dir outputs/policy-eval/vlact-new --dry-run

# 每个 task 20 blocks；按固定清单串行完成 460 个 episodes。
bash scripts/eval.sh --policy vlact --sim-gpu 0 --model-gpu 1 \
  --output-dir outputs/policy-eval/vlact-new

# 可先验证一个任务的前两个完整 blocks。
bash scripts/eval.sh --policy hy_vla --task arm_select --blocks 2 \
  --sim-gpu 0 --model-gpu 1 --output-dir outputs/policy-eval/hy-vla-pilot
```

替换 `--policy` 即使用对应适配器。切换模型时结束上一模型服务，再启动下一模型；
脚本不同时加载六个模型。`--python /path/to/RoboTwin/bin/python`（或 `SIM_PYTHON`）可指定解释器，
`--server-url`、`--robotwin-dir` 和 `--manifest-dir` 可覆盖默认位置，无需本机旧 `/Data` 目录。

脚本保持单 sim 串行、显式绑定 SAPIEN GPU，并检查 sim GPU 空闲、GPU 温度/显存。
GPU 查询超过 8 秒、温度达到 87°C 或显存超限会停止本次 sim；模型服务由其原启动终端管理。
每个 episode 仍执行 oracle qualification，seed 不跳过、不替换。全失败但正常跑完的任务也算完成，
继续下一个任务；基础设施错误停止。脚本核对最终 seed 顺序与回合数量。

输出目录为 `<output-dir>/<policy>/<task>/`，含 `run.json`、`summary.json`、`results.jsonl`、
逐回合视频、动作、初始观测、指令和诊断。已有 task 目录不覆盖；本入口用于新运行，
不复用旧结果或自动恢复半个任务。内部归档迁移/断点续跑入口仍见 [正式评测说明](formal-policy-evaluation.md)。
新机器、代码版本或推理随机性不同，不保证重跑得到相同成功数。

## 2. 六任务 × 20 blocks 的 seed + mode manifest

目录：[`seed-manifests/robotwin-if-arm-only-v2-20-per-mode/`](../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md)。

| Task | Modes/block | 20 blocks 的回合数 | Task config |
|---|---:|---:|---|
| bottle_verb | 2 | 40 | demo_clean |
| pick_diverse_object | 2 | 40 | demo_clean |
| attribute_select | 8 | 160 | demo_clean |
| arm_select | 2 | 40 | demo_clean_arm_select_v3 |
| stack_sequence | 6 | 120 | demo_clean |
| place_relative | 3 | 60 | demo_clean |
| 每个 policy 合计 | 23 | 460 | |

- `<task>.json` 是 flat manifest，evaluator 直接读取原始 `seeds`。Spatial 使用 schema 2，
  每组 seeds 为 `[5k, 5k+1, 5k+4]`；Arm-Select 使用新 seeds `500000–500039`。旧 Spatial schema 1 仅供五模式历史校验。
- [`seed-modes.json`](../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/seed-modes.json) 给出每个任务的
  config、manifest SHA-256、mode 分母及逐 episode 的 `seed`、`mode`、`block`、`block_offset`、scene 信息。
- [`seed-modes.csv`](../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/seed-modes.csv) 为相同信息的 460 行平表。
- `block` 是清单内从 **0 到 19** 的顺序编号；候选 seed 可能有间隔，不等于 `seed // block_size`。
- `suite.yml`、`qualification-files.json`、`reusable-results.yml` 保留正式发布及历史复用证据。
  接收方启动新评测只需 flat manifests 与 seed/mode 导出，不需要访问复用索引中的原机器路径。

`python tools/export_seed_modes.py --check` 检查 JSON/CSV 与 flat seeds/modes 一致；
完整发布检查使用 `python seed-manifests/robotwin-if-arm-only-v2-20-per-mode/verify.py`，需要原机历史运行目录与产物。
旧版实体目录已移入 [历史清单归档](../seed-manifests-archive/README.md)，旧路径保留兼容软链接。

## 3. Result

当前结果：[`result/robotwin-if-arm-only-v2-20blocks/`](../result/robotwin-if-arm-only-v2-20blocks/README.md)。
六个 policies 已完成 **2760/2760 episodes、720/720 blocks**，每个 policy 为 460 episodes；2026-09-18 05:26 UTC 正式校验通过。
Arm 按 target-arm-only-lift-v2 全新运行 240 回合，其余五任务复用 Attribute-v2 的 2520 回合，包含成功和失败。
初始观测、记录哈希、统计及 checkpoint 身份核对通过，见 [Arm 重评说明](arm-select-target-only-v2-evaluation.md)。
历史结果保留原始判据和计数，入口在 [结果索引](../result/README.md)。

提供 `results.html/md/json/csv`、`episodes.csv`、六份 frozen manifests、checkpoint 身份、
provenance 与 `SHA256SUMS`。可离线查看汇总表和逐回合计数，不依赖原机器。
`Overall` 对六个任务的 `Task Avg.` 等权，成功与已完成的 policy failure 都保留。

```bash
(cd result/robotwin-if-arm-only-v2-20blocks && sha256sum -c SHA256SUMS)
```

完整视频和动作轨迹体积较大，仍保存在结果 README 指定的原始评测目录，不包含在此轻量结果包中。
历史七任务结果单独保留在 `result/if-ext-v2-wide-20blocks/`；当前分数不与七任务 Overall 混用。
`bak/`、历史 releases 和原机部署记录用于追溯，不属于接收方默认运行路径。

## 交付检查

以下为可运行的检查入口；完整 release 校验需要原机数据。

2026-09-18 清单归档与默认入口更新：54 项相关 CPU 测试通过，覆盖默认六任务运行、
旧路径兼容、资格证据哈希及源码审计边界。12 份历史清单的 148 个原文件保持逐字节一致；历史校验通过兼容入口还原原目录布局。

2026-09-16 的 cube-v3 交付记录：相关的 **31 项 CPU 测试**通过（23 项 formal runner/report 测试、8 项分支交付测试），
seed/mode 导出、release 复用来源与完整 artifact 哈希验证通过，Bash 语法与 diff 格式检查通过。
六个 policy 的 240 个新 Arm 回合已实际完成；合并后的 2760 回合通过动作轨迹、初始场景、文件哈希和新视频帧数校验。
新旧两个结果包的 `SHA256SUMS` 均通过。CPU 入口测试覆盖全失败仍完成、异常停止、原始 seed 保留、禁止覆盖及 GPU 异常时清理本脚本的仿真进程组。

```bash
bash -n scripts/eval.sh
python -m unittest discover -s tests -p test_branch_delivery.py
# 以下使用安装好客户端依赖的 RoboTwin 环境。
python -m unittest discover -s tests -p 'test_formal*.py'
python tools/export_seed_modes.py --check
python seed-manifests/robotwin-if-arm-only-v2-20-per-mode/verify.py
```
