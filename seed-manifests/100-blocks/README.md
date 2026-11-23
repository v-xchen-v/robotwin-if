# 六任务 100-block seed 清单

从 [200-blocks](../200-blocks/README.md) 的每份 manifest 按原始顺序取前 **100 个完整 blocks**，
每个 mode **100 episodes**，每模型共 **2,300 episodes**。
这里的 block 是清单中的完整模式组；截取使用清单序号，不按 seed 数值划分区间。

| 任务 | task_config | Blocks | Episodes |
| --- | --- | ---: | ---: |
| press_lift_stapler | demo_clean | 100 | 200 |
| pick_diverse_object | demo_clean | 100 | 200 |
| attribute_select | demo_clean | 100 | 800 |
| arm_select | demo_clean_arm_select | 100 | 200 |
| stack_sequence | demo_clean | 100 | 600 |
| place_relative | demo_clean | 100 | 300 |

前 20 blocks 与 [20-blocks](../20-blocks/README.md) 完全一致，其后 80 blocks 来自已有的 expert-qualified 扩展。
所有 seeds、顺序及任务配置均沿用来源清单，step limit 和计分规则保持不变。
本次只截取已有清单，资格证据沿用 [200-blocks/qualification.json](../200-blocks/qualification.json)
及其指向的原始记录，没有重新运行 expert 或 policy。现有 `result/` 仍对应原 20-block 评测。

本目录包含：

- 六份 `<task>.json`：供 evaluator 直接消费的 exact-seed 清单。
- `suite.yml`：任务配置、manifest 哈希、模式分母及每模型总回合数。
- `seed-modes.json` / `seed-modes.csv`：2,300 条 seed、mode、block 映射。
- `derivation.json`：来源提交、来源文件哈希、截取范围及各任务的前缀校验记录。
- `SHA256SUMS`：本目录全部文件的 SHA-256，自身除外。

在仓库根目录验证：

```bash
python tools/validate_if_seed_manifest.py \
  seed-manifests/100-blocks/{press_lift_stapler,pick_diverse_object,attribute_select,arm_select,stack_sequence,place_relative}.json
python tools/export_seed_modes.py --manifest-dir seed-manifests/100-blocks --check
(cd seed-manifests/100-blocks && sha256sum --check SHA256SUMS)
```

评测入口默认仍为原 20-block 计划。使用本套件时同时指定清单和 `--blocks 100`，以下以 VLAct 为例：

```bash
# 仅预览计划；模型服务准备好后，移除 --dry-run 启动评测。
bash scripts/eval.sh --policy vlact \
  --manifest-dir seed-manifests/100-blocks --blocks 100 \
  --output-dir outputs/policy-eval/vlact-100blocks --dry-run

# 对本次 100-block 运行按全部结果汇总。
python tools/summarize_formal_policy_results.py \
  --run-dir outputs/policy-eval/vlact-100blocks \
  --manifest-dir seed-manifests/100-blocks --blocks 100 \
  --output outputs/report/vlact-100blocks.md
```

完整运行要求见 [评测说明](../../docs/formal-policy-evaluation.md)。
