# Seed manifests

当前使用 **Press/Lift Stapler + 其余五任务**，每个任务 20 blocks，共 460 回合/model。

| 版本 | Verb 任务 | 状态 |
|---|---|---|
| [Press/Lift Stapler v1](robotwin-if-press-lift-stapler-v1-20-per-mode/README.md) | `press_lift_stapler`：press / lift | 当前默认，随机朝向 |
| [Arm-only-v2](robotwin-if-arm-only-v2-20-per-mode/README.md) | `bottle_verb`：pick / shake | 旧版，保留原清单和结果 |

新版不包含 Bell 或 Bottle。其余五份 flat manifest 与旧版逐字节相同。
订书器 seeds 为 `110000–110039`，20 组 expert 全部通过；每组 Press/Lift 的初始图像、机器人状态和位姿一致。
订书器 yaw ±15°，两个 distractor 各自 yaw ±180°，由 scene seed 固定。
本版尚未进行模型 eval；固定朝向 pilot 的成绩不属于本 manifest。

旧 Bell 清单已移至 [bak](../bak/robotwin-if-press-lift-bell-v1-20-per-mode/README.md)。
`scripts/eval.sh`、`tools/export_seed_modes.py` 和默认 IF inventory 均使用 Stapler 版本。

```bash
python tools/export_seed_modes.py --check
python seed-manifests/robotwin-if-press-lift-stapler-v1-20-per-mode/verify.py
bash scripts/eval.sh --policy lingbot_va --output-dir outputs/policy-eval/stapler-v1-lva --dry-run
```

每套 `suite.yml` 指定任务、配置和 seeds；`qualification/` 保存新旧资格证据，`SHA256SUMS` 校验文件。
旧 Arm-only-v2 可用 `--manifest-dir seed-manifests/robotwin-if-arm-only-v2-20-per-mode` 显式选择。
