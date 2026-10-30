# 使用交付的 benchmark

[Quickstart](quickstart.md)覆盖安装、expert 预览和首次 policy 运行。
[评测说明](formal-policy-evaluation.md)覆盖固定 seeds、参数和成绩汇总。

- 任务定义：`tasks/`，清单 `eval_cfg/if_tasks.yml`。
- 固定 seeds：`seed-manifests/20-blocks/`。
- 当前六模型成绩：`result/`。
- 本机已下载输出的入口：`outputs/policy-eval/benchmark/`，不提交 Git。
- 完整视频、动作、观测与来源证据：[下载说明](download-results.md)。

仓库内离线校验：`python tools/verify_benchmark.py`。
新 checkout 的 bridge 使用固定 runtime；已修改或外部 runtime 的兼容接入见 [task bridge](task-bridge.md)。
