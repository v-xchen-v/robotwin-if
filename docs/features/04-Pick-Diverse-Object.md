---
status: not-started
parent: "[[RoboTwin-IF 复刻]]"
tags: [robotwin, vla, benchmark]
---

# Pick-Diverse-Object

对应主文档「时间评估」阶段3（新建型任务，高风险：成功判定无原文细节，需自行设计）。

## 场景设计

12物体池随机采4个，指令用"颜色+名词"点名1个目标，其余3个是干扰项。测试目标物体 grounding。

### 论文原文依据（高可信度）

来自论文 §6.2.1 截图（见主文档 [[RoboTwin-IF 复刻#论文原文截图（§6.2.1 + Figure 6）]]）：

> "Four objects are randomly sampled from a pool of 12 everyday items. The instruction names one object by color and noun. The robot must identify and lift the correct target among three distractors, testing target-object grounding."

能确认：物体池12个日常物品、每次采样4个、指令用"颜色+名词"点名、3个干扰物、单臂、测的是 target-object grounding。**论文没给**：12个物体具体是什么、"lift"成功判据（离地高度/时长）、位置随机化分布、颜色词表——这些都要自行设计（低可信度，见下）。

## 复用基础

### 与 RoboTwin 原生 `Pick Diverse Bottles` 的区别（中可信度，来自 [RoboTwin 官方文档](https://robotwin-platform.github.io/doc/tasks/pick_diverse_bottles.html) 查证，2026-08-20）

官方任务里没有直接对应，`Pick Diverse Bottles` 名字像但本质不同任务，**不能直接魔改**，只能算"抓取原语/物体资产可复用"的参考：

| 维度 | RoboTwin `Pick Diverse Bottles` | 论文 `Pick-Diverse-Object` |
|---|---|---|
| 物体类别 | 只用 `001_bottle` 一种类型，换的是同类不同款 | 12个物体池，跨类别日常物品 |
| 抓取方式 | 双臂各抓一个瓶子 | 单臂抓指令指定的1个 |
| 语言指令 | 文档未提"颜色+名词"式指代消解要求 | 核心考点：颜色+名词精确点名 |
| 干扰物 | 文档未提干扰物概念 | 明确3个干扰物同时在场 |
| 测试目的 | 双臂协调+多样物体形态抓取 | 语言指令驱动的目标识别（instruction following） |
| 性能参考 | 平均约122步（Aloha-AgileX, save freq 15），success rate 因具身差异极大：Aloha-AgileX 51%、Piper 27%、UR5-Wsg 4%、ARX-X5 2%、Franka-Panda 0% | 论文 Table 8（未细查具体数值，待补） |

**结论**：这是"新建型"任务而非"复用型"（不同于阶段2的 Operate-Stapler/Operate-Tabletop 那种魔改自现有任务），可复用的只有 RoboTwin 的物体资产库和抓取相关 API（`grasp_actor()` 等），场景逻辑（干扰物摆放、颜色+名词指令生成、grounding 判定）要重新设计。

## 实现记录

（待开始）

## 成功判定设计（需自行摸索，记录尝试过程）

（待开始）

## Layer B 验证（正反例）

- [ ] 正例：oracle 按指令操作正确目标 → `check_success()` 稳定 True
- [ ] 反例：oracle 操作干扰物 → `check_success()` 稳定 False

## 踩坑

（待开始）
