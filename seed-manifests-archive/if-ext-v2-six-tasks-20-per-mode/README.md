# Formal IF v2: six tasks, 20 blocks

2026-09-15 从七任务 20-block release 中移除 `grasp_cube_approach`，其余六项的 config、
seeds、顺序、完整 block、指令 split 均保持原样；arm_select 继续使用 v2。
这是任务范围调整，没有重新挑选 seeds 或重新运行 oracle/model。

| Task | Config | Episodes per policy |
|---|---|---:|
| bottle_verb | demo_clean | 40 |
| pick_diverse_object | demo_clean | 40 |
| attribute_select | demo_clean | 160 |
| arm_select | demo_clean_arm_select_v2 | 40 |
| stack_sequence | demo_clean | 120 |
| place_relative | demo_clean | 100 |
| 合计 | | 500 |

提供两种互相校验的格式：

- 六份 `<task>.json`：evaluator 直接使用的 flat manifest，保留原始 seeds 和文件哈希。
- [`seed-modes.json`](seed-modes.json) / [`seed-modes.csv`](seed-modes.csv)：显式列出 500 条 `task/config/block/seed/mode`，附 scene index 与 block offset，方便交付方直接读取。

`block` 是每个任务清单内从 0 到 19 的顺序编号；不是 `seed // block_size`。
不同任务的一个 block 分别含 2、2、8、2、6、5 个 modes，因此每个 policy 合计 500 回合。

```bash
python tools/export_seed_modes.py --check
```

六个 policies 共 3000 回合、720 个完整 blocks。这些回合在原七任务最终运行
`/Data/robotwin-if/evaluations/if-seven-tasks-v2-wide-20blocks-001` 中已经完成。
`reusable-results.yml` 索引全部 3000 条成功和失败，记录原始文件与 provenance 的 SHA-256；
没有按回合成败筛选。VLAct 沿用 All checkpoint，旧 Clean checkpoint 不进入索引。

`qualification-files.json` 绑定原发布的六项 flat manifests 与 oracle qualification 文件。
这些历史证据留在原 release 目录；本目录六份 flat JSON 与其逐字节一致。
验证只检查发布与复用索引的一致性，不重新宣称做过新的 oracle qualification：

```bash
python seed-manifests/if-ext-v2-six-tasks-20-per-mode/verify.py
```

结果汇总默认采用六任务范围，不必先复制原始视频或重跑模型：

```bash
python tools/summarize_formal_policy_results.py \
  --run-dir /Data/robotwin-if/evaluations/if-seven-tasks-v2-wide-20blocks-001 \
  --output outputs/policy-eval/reports/results-six-tasks.md
```

六任务 Overall 是六个 Task Avg. 等权平均；原七任务报告及其指标保留，不覆盖。
