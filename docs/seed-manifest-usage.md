# 固定 seeds 与生成候选清单

正式评测直接使用 [20-blocks](../seed-manifests/20-blocks/README.md)，不需要重新生成 seeds。
六个 `<task>.json` 是 evaluator 的 exact-seed 输入；`seed-modes.csv` 提供 block、mode 和 scene 对照。

```bash
python tools/export_seed_modes.py --check
python tools/verify_benchmark.py
```

每任务 20 blocks，每模型 460 回合。一次 block 包含所有模式：Stapler 2、Noun 2、Attribute 8、Arm 2、Sequence 6、Spatial 3。
Spatial 沿用五槽位 seed 编码，仅取 offsets 0、1、4；不能用连续三个整数重编号。
除 Noun 外按同场景指令组配对；Attribute 一个 block 含四对独立属性场景。

## 只想预览场景

使用 [expert 采集入口](expert-review.md)：默认每任务采够一个完整 block，失败则跳过候选 block。
可传 `--seed-manifest seed-manifests/20-blocks` 加快采集。
采集时跳过候选 block 与正式评测时跳过失败回合不同：正式评测不换 seed。

## 为任务研发生成新候选 seeds

需要已安装 RoboTwin 并完成 bridge。示例生成每任务两个 expert-qualified blocks：

```bash
python tools/generate_if_seed_manifest.py --all --task-config demo_clean   --accepted-blocks 2 --max-candidate-blocks 20   --output-dir outputs/seed-candidates
python tools/validate_if_seed_manifest.py --require-evidence outputs/seed-candidates
```

生成器逐 seed 执行 expert，只接受所有模式均通过的完整 block。
达到候选上限仍未采够时返回未完成状态，不发布半个 block；相邻 `.generation.json` 保存拒绝原因与来源。
`--help` 提供单任务、候选起点与恢复选项。新候选数据不属于正式 20-block 清单。

更改场景设置后，需要针对受影响模式重新验证 expert 与配对观测；相同 seeds 本身不证明新场景仍可行。
任务设置、代码、checkpoint、instruction 与 seed 顺序共同定义可比较的评测。
