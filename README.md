# robotwin-if

复刻 [Qwen-RobotManip Technical Report](https://arxiv.org/abs/2606.17846) 中提出的 **RoboTwin-IF** (Instruction Following) 基准。

在 [RoboTwin 2.0](https://github.com/RoboTwin-Platform/RoboTwin)（作为 third-party 依赖引入，非 fork）之上实现 5 个指令跟随任务集：

- Pick-Diverse-Object
- Place-Relative
- Operate-Mic-Drawer
- Operate-Stapler
- Operate-Tabletop

范围仅限复刻基准本身（场景/干扰物/指令模板/成功判定），不训练模型。

设计文档见 Obsidian 笔记库 `工作/1-Projects/RoboTwin-IF 复刻.md`（未纳入本仓库）。

## Status

Planning — 实施计划尚未落地。
