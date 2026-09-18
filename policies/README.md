# Policy inference integrations

本目录维护六个开源 policy 的独立模型环境、推理服务、客户端和评测适配。
模型服务与 RoboTwin 仿真分别运行；安装、权重下载、服务启动及输出格式见各 policy README。

| Policy | 当前 checkpoint | 通信与动作接口 |
|---|---|---|
| [X-VLA](xvla/README.md) | `2toINF/X-VLA-RoboTwin2` | HTTP；20D EE6D action chunks |
| [LingBot-VA](lingbot_va/README.md) | `robbyant/lingbot-va-posttrain-robotwin` | WebSocket；有状态视觉历史 |
| [LingBot-VLA](lingbot_vla/README.md) | `robbyant/lingbot-vla-4b-posttrain-robotwin` | WebSocket；absolute 14D joint chunks |
| [VLAct](vlact/README.md) | `StarVLA/VLAct_Qwen3OFT_Robotwin_all_Finetune` | WebSocket；32-action joint chunks |
| [DM05](dm05/README.md) | `Dexmal/DM05-robotwin2` | HTTP；absolute 14D joint chunks |
| [Hy-VLA](hy_vla/README.md) | `tencent/Hy-Embodied-0.5-VLA-RoboTwin` | WebSocket；六帧历史，relative/absolute EE 融合 |

六个 policy 的完整正式结果已发布，见[当前结果包](../result/robotwin-if-arm-only-v2-20blocks/README.md)。
X-VLA 使用 clean 微调权重，其他五个使用 clean + randomized 权重，比较时须保留这项训练数据差异。
Checkpoint revisions、模型参数和各回合来源随结果包记录。

## 运行

先按对应 README 启动模型服务，再在 RoboTwin 环境从仓库根目录执行：

```bash
# 默认六任务、每任务 20 blocks；不连接模型或启动仿真。
bash scripts/eval.sh --policy vlact --output-dir outputs/policy-eval/vlact-new --dry-run

# 实际运行：sim GPU 0，模型服务 GPU 1。
bash scripts/eval.sh --policy vlact --sim-gpu 0 --model-gpu 1 \
  --output-dir outputs/policy-eval/vlact-new

# 一个任务的前两个完整 blocks。
bash scripts/eval.sh --policy hy_vla --task arm_select --blocks 2 \
  --output-dir outputs/policy-eval/hy-vla-arm-pilot
```

默认使用[当前六任务清单](../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md)：
每个 policy 460 回合；六任务各取两个 blocks 时为 46 回合。
Arm 使用 `demo_clean_arm_select_v3` 与[错误手臂历史判据](../docs/arm-select-target-arm-only.md)。
Grasp-Approach 已下线，所有 evaluator 都拒绝执行该任务。

同一个有状态模型服务一次只接一个客户端。需要并发时使用独立服务实例，
见[正式评测与远端调度](../docs/formal-policy-evaluation.md)。
新机器安装、task bridge、参数与文件格式见[交付说明](../docs/branch-delivery.md)。

## 评测契约

六个 evaluator 共用 `policies/evaluation.py`：每回合先对固定 seed 做 oracle qualification，
关闭场景后用同一个 seed 重建 policy 场景，并检查 mode、配对资格和成功判据基线。
完成的 policy failure 是有效结果；基础设施错误停止评测，不替换 seed。
Bottle pick 在完整动作预算结束后裁决；其他任务保留各自的终止协议。

模型历史状态更新、动作解码和输出转换由各 policy 适配器维护。
输出目录为 `<output-dir>/<policy>/<task>/`，包含逐回合指令、视频、动作、初始观测、
耗时与判定；已有 task 输出目录不会覆盖。`run.json` 记录公共 evaluator 的源码 SHA-256。
第三方源码、权重、Conda 环境及仿真原始产物不加入 Git。
