# 六任务评测清单：20 blocks / task

本目录随 README 结果展示提供已完成评测的只读 seed/mode 清单。
六份 `<task>.json` 与 [结果包中的冻结 manifests](../../result/if-ext-v2-six-tasks-20blocks/manifests/) 逐字节一致，
没有重新挑选 seeds、排除失败回合或重新运行评测；Arm-Select 使用 v2，Grasp-Approach 不在本版范围中。

| Task | Config | Modes/block | Episodes/policy |
|---|---|---:|---:|
| bottle_verb | demo_clean | 2 | 40 |
| pick_diverse_object | demo_clean | 2 | 40 |
| attribute_select | demo_clean | 8 | 160 |
| arm_select | demo_clean_arm_select_v2 | 2 | 40 |
| stack_sequence | demo_clean | 6 | 120 |
| place_relative | demo_clean | 5 | 100 |
| 合计 | | 25 | 500 |

- `<task>.json`：任务名、配置名与原始 `seeds` 列表，保持 evaluator 的 flat manifest 格式。
- [seed-modes.json](seed-modes.json)：显式列出各任务 config、manifest SHA-256、mode 分母，以及每回合的 seed、mode、block 与 scene 信息。
- [seed-modes.csv](seed-modes.csv)：同样信息的 500 行平表。

`block` 是各任务清单内从 0 到 19 的顺序编号，不等于 `seed // block_size`；候选 seeds 可能存在间隔。
每个 mode 均有 20 回合。不同任务的 block 大小不同，六个 policies 共 3000 回合、720 个完整 blocks。

这份只读清单用于追溯 README 的结果；发布/续跑工具、oracle 资格证据与复用索引属于独立的评测交付改动。
当前统计见 [六任务结果包](../../result/if-ext-v2-six-tasks-20blocks/README.md)，原始七任务结果单独保存在 [历史结果包](../../result/if-ext-v2-wide-20blocks/README.md)。
