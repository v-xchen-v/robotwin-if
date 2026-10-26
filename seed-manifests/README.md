# Seed manifests

两套清单分别保存在独立目录，均为**六任务 × 每任务 20 blocks，共 460 回合/model**：

| 版本 | Verb 任务 | 状态 |
|---|---|---|
| [robotwin-if-press-lift-bell-v1-20-per-mode](robotwin-if-press-lift-bell-v1-20-per-mode/README.md) | `press_lift_bell`：press / lift | 当前默认；expert 40/40，模型 eval 暂停 |
| [robotwin-if-arm-only-v2-20-per-mode](robotwin-if-arm-only-v2-20-per-mode/README.md) | `bottle_verb`：pick / shake | 旧版，原清单和结果保留 |

新版仅替换 Verb，其余五个任务的 flat manifest 与旧版逐字节相同，并保留原资格证据。
铃铛 episode seeds 为 `100000–100039`，每两回合共享一个初始场景；本次 expert 筛选 20 组全部通过。
配对初始三路 RGB、proprio 完全相同，两个铃铛模型 × 左右两侧各 5 组。
当前固定指令为 `Press down on the bell.` / `Lift the bell.`，均为 250 actions。
2026-10-26 已按用户要求直接覆盖原 v1 包的 Lift 配置，目录名称与所有 seeds 不变。
原始资格日志保留实测的 `Pick up the bell.`，`instruction_override` 记录文本覆盖及当前源码。
新指令的评测需使用独立输出目录，不能直接续跑并混入此前暂停运行的成绩。
具体对照及当前指令见[任务实验记录](../docs/press-lift-bell-experiment.md#2026-10-26lift-改回旧-instruction)。
不会根据模型失败删换 seeds；新版尚无正式模型成绩。

`scripts/eval.sh` 和 `tools/export_seed_modes.py` 默认使用新版；每套 `suite.yml` 决定自己的六任务列表。
旧版可通过 `--manifest-dir seed-manifests/robotwin-if-arm-only-v2-20-per-mode` 显式选择。

```bash
python tools/export_seed_modes.py --check
python seed-manifests/robotwin-if-press-lift-bell-v1-20-per-mode/verify.py
bash scripts/eval.sh --policy lingbot_va --output-dir outputs/policy-eval/bell-v1-lva --dry-run
```

新包包含本次完整筛选日志 JSON、源码快照、runtime patch、旧资格原件及校验和，校验不需要启动模拟器或模型。
原始 NPZ 初始观测留在生成运行目录，数组哈希随清单发布。模拟器版本、资产、配置与源码需一并固定才能复现。

旧 [Arm-only-v2 结果](../result/robotwin-if-arm-only-v2-20blocks/README.md)的 2760 回合不代表新版成绩。
`tools/run_formal_policy_suite.py` 保留为旧成绩复用工作流，依赖旧任务的模型元数据；新任务评测使用 `scripts/eval.sh`。
旧包的 `verify.py` 仍用于其历史来源及原机产物审计；新版验证使用上面的新版入口。
