# Attribute-Select target-only-v2：动作回放核对

这是成功判据修复的诊断证据，**不是新的六任务成绩包**。完整 Attribute/Overall 尚未重新评测。
三个案例均使用原始保存的动作，初始三路 RGB 逐像素一致，机器人初始状态误差为 0，
回放动作数及旧判据的成功停止点与归档一致。模型和双目标 oracle gate 没有重新运行。

| Policy / seed | 指令目标 | 首次错误抬升 action | 干扰物最高抬升 | 动作数 | 旧判据 | 新判据 |
|---|---|---:|---:|---:|---|---|
| LingBot-VA / 100003 | dog block | 79 | 9.10 cm | 256 | success | failure |
| X-VLA / 100001 | blue block | 74 | 8.69 cm | 232 | success | failure |
| LingBot-VA / 100002 | cat block（正确抓取对照） | — | 0.00 cm | 84 | success | success |

前两个案例最终只抬着目标，干扰物已回到初始高度；新的
`distractor_lifted_ever` 仍保留此前错误，因此不会把后续目标抓取记成成功。
阈值仍为相对静止高度 **严格超过 5 cm**。

- [LingBot-VA 100003](lingbot_va-100003.result.json) · [物体抬升事件](lingbot_va-100003.events.json)
- [X-VLA 100001](xvla-100001.result.json) · [物体抬升事件](xvla-100001.events.json)
- [LingBot-VA 100002 对照](lingbot_va-100002.result.json) · [物体抬升事件](lingbot_va-100002.events.json)
- [规则、实现与验证说明](../../docs/attribute-select-target-only.md)

JSON 包含原始回合、动作、初始观测、任务源码和 checker 的 SHA-256，以及每个案例的新旧判据结果。
`first_distractor_lift_action` 是从 1 开始的 policy action 计数，错误记录在该 action 的 physics 子步内产生。
逐 action 的完整信号保存在 `outputs/policy-eval/attribute-target-only-v2-review-001/`。
本目录的 `SHA256SUMS` 可用于核对分享文件；原始 [cube-v3 结果包](../robotwin-if-cube-v3-20blocks/README.md)未改写。
