# 工具入口

常规运行使用 `bash scripts/collect.sh` 或 `bash scripts/eval.sh`。工具按用途如下：

| 用途 | 入口 |
|---|---|
| 校验交付的 seeds、成绩与文件哈希 | [verify_benchmark.py](verify_benchmark.py) |
| 汇总 evaluator 输出 | [summarize_formal_policy_results.py](summarize_formal_policy_results.py) |
| 采集 expert blocks | [collect_if_expert.py](collect_if_expert.py)，见 [expert review](../docs/expert-review.md) |
| 生成/校验候选 seeds | [generate_if_seed_manifest.py](generate_if_seed_manifest.py)、[validate_if_seed_manifest.py](validate_if_seed_manifest.py) |
| 导出/核对 seed-mode 对照 | [export_seed_modes.py](export_seed_modes.py) |
| Stapler 场景可行性检查 | [press_lift_stapler.py](press_lift_stapler.py) |
| Noun 物体池检查与报告 | [probe_pick_diverse_unseen.py](probe_pick_diverse_unseen.py)、[render_pick_pool_snapshots.py](render_pick_pool_snapshots.py)、[report_pick_diverse_object.py](report_pick_diverse_object.py) |
| 模型 × 任务成绩与视频 | [policy-video-review](policy-video-review/README.md)，`just video-review-azure` |
| 资产与采集视频 | [object-gallery](object-gallery/README.md)、[dataset-viewer](dataset-viewer/index.html) |
| 抽帧与采集进程管理 | [extract_frames.sh](extract_frames.sh)、[kill_collect.sh](kill_collect.sh) |

`press_lift_bell.py`、`bell_seed_audit.py` 是 Stapler 仍在使用的共享 runner 和配对观测检查模块；
文件名不代表 Bell 是当前任务。`sim_device.py` 为仿真选择设备；`_pick_diverse_probe_logic.py` 支持 Noun probe。
