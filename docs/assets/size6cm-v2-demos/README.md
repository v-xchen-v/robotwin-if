# Stapler v2：Attribute Size 6 cm 示例

[MP4](attribute_select.mp4) · [GIF](attribute_select.gif) · [来源与哈希](sources.json)

VLAct All 在同一初始场景下分别执行两个目标：

| 位置 | Seed | Instruction | 成功 |
|---|---:|---|---|
| 左：Big 6 cm | 100174 | `Reach for the big block and lift it.` | 是 |
| 右：Small 4 cm | 100175 | `Fetch the small block.` | 是 |

左侧是本次 120 个 Big 回合中唯一成功例；示例用于说明任务，不代表总体成功率。
新旧行为对照与先小后大的现象见[实验记录](../../attribute-size-6cm-ablation.md)。

从原始三相机视频裁出 head camera，以 20 fps 并排播放，短片结束后保持末帧，
两侧均播完后再保留 1.5 秒；GIF 为 480 px、8 fps。仅用 CPU FFmpeg 处理既有文件，未重跑模型。
其余五任务沿用 [v1 示例](../stapler-v1-demos/README.md)，原 v1 Attribute 四面板视频保留为历史素材。
