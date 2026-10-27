# 过时 tools 脚本清理

当前入口见 [tools/README.md](../../tools/README.md)。从 `tools/` 移除 12 个旧脚本；
原文件均保存在已推送的[清理前提交 `b5e67ce`](https://github.com/v-xchen-v/robotwin-if/tree/b5e67ce66dd550a9024869f06389d1c0618557ef/tools)。

| 移除的脚本 | 原因与当前入口 |
|---|---|
| `report_operate_stapler.py`、`report_operate_tabletop.py` | 对应已停用的实验任务。 |
| `report_place_relative.py` | 固定按 `seed % 2` 统计 beside/on_top，不适用于当前 left/right/on_top；当前正式成绩使用 `summarize_formal_policy_results.py`。 |
| `render_distractor_thumbs.py`、`render_pick_pool_thumbs.py`、`render_place_pool_candidates.py` | 旧 Operate distractors、最初 12-item Seen 池和早期 Spatial 候选的一次性渲染。当前物体浏览器及完整 Noun pool snapshots 保留。 |
| `probe_arm_select_variation.py` | 早期 v2/cube-v3 对照，依赖已清理的 fixed-v1 参考观测。当前 Arm 判据回归与固定清单保留。 |
| `task_diag.py` | 旧采集诊断在 setup 失败后自动换 seed，仍用原 seed 标记，并跳过完全失败的 setup。当前固定 seed 资格流程用 `generate_if_seed_manifest.py` 保存每个候选 block 的实际结果。 |
| `release_arm_select_target_only_v2.py`、`release_press_lift_bell_v1.py` | 旧 Arm/Bell 发布目录已下线；当前使用 `release_press_lift_stapler_v1.py`。 |
| `prepare_bell_policy_suite.py`、`publish_bell_policy_results.py` | 活跃逻辑合并到对应 Stapler 入口，保留五任务复用审计与完成校验。 |

旧 Arm verifier 专用的历史目录恢复函数及 7 项测试同时退休。当前包 checksum、2520 条复用行、
checkpoint 身份与固定 Git parent 读取测试继续保留。历史源码快照中的旧脚本名属于发布证据，保持原样。

Bell 命名的共享 runner/seed audit、远端 Attribute 调度 helper 仍被当前工具调用，继续保留。
`just video-review` 默认目录更新为当前 Stapler 运行；现有服务不重启。

清理后根目录 CPU 回归 **253 项全部通过**，当前 manifest 校验、eval dry-run、现有工具 CLI 与
formal 源码快照路径检查通过。当前 seeds、发布结果与原始视频保持原样；本次未运行 GPU 仿真或模型评测。
