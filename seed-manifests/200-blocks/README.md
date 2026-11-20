# 六任务 200-block seed 清单

2026-11-20 生成，每个任务 **200 个完整 blocks**，每个 mode **200 episodes**，共 **4,600 episodes**。
六份 `<task>.json` 与生成结果逐字节一致，可作为单任务 evaluator 的 exact-seed 输入。

| 任务 | task_config | Blocks | Episodes |
| --- | --- | ---: | ---: |
| press_lift_stapler | demo_clean | 200 | 400 |
| pick_diverse_object | demo_clean | 200 | 400 |
| attribute_select | demo_clean | 200 | 1,600 |
| arm_select | demo_clean_arm_select | 200 | 400 |
| stack_sequence | demo_clean | 200 | 1,200 |
| place_relative | demo_clean | 200 | 600 |

每份清单的前 20 blocks 与 [20-blocks](../20-blocks/README.md) 的 seeds、顺序及配置完全一致，
沿用其资格证据；新增 180 blocks 均经过 expert 筛选，只有全部模式通过的完整 block 才被接受。
新清单尚无对应的 policy 评测成绩，现有 `result/` 仍对应原 20-block 清单。

Attribute 的新增部分由先前已通过的 92 blocks 和六个分片的 88 blocks 组成。
分片目标为 15/15/15/15/14/14，使用互不重叠的候选范围，合并时按 seed 区间排序；
已通过的记录和拒绝记录均保留。Spatial 继续使用五槽位编码中的 offsets 0、1、4。

生成使用任务源码提交 `777eff4a8839a50c8345326f3b58a1a3cc7505c2`，
沿用当前 6 cm / 4 cm Size 设置和 `demo_clean_arm_select` 配置。
完整原始记录保存在生成机器的 `/Data/robotwin-if/seed-manifests/200-blocks-20261120/`，
含逐 seed 资格记录、分片证据、源码快照和日志。本目录包含输入清单、评测入口配置与验证摘要：

- `suite.yml`：六任务的配置、manifest 哈希、模式分母和每模型 4,600 回合的总计划。
- `seed-modes.json` / `seed-modes.csv`：4,600 条逐回合 seed、mode、block 映射，供入口校验和核对。
- `qualification.json`：最终合并验证结果，包括数量、mode 分母、旧前缀一致及新增资格证据校验。
- `SHA256SUMS`：本目录所有文件的校验值，自身除外。

在仓库根目录验证六份输入的完整 blocks、顺序、唯一性和模式数量：

```bash
python tools/validate_if_seed_manifest.py \
  seed-manifests/200-blocks/{press_lift_stapler,pick_diverse_object,attribute_select,arm_select,stack_sequence,place_relative}.json
python tools/export_seed_modes.py --manifest-dir seed-manifests/200-blocks --check
(cd seed-manifests/200-blocks && sha256sum --check SHA256SUMS)
```

上述离线检查不重跑 expert；`qualification.json` 是已完成验证的摘要，不代替原始逐 seed 证据。

评测和汇总入口已支持本套件。两者默认仍为原 20-block 计划，运行本套件时同时指定
`--manifest-dir seed-manifests/200-blocks --blocks 200`。以下以 VLAct 为例：

```bash
# 预览完整计划，不启动模型或仿真。
bash scripts/eval.sh --policy vlact \
  --manifest-dir seed-manifests/200-blocks --blocks 200 \
  --output-dir outputs/policy-eval/vlact-200blocks --dry-run

# 按 policies/vlact/README.md 准备模型服务后运行。
bash scripts/eval.sh --policy vlact --sim-gpu 0 --model-gpu 1 \
  --manifest-dir seed-manifests/200-blocks --blocks 200 \
  --output-dir outputs/policy-eval/vlact-200blocks

# 按全部 200 blocks 汇总，沿用现有计分规则。
python tools/summarize_formal_policy_results.py \
  --run-dir outputs/policy-eval/vlact-200blocks \
  --manifest-dir seed-manifests/200-blocks --blocks 200 \
  --output outputs/report/vlact-200blocks.md
```

更多运行约束见 [评测说明](../../docs/formal-policy-evaluation.md)。
