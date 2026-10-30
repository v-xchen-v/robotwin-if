# 六个开源 checkpoint 的评测结果

六个任务，每任务 20 blocks；每模型 460 回合，共 **2760 回合、720 blocks**。
Attribute Size 大块 6 cm、小块 4 cm；任务定义和固定 seeds 见[仓库 README](../README.md)。

| Policy | Overall (%) |
|---|---:|
| X-VLA | 27.6 |
| LingBot-VA | 56.2 |
| LingBot-VLA | 31.6 |
| VLAct | 57.5 |
| DM05 | 50.1 |
| Hy-VLA | 38.9 |

Overall 是六个任务成功率的等权平均，各任务内部按 mode 等权。它不是全部回合的合并成功率。

- [分模式成绩](results.md) · [HTML 表格](results.html) · [JSON](results.json) · [CSV](results.csv)
- [2760 条逐回合记录](episodes.csv)：seed、instruction、判定和原始记录 SHA-256。
- [Checkpoint 身份](checkpoints.json)及 `checkpoint-evidence/`：公开权重的 revision 与哈希证据。
- [Press/Lift 配对统计](stapler-summary.json)：同场景两种指令的双成功率。
- [完整结果下载](../docs/download-results.md) · [Azure 上传校验记录](azure-backup.json)

Size 的 240 个回合在 6 cm 设置下重测，其余 2520 个回合复用未变化设置的结果。
[结果来源](../docs/release-provenance.md)说明资格证据、复用范围和已知复核分歧。
原始输出保持原始 metadata；通过下载包的 `episode-index.csv` 定位文件。

从仓库根目录执行 `python tools/verify_benchmark.py` 核对 seeds、分数和文件 SHA-256。
完整视频与推理输出不存入 Git；使用 `just video-review-azure` 按需浏览。
