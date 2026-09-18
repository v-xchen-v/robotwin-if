# Policy inference integrations

每个策略使用一个小写目录 `policies/<policy_name>/`，维护自己的推理环境、配置、适配代码与使用说明。采用复数 `policies`，与上游 RoboTwin 的 `policy/` 安装目录区分。

统一评测入口：[`scripts/eval.sh`](../scripts/eval.sh)。先按对应 policy README 启动一个模型服务，
再在 RoboTwin 环境执行：

```bash
bash scripts/eval.sh --policy vlact --sim-gpu 0 --model-gpu 1 \
  --output-dir outputs/policy-eval/vlact-six-tasks-20blocks
```

默认串行跑六任务的 20 blocks。支持 `--task arm_select --blocks 2` 做小规模验证，以及
`--dry-run` 查看命令。安装顺序、seed/mode 格式与结果入口见 [分支交付说明](../docs/branch-delivery.md)。

`arm_select` 的可选场景变化配置、双臂预检与独立 manifest 使用方式见
[arm_select v2 试验说明](../docs/arm-select-v2.md)。

当前六任务正式评测使用 [Arm-only-v2 20-block 清单](../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md)，
Arm 使用 cube-v3 场景和错误臂历史判据；每项 20 blocks，每个 policy 460 回合。Grasp-Approach 已暂时下线，
材料归档到 [bak/](../bak/grasp_cube_approach/README.md)，六个 evaluator 均拒绝执行该任务。

```text
policies/
├── README.md
├── xvla/                 # HTTP, stateless chunks, 20D EE6D
├── lingbot_vla/          # WebSocket, 4B VLA, absolute 14D joint chunks
├── hy_vla/               # WebSocket, six-frame MEM, blended rel+abs EE targets
├── dm05/                 # HTTP, Gemma3/action expert, absolute 14D joint chunks
├── vlact/                # WebSocket, Qwen3OFT, wrap32 absolute joint chunks
└── lingbot_va/           # WebSocket, KV cache, relative EE poses
    ├── README.md
    ├── setup_env.sh
    ├── requirements.txt
    ├── requirements-client.txt
    ├── download_checkpoint.py
    ├── serve.py
    ├── client.py
    ├── eval.py
    ├── outputs.py
    ├── patch_source.py
    └── check_env.py
```

| Policy | Checkpoint | Conda inference environment | 当前状态 |
|---|---|---|---|
| [X-VLA](xvla/README.md) | `2toINF/X-VLA-RoboTwin2` | `robotwin-if-xvla` | 初次闭环已验证：raw `click_bell` 1/1；IF `arm_select` 左成功、右失败（1/2） |
| [LingBot-VA](lingbot_va/README.md) | `robbyant/lingbot-va-posttrain-robotwin` | `robotwin-if-lingbot-va` | 初次闭环已验证：raw `click_bell` 1/1；IF `arm_select` 左右均成功（2/2） |
| [LingBot-VLA 4B](lingbot_vla/README.md) | `robbyant/lingbot-vla-4b-posttrain-robotwin` | `robotwin-if-lingbot-vla` | raw `click_bell` 1/1 成功；IF `arm_select` 完整左右 block 为 0/2，均达到动作上限，IF 成功验收尚未通过 |
| [VLAct Qwen3OFT](vlact/README.md) | `StarVLA/VLAct_Qwen3OFT_Robotwin_all_Finetune` | `robotwin-if-vlact` | 正式评测使用 All 100K；保留 Clean 50K 版本及历史结果，切换 checkpoint 后全部重跑 |
| [DM05](dm05/README.md) | `Dexmal/DM05-robotwin2` | `/Data/robotwin-if/envs/robotwin-if-dm05` | 初次闭环已验证：raw `click_bell` 1/1；IF `arm_select` 完整左右 block 为 2/2 |
| [Hy-VLA](hy_vla/README.md) | `tencent/Hy-Embodied-0.5-VLA-RoboTwin` | `/Data/robotwin-if/envs/robotwin-if-hy-vla` | 真实 checkpoint：raw `click_bell` 1/1；IF `arm_select` 完整左右 block 为 0/2，均达到 400 步上限，IF 成功验收尚未通过 |

## 环境与源码约定

- RoboTwin 仿真运行在独立的 `RoboTwin` 环境；模型服务运行在各自的 `robotwin-if-<policy>` 环境，通过客户端通信。
- 每个目录至少提供 `setup_env.sh`、依赖声明和 README；随后按需加入客户端/adapter 和推理配置。
- 第三方模型源码放在 `third_party/<policy>/`，setup 固定其 revision。模型权重保留在 Hugging Face cache 或外部 checkpoint 目录。
- 环境目录、第三方 checkout、权重和运行日志不加入 Git。这里维护安装方法及适配代码。
- 先完成一至两个策略，再从实际实现中提取公共层；公共层的目录和接口在该阶段确定。
- 评测输出统一采用 `outputs/policy-eval/<run>/<policy>/<task>/`，以 `<task>_ep<seed>` 平铺保存 summary、status、指令、日志、视频、初始图像、逐步耗时和 chunk 动作日志，参考 `smoke-blocks1/cogact/arm_select/`。可增加策略专用诊断文件；未采集字段明确标为 `null`。X-VLA 的文件语义与离线转换见其 [README](xvla/README.md#输出格式)。

## 每个策略的验收顺序

1. 安装环境并检查模块导入，启动真实 checkpoint 的推理服务。
2. **先成功完成一个 raw RoboTwin task**，记录命令、配置、seed、结果和视频。
3. **再成功完成一个选定的 RoboTwin-IF task**，使用完整的 balanced seed block 并保留失败记录。

环境检查通过只表示依赖可以导入。任务验证通过后才将策略标记为 inference 已验证。X-VLA 暂定按 `click_bell` → `arm_select` 验证。后续 refactor 和 external RoboTwin bridge 也沿用这一顺序。

## 完整 IF task suite 的小规模评测

六个 `eval.py` 均支持 canonical 六项 IF task。使用同一份固定 manifest，
`--blocks 2` 选择前两个完整 balance blocks，每种 mode 各运行两个回合：

```bash
PYTHONNOUSERSITE=1 conda run --no-capture-output -n RoboTwin \
  python policies/xvla/eval.py \
  --task attribute_select --task-config demo_clean \
  --seed-manifest seed-manifests/robotwin-if-arm-only-v2-20-per-mode/attribute_select.json \
  --blocks 2 --instruction-type unseen --sim-gpu 0 \
  --output-dir outputs/policy-eval/if-blocks2/xvla/attribute_select
```

替换 policy 和 task 即可；模型服务须已在对应默认端口运行。同一个 policy 的
有状态服务一次只接一个评测客户端。六项合计每个 policy 46 回合、六个 276 回合。
输出保留固定 seeds、每种 mode 的分母和成功数；基础设施错误标为 incomplete，
不会用新 seed 替换。源码/config 与 manifest 发布版本有差异时，先对选定的
完整 blocks 在当前环境下重新做 oracle qualification，并保留两份 provenance。

属性选择任务在 setup 后即可读取抬起高度基线，继续保留 target/distractor 联合成功判定。

## 统一的串行评测流程

六个 evaluator 共用 `policies/evaluation.py`：每个新回合先对指定 seed 执行
oracle qualification，通过后关闭 oracle 场景，再用同一个 seed 重建 policy 场景。
两次 setup 都检查 IF mode；配对资格、成功判定基线与 policy rollout hook 保留。
资格失败或场景不一致时停止，不替换 seed。

渲染使用 RoboTwin 原生路径。评测不再提供 oracle 磁盘缓存、延迟渲染开关，
也不包装 `take_action` / `get_obs`。模型本身的历史状态更新与动作解码保持原样。
`run.json` 记录公共 evaluator 的源码 SHA-256；每回合记录 oracle/setup 耗时。

正式套件使用一个 sim（GPU 0）和一个模型服务（GPU 1）串行运行，提供固定 manifest、
断点续跑、逐回合跨 policy 场景校验及 GPU 异常停止，见
[正式评测说明](../docs/formal-policy-evaluation.md)。
之前的双队列、多机分片和优化测速工具已移除；旧结果及其源码快照仍保留。
