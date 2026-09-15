# README 任务视频素材

这六组视频来自已完成的六任务、20-block policy 评测，用于介绍任务行为。
每个画面选用一个成功回合，完整成功率与失败回合仍保留在 [结果包](../../../result/if-ext-v2-six-tasks-20blocks/README.md)。
视频选例不参与结果计算，也没有重跑仿真或模型。

| Task | Policy | Seeds（按画面从左到右、从上到下） | 展示内容 | 存档播放倍速 |
|---|---|---|---|---:|
| [bottle_verb](bottle_verb.mp4) | Hy-VLA | 100026, 100027 | pick / shake | 1× |
| [pick_diverse_object](pick_diverse_object.mp4) | 左：DM05；右：Hy-VLA | 100014, 100053 | seen: mug / unseen: wooden mallet | 1× |
| [attribute_select](attribute_select.mp4) | Hy-VLA | 100080, 100082, 100085, 100087 | red / cat / long bar / small | 1× |
| [arm_select](arm_select.mp4) | DM05 | 200010, 200011 | v2 left / right | 1× |
| [stack_sequence](stack_sequence.mp4) | VLAct All | 100014, 100017 | red→green→blue / green→blue→red（自下而上） | 3× |
| [place_relative](place_relative.mp4) | VLAct All | 100055, 100059 | left / on top | 1.5× |

Bottle-Verb、Arm-Select、Stack-Sequence 和 Place-Relative 各自的两个例子来自同一个 block。
Noun-Grounding 的 seen/unseen 是两个独立场景；Attribute-Select 展示同一个 block 中四个不同属性的场景，未展示全部八个 modes。

Noun-Grounding 的 Seen 示例已从 Hy-VLA seed 100052（coffee box）替换为 DM05 seed 100014（mug）。
原例被用户指出画面失败；其存档虽标记为 `success`，末段动作记录显示左夹爪已打开，故撤出展示。
新例核对了目标名词、成功记录，以及末段左夹爪闭合和末端上升轨迹。
替换原因与原始文件哈希保存在 `sources.json` 的 `excluded_examples` 中；此处仅更新展示素材，原始评测结果保留待复核。

## 文件与播放

- `<task>.gif`：README 内联循环预览，8 fps、480 px 宽。
- `<task>.mp4`：H.264 / yuv420p、20 fps、无音轨、faststart，可点击或下载播放。
- [sources.json](sources.json)：逐画面的原始指令、mode、seed、policy、源视频/回合记录路径与 SHA-256，以及导出文件 SHA-256。

GIF 预览兼容 GitHub Markdown；点击预览或“观看 MP4”链接打开对应视频，无需支持 README 内的 HTML `video` 标签。
文件均保存在本目录，查看时不依赖原机器、模型环境或外部视频托管服务。

## 来源与处理

源归档：`if-seven-tasks-v2-wide-20blocks-001`。选例均属于当前六任务结果，
Arm-Select 使用 `demo_clean_arm_select_v2`，VLAct 使用 All checkpoint。
可用 `sources.json` 中的 `record` 与 `record_sha256` 对照结果包的 `episodes.csv`；
模型版本见 [checkpoints.json](../../../result/if-ext-v2-six-tasks-20blocks/checkpoints.json)。

处理仅使用 CPU 上的 FFmpeg：从 960×240 的三相机存档裁出左侧 320×240 的 head camera，
加上 mode 标签后按两列拼接；Attribute-Select 为两行，其余为一行。
每条轨迹从开始播放到最后一帧，短片结束后保持末帧以等待同组其他片段，整体末尾再停留 1.5 秒。
倍速相对源视频定义；源视频本身按动作帧保存，不代表模型推理的实际耗时。
没有插入生成画面或重新生成轨迹。
