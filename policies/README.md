# Policy inference integrations

每个策略使用一个小写目录 `policies/<policy_name>/`，维护自己的推理环境、配置、适配代码与使用说明。采用复数 `policies`，与上游 RoboTwin 的 `policy/` 安装目录区分。

```text
policies/
├── README.md
└── xvla/
    ├── README.md
    ├── setup_env.sh
    └── requirements.txt
```

| Policy | Checkpoint | Conda inference environment | 当前状态 |
|---|---|---|---|
| [X-VLA](xvla/README.md) | `2toINF/X-VLA-RoboTwin2` | `robotwin-if-xvla` | 本地环境安装、模块导入和 CUDA 检查通过；模型加载及任务验证待完成 |

## 环境与源码约定

- RoboTwin 仿真运行在独立的 `RoboTwin` 环境；模型服务运行在各自的 `robotwin-if-<policy>` 环境，通过客户端通信。
- 每个目录至少提供 `setup_env.sh`、依赖声明和 README；随后按需加入客户端/adapter 和推理配置。
- 第三方模型源码放在 `third_party/<policy>/`，setup 固定其 revision。模型权重保留在 Hugging Face cache 或外部 checkpoint 目录。
- 环境目录、第三方 checkout、权重和运行日志不加入 Git。这里维护安装方法及适配代码。
- 先完成一至两个策略，再从实际实现中提取公共层；公共层的目录和接口在该阶段确定。

## 每个策略的验收顺序

1. 安装环境并检查模块导入，启动真实 checkpoint 的推理服务。
2. **先成功完成一个 raw RoboTwin task**，记录命令、配置、seed、结果和视频。
3. **再成功完成一个选定的 RoboTwin-IF task**，使用完整的 balanced seed block 并保留失败记录。

环境检查通过只表示依赖可以导入。任务验证通过后才将策略标记为 inference 已验证。X-VLA 暂定按 `click_bell` → `arm_select` 验证。后续 refactor 和 external RoboTwin bridge 也沿用这一顺序。
