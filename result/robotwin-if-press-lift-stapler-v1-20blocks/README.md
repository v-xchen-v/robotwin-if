# Press/Lift Stapler v1：六模型 × 六任务 × 20 blocks

**2760/2760 回合、720/720 blocks 已完成并校验。**

其余五个任务的 2520 回合全部复用 Arm-only-v2，包含成功和失败，逐回合记录哈希与已发布结果一致。
仅 Press/Lift Stapler 的 240 回合是本次新跑；使用 manifest 中固定的 40 个 seeds、随机 distractors、固定指令与 250-action 预算。
六个模型沿用各自原 checkpoint 和推理参数。小规模 pilot 未混入本结果。

| 模型 | Press | Lift | 两种指令都成功 | Overall |
|---|---:|---:|---:|---:|
| X-VLA | 9/20 | 15/20 | 7/20 | 27.6% |
| LingBot-VA | 18/20 | 0/20 | 0/20 | 56.2% |
| LingBot-VLA | 18/20 | 1/20 | 1/20 | 31.6% |
| VLAct | 20/20 | 16/20 | 16/20 | 57.4% |
| DM05 | 20/20 | 12/20 | 12/20 | 50.1% |
| Hy-VLA | 17/20 | 18/20 | 17/20 | 38.9% |

Overall 是六个任务成功率的等权平均，每任务内部各 mode 等权；不是 460 回合的合并成功率。
新旧 Verb 任务不同，因此 Overall 的变化不代表同一任务上的模型能力提升。
X-VLA 使用公开 clean checkpoint，其余模型沿用旧报告对应的 clean + randomized checkpoints。

旧报告中 Hy-VLA noun seed 100052 的视频复核疑问仍保留；本次按要求复用原自动标签，未重新判定该回合。

- [六任务 HTML](results.html) · [Markdown](results.md) · [分模式 CSV](results.csv) · [逐回合 CSV](episodes.csv)
- [Verb 统计](stapler-summary.json) · [Verb 逐回合诊断](stapler-episodes.json)
- [来源](provenance.json) · [复用审计](reuse-audit.json) · [校验](validation.json) · [checkpoints](checkpoints.json)

原始视频、动作及观测：`/Data/robotwin-if/evaluations/robotwin-if-press-lift-stapler-v1-20blocks-001/<policy>/<task>/`。
原始数组、动作、逐回合哈希、新视频帧数及各模型初始观测已检查。
在本目录执行 `sha256sum -c SHA256SUMS` 可校验发布文件。
