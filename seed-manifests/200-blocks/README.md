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
含逐 seed 资格记录、分片证据、源码快照和日志。本目录提交输入清单与验证摘要：

- `qualification.json`：最终合并验证结果，包括数量、mode 分母、旧前缀一致及新增资格证据校验。
- `SHA256SUMS`：本目录所有文件的校验值，自身除外。

在仓库根目录验证六份输入的完整 blocks、顺序、唯一性和模式数量：

```bash
python tools/validate_if_seed_manifest.py \
  seed-manifests/200-blocks/{press_lift_stapler,pick_diverse_object,attribute_select,arm_select,stack_sequence,place_relative}.json
(cd seed-manifests/200-blocks && sha256sum --check SHA256SUMS)
```

上述离线检查不重跑 expert；`qualification.json` 是已完成验证的摘要，不代替原始逐 seed 证据。
当前 `scripts/eval.sh` 的 suite 加载器固定为 20 blocks，尚未适配此扩展清单；
不能仅替换其 `--manifest-dir` 就运行 200-block suite。
