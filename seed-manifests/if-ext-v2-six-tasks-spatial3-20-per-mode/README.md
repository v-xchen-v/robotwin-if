# IF-Ext v2：六任务、Spatial 三模式、20 blocks

当前正式清单：6 tasks × 20 blocks；每个 policy **460 回合**，6 policies 合计 **2760 回合、720 blocks**。
`place_relative` 仅含 left/right/on_top，每个 mode 20 回合；其余五项任务与上一版完全一致。

Spatial 使用 schema 2，保留原 seed：每组 `[5k, 5k+1, 5k+4]`，场景仍为 `seed // 5`。
没有重新编号、更换场景或筛选成功回合。原五模式清单及 oracle 资格证据由
`qualification-files.json` 绑定；全部 2760 回合已完成，可以按 `reusable-results.yml` 复用。
旧五模式 flat manifest 保持 schema 1，用于历史校验，当前运行入口拒绝 front/back。

- [显式 seed/mode JSON](seed-modes.json) · [CSV](seed-modes.csv)
- [套件及计数](suite.yml) · [复用清单](reusable-results.yml)
- [决策与证据](../../docs/place-relative-spatial3.md)
- [结果](../../result/if-ext-v2-six-tasks-spatial3-20blocks/README.md)

CPU 校验：`python seed-manifests/if-ext-v2-six-tasks-spatial3-20-per-mode/verify.py`。
运行：`bash scripts/eval.sh --policy <policy> --output-dir <new-output>`，先启动相应模型 server。
入口默认本目录；每个任务串行跑满 20 blocks，不自动重跑失败。
