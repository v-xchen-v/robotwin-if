# Seed manifests

本目录仅保留 [Press/Lift Stapler v1](robotwin-if-press-lift-stapler-v1-20-per-mode/README.md)：
**6 个任务 × 每任务 20 blocks，460 回合/model；6 个开源 checkpoint 合计 2760 回合**。

| 任务 | 每个模型的回合数 |
|---|---:|
| `press_lift_stapler`：press / lift | 40 |
| `pick_diverse_object` | 40 |
| `attribute_select` | 160 |
| `arm_select` | 40 |
| `stack_sequence` | 120 |
| `place_relative` | 60 |

订书器 seeds 为 `110000–110039`，20 组 expert 全部通过；每组 Press/Lift 的初始图像、机器人状态和位姿一致。
订书器 yaw ±15°，两个 distractor 各自 yaw ±180°，由 scene seed 固定。
其余五份 flat manifests 沿用已验证的 seeds。

`suite.yml`、六份任务 JSON 和 seed/mode 导出保持原样。`qualification/` 内的父版本描述、
继承资格证据与源码快照用于独立校验当前清单，不是额外可选的旧版任务集。
资格文件记录清单发布时的状态；最终 [六模型评测结果](../result/robotwin-if-press-lift-stapler-v1-20blocks/README.md)
已全部完成：Stapler 新跑 240 回合，其余五任务复用 2520 回合。

```bash
python tools/export_seed_modes.py --check
python seed-manifests/robotwin-if-press-lift-stapler-v1-20-per-mode/verify.py
bash scripts/eval.sh --policy lingbot_va --output-dir outputs/policy-eval/stapler-v1-lva --dry-run
```

当前清单的验证和新的 policy eval 不依赖已移除的 Arm-only-v2、Bell 清单目录。
旧版清单及其发布工具使用方式见[备份分支](https://github.com/v-xchen-v/robotwin-if/tree/master-261027-staper-v1)。
