# Benchmark 设计依据

本项目受 [Qwen-RobotManip Technical Report](https://arxiv.org/abs/2606.17846) §6.2.1 的 instruction-following 评测启发，
在 [RoboTwin 2.0](https://github.com/RoboTwin-Platform/RoboTwin) 上独立实现六个诊断轴。
场景分布、阈值、干扰物和成功判据由本仓库定义，不宣称与论文未公开的实现逐参数一致。

设计从原生 50 个任务中已有的原子动作出发，在共享场景中改变动作、物体、属性、手臂、顺序或空间关系。
除 Noun 外，同组指令使用 pixel-equal 初始观测；Noun Seen/Unseen 使用独立物体池。
干扰物的位置和朝向在不同场景间随机化，在组内保持一致，减少场景直接暗示动作的机会。

[当前任务设计与结果](../README.md) · [任务设计原则](task-design/被测行为须在能力库内-IF避免塌成OOD.md) ·
[实施流程](task-design/IF任务实现流水线-SOP.md) · [原生动作选型](task-design/native-动词清单-verb选型参考.md)
