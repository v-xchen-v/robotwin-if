# 九个开源 checkpoint 的评测结果

六个任务，每任务 20 blocks；每模型 460 回合，共 **4140 回合、1080 blocks**。
Attribute Size 大块 6 cm、小块 4 cm；任务定义和固定 seeds 见[仓库 README](../README.md)。

| Policy | Overall (%) |
|---|---:|
| X-VLA | 27.60 |
| LingBot-VA | 56.25 |
| LingBot-VLA | 31.63 |
| VLAct | 57.47 |
| DM05 | 50.14 |
| Hy-VLA | 38.92 |
| Fast-WAM | 51.74 |
| Motus | 53.06 |
| X-WAM | 42.33 |

Overall 是六个任务成功率的等权平均，各任务内部按 mode 等权。

- [分模式成绩](results.md) · [HTML 表格](results.html) · [JSON](results.json) · [CSV](results.csv)
- [4140 条逐回合记录](episodes.csv)：seed、instruction、判定和原始记录 SHA-256。
- [Checkpoint 身份](checkpoints.json)及 `checkpoint-evidence/`：公开权重的 revision、哈希和服务配置证据。
- [Press/Lift 配对统计](stapler-summary.json)：同场景两种指令的双成功率。
- [完整结果下载](../docs/download-results.md) · [Azure 上传校验记录](azure-backup.json)
- [新增 WAM 结果审计](wam-audit.json)：完整 seed 覆盖、逐回合哈希与 oracle 错误归档核查。

原六模型的 2760 条记录完整保留，其中历史 Size 240 回合重测来源见[发布溯源](../docs/release-provenance.md)。
新增三模型 1380 回合于 2026-11-06 完成，沿用同一 seed manifest、判据与动作预算。22 次模型调用前 oracle 资格错误在原 seed 恢复并保留归档，正常 policy failure 不重跑。
合并后的结果包包含九模型证据；原六模型 Azure 备份 `robotwin-if-20261030` 和日期 tag 保留。
原始输出保持原始 metadata；通过下载包的 `episode-index.csv` 相对路径定位文件。

从仓库根目录执行 `python tools/verify_benchmark.py` 核对 seeds、分数和文件 SHA-256。
完整视频与推理输出不存入 Git；使用 `just video-review-azure` 按需浏览。
