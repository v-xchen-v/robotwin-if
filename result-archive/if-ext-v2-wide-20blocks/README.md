# IF-Ext v2 wide：七任务 × 20 blocks

最终结果于 **2026-09-15 00:31 UTC** 通过完整性校验。六个 policies 均完成七项任务各 20 blocks：
**3240/3240 回合、840/840 blocks、42/42 个 policy-task 组合**。
其中 1944 回合复用已验证的 12-block 结果，1296 回合为本次新增；成功与 policy failure 均保留。

| Policy | 成功回合 | 已完成 / 计划回合 | 已完成 / 计划 blocks | Overall（7 tasks，%） |
|---|---:|---:|---:|---:|
| X-VLA | 176 | 540/540 | 140/140 | 34.8 |
| LingBot-VA | 298 | 540/540 | 140/140 | 58.0 |
| LingBot-VLA | 180 | 540/540 | 140/140 | 35.4 |
| VLAct All | 228 | 540/540 | 140/140 | 37.9 |
| DM05 | 243 | 540/540 | 140/140 | 50.1 |
| Hy-VLA | 226 | 540/540 | 140/140 | 37.3 |

## 文件入口

| 文件 | 内容 |
|---|---|
| [results.html](results.html) | 可独立打开的两 panel 合并表头报表，无外部网页资源依赖 |
| [results.md](results.md) | GitHub 可直接阅读的总览、逐任务分模式结果和完成进度 |
| [results.csv](results.csv) | 162 行 policy × task × mode 成功数、分母和成功率 |
| [results.json](results.json) | 完整报表快照：任务/模式计数、未舍入分数、纳入 seeds 和完成 blocks |
| [episodes.csv](episodes.csv) | 3240 行逐回合结果：seed、mode、成败、步数、指令、复用来源及原始结果文件 SHA-256 |
| [manifests/](manifests/) | 本次实际使用的七个冻结 seed manifest |
| [plan.json](plan.json) | 原始评测计划，包含任务配置、模型切换与 12 → 20 blocks 扩展信息 |
| [checkpoints.json](checkpoints.json) | 六个实际模型的仓库、revision 及身份记录来源 |
| [source-hashes.json](source-hashes.json) | 原始评测归档中的源码 SHA-256 清单 |
| [provenance.json](provenance.json) | 运行目录、时间、归档来源哈希和 CSV 字段约定 |
| [validation/](validation/) | 原始最终校验、扩展校验、恢复后已有结果保护校验 |
| [SHA256SUMS](SHA256SUMS) | 本目录归档文件的校验清单 |

## 任务与评分口径

| Panel | Task | 配置版本 | 每 policy 回合数 |
|---|---|---|---:|
| Xa | Verb / `bottle_verb` | `demo_clean` | 40 |
| Xa | Noun / `pick_diverse_object` | `demo_clean` | 40 |
| Xa | Attribute / `attribute_select` | `demo_clean` | 160 |
| Xa | Arm / `arm_select` | `demo_clean_arm_select_v2` | 40 |
| Xb | Sequence / `stack_sequence` | `demo_clean` | 120 |
| Xb | Spatial / `place_relative` | `demo_clean` | 100 |
| Xb | Grasp / `grasp_cube_approach` | `demo_clean_grasp_approach_v2`，wide-r1 | 40 |

每种 mode 均为 20 回合。Grasp wide-r1 使用 x=[0, 0.08] m、y=[-0.085, -0.035] m 的平移范围。
VLAct 使用 **StarVLA/VLAct_Qwen3OFT_Robotwin_all_Finetune**，revision
`999b37d4d7c1bd0f5588f78d72a185f6f052bf83`，100K checkpoint；540 回合均属于 All 模型。

`Task Avg.` 为任务内各 mode 成功率的等权平均。Attribute 的四个子轴各平均两个 target values，
再对四个子轴等权平均；等价于八个 modes 等权。

`Overall = (Verb Avg. + Noun Avg. + Attribute Avg. + Arm Avg. + Sequence Avg. + Spatial Avg. + Grasp Avg.) / 7`

原始 HTML 把 `Overall` 放在 Xb 表格末尾，该列汇总 **Xa + Xb 全部七项任务**。
它不是 Xb 单独的平均分，也不是总成功数除以 540。Xa 有四项任务、Xb 有三项任务，两个 panel 不各占一半权重。
例如 X-VLA：`(62.5 + 37.5 + 62.5 + 62.5 + 0 + 6 + 12.5) / 7 = 34.8%`。

`episodes.csv` 的 `block_index` 是 manifest 内从 0 开始的 block 序号（0–19），
`success` 为 1/0；`origin=reused` 表示保留的 12-block 回合，`origin=new` 表示扩展新增回合。
所有行均为已完成的 success 或 policy failure；运行异常的原始尝试保存在完整运行目录的 batches 中。

## 校验与原始输出

[formal.json](validation/formal.json) 确认全部 3240 回合的产物哈希、动作记录、跨 policy 初始 RGB/指令、
新增视频帧数通过校验；[extension.json](validation/extension.json) 确认旧结果保留、VLAct All 身份及零 Clean 模型结果复用。

本机完整运行目录：

```text
/Data/robotwin-if/evaluations/if-seven-tasks-v2-wide-20blocks-001
```

仓库内对应入口为 `outputs/policy-eval/if-seven-tasks-v2-wide-20blocks-001`。
`episodes.csv` 的 `record_path` 相对上述运行目录，逐回合文件位于 `<policy>/<task>/<task>_ep<seed>_*`。
同一前缀下可查找视频、初始观测、动作轨迹、诊断信息和完整 provenance。远端 grasp 结果已回传并纳入本目录对应的最终统计。

校验本结果包（从 repo 根目录执行）：

```bash
cd result/if-ext-v2-wide-20blocks
sha256sum -c SHA256SUMS
```

报表由 [`tools/summarize_formal_policy_results.py`](../../tools/summarize_formal_policy_results.py) 生成。
本目录报表和表格数据可随 repo 独立查看；原始视频与轨迹保留在上述运行目录。
