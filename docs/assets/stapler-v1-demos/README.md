# 当前 Stapler v1 README 视频

六组视频均从 `robotwin-if-press-lift-stapler-v1-20blocks-001` 的归档回合导出，
逐条匹配当前[正式结果](../../../result/robotwin-if-press-lift-stapler-v1-20blocks/episodes.csv)的 record SHA-256、成功标签及 provenance 中的视频 SHA-256。
共展示 14 个成功回合，包含新跑的 Stapler 和当前结果复用的五任务；Attribute 与 Arm 使用当前历史错误判据下的正式回合。

| Task | Policy | Seeds（从左到右、从上到下） | 内容 | 相对存档倍速 |
|---|---|---|---|---:|
| [press_lift_stapler](press_lift_stapler.mp4) | VLAct All | 110000, 110001 | 同一场景 Press / Lift | 1× |
| [pick_diverse_object](pick_diverse_object.mp4) | DM05 / Hy-VLA | 100014, 100053 | seen: mug / unseen: wooden mallet | 1× |
| [attribute_select](attribute_select.mp4) | Hy-VLA | 100008, 100010, 100013, 100015 | red / cat / long bar / small | 1× |
| [arm_select](arm_select.mp4) | LingBot-VA | 500000, 500001 | 指定 left / right arm | 1× |
| [stack_sequence](stack_sequence.mp4) | VLAct All | 100014, 100017 | 自下而上 R→G→B / G→B→R | 3× |
| [place_relative](place_relative.mp4) | VLAct All | 100055, 100059 | left / on top | 1.5× |

Stapler、Arm、Sequence、Spatial 的两个示例各自来自同一 block。
Noun 的 seen/unseen 是两个独立场景；Attribute 展示同一个 block 的四个属性场景，各取一个成功目标值。
示例用于解释任务，不是随机抽样的成绩展示；所有成功和失败的完整分母见正式结果。
有标签分歧的 Hy-VLA Noun seed 100052 未用于展示，相关记录仍在[旧素材说明](../task-demos/README.md)中。

## 来源和处理

[sources.json](sources.json)记录每个示例的 policy、seed、原始指令、mode、动作数、checker 版本、new/reused 来源，
以及源 record、视频和导出文件的 SHA-256。Checkpoint 身份见当前结果包的 [checkpoints.json](../../../result/robotwin-if-press-lift-stapler-v1-20blocks/checkpoints.json)。

仅使用 CPU FFmpeg 处理既有视频：从 960×240 三相机存档裁出左侧 320×240 的 head camera，加上标签后拼接。
所有轨迹从第一帧播放到最后一帧；短片结束后保持末帧，等待同组最长片段，末尾再停留 1.5 秒。
MP4 为 H.264 / yuv420p、20 fps、无音轨、faststart；GIF 为 480 px 宽、8 fps 循环预览。
播放时间由源视频的动作帧决定，不代表模型推理耗时。

这些文件随仓库保存，查看无需原机器或正在运行的视频服务。导出过程没有重跑模型、仿真或修改评测标签。
旧版 README 的素材继续保存在 [task-demos](../task-demos/README.md)，由[archive 文档](../../archive/README.md)引用。
