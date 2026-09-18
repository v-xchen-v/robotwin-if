# Grasp-Approach（暂时下线）

2026-09-15 按任务维护决定，`grasp_cube_approach` 暂时退出 RoboTwin-IF，当前正式套件为六项。
下线原因：当前模型在该任务上的表现不足，暂不纳入现行评测范围。

这里按原仓库相对路径保留 env、instruction JSON、v2 config、专用测试、probe 与设计说明。
`tests/test_if_policy_evaluation.py` 是下线前的共享测试快照，包含方向判定回归测试。
这些文件不再通过默认 bridge 安装，不参与 `--all` seed 生成或正常 policy 评测。
归档脚本中的路径反映原目录结构；本目录不是可直接启动的评测入口。

历史七任务清单与结果只保留在 Git 历史中，不作为当前目录中的备选入口。
`if_benchmark.seed_contracts.ARCHIVED_SEED_CONTRACTS` 仅保留读取旧 manifest/结果所需的 mode 与 block 元数据。

当前正式清单是 [Arm-only-v2 六任务清单](../../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md)。
当前报告默认不含 grasp，Overall 为六个 Task Avg. 等权平均。
需还原旧七任务报告时，给 `tools/summarize_formal_policy_results.py` 加 `--include-archived-tasks`。
不要将删除任务后的 Overall 与旧七任务分数当作相同指标比较。

若以后恢复任务，应将文件放回原相对路径，重新加入 inventory/bridge/seed contracts，
恢复相关测试并重新完成任务资格验证；不能仅把 env 软链回去。
