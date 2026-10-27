# 当前工具入口

当前发布是 **Press/Lift Stapler v1：六任务、每任务 20 blocks、六个开源 checkpoint**。
常规评测从 [`scripts/eval.sh`](../scripts/eval.sh) 启动；工具按用途如下。

| 用途 | 入口 |
|---|---|
| 采集完整 expert blocks，人工查看各 mode 场景和动作 | [collect_if_expert.py](collect_if_expert.py)，入口 `bash scripts/collect.sh`，见 [expert review](../docs/expert-review.md) |
| 生成 expert-qualified seeds、保留拒绝记录 | [generate_if_seed_manifest.py](generate_if_seed_manifest.py) |
| 校验 flat manifest / generation evidence | [validate_if_seed_manifest.py](validate_if_seed_manifest.py) |
| 导出或核对 seed/mode | [export_seed_modes.py](export_seed_modes.py) |
| 构建、校验当前六任务清单 | [release_press_lift_stapler_v1.py](release_press_lift_stapler_v1.py) |
| 复用其余五任务的 2520 回合，准备 Stapler 的 240 回合 | [prepare_stapler_policy_suite.py](prepare_stapler_policy_suite.py) |
| 正式运行、状态与完整性校验 | [run_formal_policy_suite.py](run_formal_policy_suite.py) |
| 双路 Stapler eval | [run_parallel_stapler_suite.py](run_parallel_stapler_suite.py) |
| 汇总成绩、发布完成的六任务结果 | [summarize_formal_policy_results.py](summarize_formal_policy_results.py)、[publish_stapler_policy_results.py](publish_stapler_policy_results.py) |
| Stapler 配对场景可行性检查 | [press_lift_stapler.py](press_lift_stapler.py) |
| Noun 当前物体池诊断、真实贴图与采集报告 | [probe_pick_diverse_unseen.py](probe_pick_diverse_unseen.py)（`--production-seeds`）、[render_pick_pool_snapshots.py](render_pick_pool_snapshots.py)、[report_pick_diverse_object.py](report_pick_diverse_object.py) |
| 视频人工复核 | [policy-video-review](policy-video-review/README.md)，`just video-review` 默认打开当前 Stapler 运行目录 |
| 原生物体、采集视频浏览 | [object-gallery](object-gallery/README.md)（`just gallery`）、[dataset-viewer](dataset-viewer/index.html)（`just dataset-viewer`） |
| 视频抽帧、采集进程管理 | [extract_frames.sh](extract_frames.sh)、[kill_collect.sh](kill_collect.sh) |

只读校验当前发布：

```bash
python tools/export_seed_modes.py --check
python tools/release_press_lift_stapler_v1.py
```

运行环境与参数见[正式评测](../docs/formal-policy-evaluation.md)、[seed 使用指南](../docs/seed-manifest-usage.md)和[发布溯源](../docs/release-provenance.md)。
生成 seeds、场景 probe 和 eval 需要 RoboTwin 仿真环境；配对 pilot 的分数独立于正式结果。

仍在使用的共享模块：

- `press_lift_bell.py`、`bell_seed_audit.py`：Stapler pilot runner 与配对 RGB/proprio/位姿审计。
- `run_remote_attribute_suite.py`、`run_sharded_remote_suite.py`、`remote_eval_support.py`：远端调度；其中冷却、硬件查询等 helper 也供 Stapler 双路 eval 使用。
- `sim_device.py`：仿真设备选择；`_pick_diverse_probe_logic.py`：Noun probe 逻辑。
- `release_history.py`：从固定 Git 提交读取五任务的原始结果与 checkpoint 身份。

旧任务报告、一次性渲染、旧 release CLI 的清单与原文件见[清理记录](../docs/archive/obsolete-tool-scripts.md)。
