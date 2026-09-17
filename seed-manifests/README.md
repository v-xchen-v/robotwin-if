# Seed releases

当前正式套件为六项任务，使用 [RoboTwin-IF cube-v3 taskset](robotwin-if-cube-v3-20-per-mode/README.md)：
每项 20 blocks、460 回合/policy，六个 policies 合计 2760 回合、720 blocks。

Arm-Select 配置为 `demo_clean_arm_select_v3`，左右臂各 20；其 [20-block 资格证据](arm-select-cube-v3-20-per-mode/README.md)
已通过 oracle 配对验证。其余五任务保留上一版清单；本轮复用最新 Bottle v6 结果中的 2520 回合，只重跑 Arm-Select 的 240 回合。

其余 release 目录保留历史发布或开发验证范围，不作为当前全量运行入口。
其中 grasp 的 seed 和资格证据仍完整保留；任务实现已移动到 [bak/](../bak/grasp_cube_approach/README.md)。
