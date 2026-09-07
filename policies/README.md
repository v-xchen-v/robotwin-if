# Policy inference integrations

每个策略使用一个小写目录 `policies/<policy_name>/`，维护自己的推理环境、配置、适配代码与使用说明。采用复数 `policies`，与上游 RoboTwin 的 `policy/` 安装目录区分。

```text
policies/
├── README.md
├── xvla/                 # HTTP, stateless chunks, 20D EE6D
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
