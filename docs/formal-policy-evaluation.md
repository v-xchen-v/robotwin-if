# 运行与汇总评测

使用固定的 `seed-manifests/20-blocks/`，六任务每任务 20 blocks，每模型 460 回合。
先按 [Quickstart](quickstart.md) 安装 RoboTwin、bridge 和所选 policy，再按 [policies](../policies/README.md) 启动模型服务。

```bash
# 预览计划，不连接服务或写输出。
bash scripts/eval.sh --policy vlact --output-dir outputs/policy-eval/my-run --dry-run

# 模型已在 GPU 1 上服务；仿真使用 GPU 0。
bash scripts/eval.sh --policy vlact --sim-gpu 0 --model-gpu 1   --output-dir outputs/policy-eval/my-run

# 小规模接入检查：一个完整 Press/Lift block。
bash scripts/eval.sh --policy vlact --task press_lift_stapler --blocks 1   --output-dir outputs/policy-eval/smoke
```

输出为 `<output-dir>/<policy>/<task>/`，包含逐回合 JSON、`results.jsonl`、summary、动作和视频。
已存在的任务输出目录会被拒绝，避免覆盖结果。Policy failure 是有效结果；基础设施错误或 oracle 失败会停止，不替换 seed。
不同 policy 可以使用同一输出根目录，各自写入独立子目录。

## 汇总

```bash
python tools/summarize_formal_policy_results.py   --run-dir outputs/policy-eval/my-run --output outputs/report/results.md
```

自动发现已运行的公开模型，输出 Markdown、HTML、JSON、CSV。
用 `--blocks N` 指定本次计划的 blocks 数（默认 20）；任务未完成时只统计完整均衡 blocks，Overall 留空。
每个任务内各 mode 等权，Overall 为六个任务等权平均。汇总检查 exact seeds、mode、逐回合 JSON 与索引；
若有 provenance 文件，还检查记录 SHA-256。

完整已发布结果的校验使用 `python tools/verify_benchmark.py`；浏览全部视频使用 `just video-review-azure`。
本仓库只维护通用 evaluator 和汇总入口，不要求历史迁移脚本、旧结果目录或作者机器路径。

## 参数与运行约束

`bash scripts/eval.sh --help` 列出 `--server-url`、`--robotwin-dir`、`--python`、`--manifest-dir` 等选项。
默认一个模型服务和一个串行 simulator，使用独立 GPU；温度或显存超限会停止当前 simulator。
固定清单按原始顺序消费，不能跳过已完成失败、排序、补 seed 或混入不同设置的输出。
