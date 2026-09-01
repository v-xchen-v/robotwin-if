---
status: principle
area: robotics / benchmark-design
created: 2026-08-31
tags: [instruction-following, task-design, ood, if-ext]
parent: "[[09-IF-Ext-单轴扩展任务集设计]]"
---

# IF 任务设计原则：被测行为必须在模型"能力库"内

> 一句话：**instruction-following(IF)诊断，让模型在指令下二选一(或多选一)的那些行为，必须都是模型执行得出来的。选了一个 unseen / OOD 的取值，IF 就塌成 OOD 泛化——失败不再可归因于"没读指令"。**

这条是做 IF-Ext 任务时踩出来的前提层面教训，适用于所有单轴 IF 任务的**选型阶段**（不是实现阶段）。

## 为什么：IF 的定义前提

instruction-following 测的是：**给一组模型做得到的行为，看它按指令挑对哪个**。前提是被测行为都在模型的 **repertoire（能力库）**内。

一旦某个被测取值的动作是 **OOD**（模型训练里从没出现），它的失败就有两种不可区分的解释：

- (a) 没读指令、默认去做惯用动作 —— 这才是 IF 要抓的失败；
- (b) 读了指令、但那个动作根本执行不出来 —— 这是 **OOD 泛化**问题，不是 IF。

二值成功率下，一个 0 分把 (a) 和 (b) 混在一起 → **单轴坍塌，诊断失效**。任务名义上测 IF，实际测的是"能不能做出一个没见过的动作"。

## Worked example：`laptop_verb` 的 close（IF-Verb-Select）

- 设计在**每一个可检查的轴上都完美**：单轴隔离（种子解耦、像素级同帧）、oracle 双向 ~90%+、视觉可分、成对门控、去腕部翻转。
- 但 `close` 是全 58 个 native RoboTwin 任务里**唯一没演示过的闭合动作**（open×2、close×0；没有任何铰链物体被驱动到闭合端）。选它当被测动词，就把行为**挤出了模型 repertoire**。
- **结论：可以在错的靶子上执行得无可挑剔。** 真正的错在**上游前提**（选型），不在实现的任何细节。这是最贵的失败模式，因为它一路"看起来都对"。

## 陷阱：强先验与 in-distribution 是同一枚硬币

verb-select 这类任务，价值来自"指令去命令一个**非默认**动词、对抗物体的惯用动作先验"。但对**不对称物体**（native 只对 laptop 做过"开"）：

> 你为了对抗强先验而选的"非默认动词"，**恰恰就是那个从没演示、因而 OOD 的取值**。

所以"**最大化先验冲突**"和"**留在分布内**"互相拉扯——单个不对称物体上鱼与熊掌不可兼得。先验越强（越有诊断价值），往往越 OOD（越破坏 IF 前提）。

## 关键：这是不是问题，取决于评测协议

| 评测协议 | OOD 取值 | IF 诊断是否成立 |
|---|---|---|
| `ifext-ft`（在本任务生成的数据上微调，含该动作） | in-distribution | **成立**，且强先验保留（最佳） |
| `zeroshot` / `native-ft`（零样本或只在 raw RoboTwin 微调） | OOD | **不成立**（0 分歧义），除非改判据 |

**有效性随协议翻转这件事，任务文档必须明写、不能藏。**

## 怎么办（三选一，按场景）

1. **seen-vs-seen**：两个被测取值都用模型执行得出来的动作（如同物体 pick vs press，都是 native 原语）。轴纯粹是"挑对哪个"，是干净的 IF。代价：先验弱一些。
2. **在 in-repertoire 协议下评**：若为强先验保留 OOD 取值，就在 `ifext-ft` 下评测（该动作变 in-distribution），OOD 顾虑基本消失。
3. **改方向性/分级判据 + 诚实改标签**：主判据从二值成功率改成"是否朝指令取值移动 + 移动了多少"，报各取值 + gap；并把这个轴**明确标注为复合轴（IF + action-OOD）**，不当纯 IF 卖。

## 落地检查（选型阶段就做）

- [ ] 列出每个被测取值对应的动作，逐一对照目标模型的训练分布：**每个都在 repertoire 内吗？**
- [ ] 若有 OOD 取值：severity 是"新技巧"还是"见过子技能的新方向/组合"？oracle 证明可执行吗？在目标评测协议下 in-distribution 吗？
- [ ] 若 OOD + 二值判据 → 会不会出现"0 分不可归因"？→ 上方三个办法之一。
- [ ] **把 action-OOD 检查前移到任务选型**，别等 oracle 建完——用 `/task-design-review <task>` 的第 5、8 维度。

---
相关：本仓库 `.claude/commands/task-design-review.md`（review 命令）· `docs/features/09-IF-Ext-单轴扩展任务集设计.md`（IF-Verb-Select 设计）· 私有笔记 `notes/2026-08-31-laptop-verb/design-review.md`（laptop_verb 逐维度评审）。
