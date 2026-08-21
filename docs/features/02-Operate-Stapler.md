---
status: not-started
parent: "[[RoboTwin-IF 复刻]]"
tags: [robotwin, vla, benchmark]
---

# Operate-Stapler

对应主文档「时间评估」阶段2（复用型任务）。

## 场景设计

订书机 + 彩色垫 + 1-2 干扰物。指令二选一："按订书机" 或 "移到垫子上"，垫子在两种场景里角色不同（干扰项 / 目标）。测试维度：**verb discrimination with shared scene elements**——考的是场景元素完全一样时能不能分清 press/move 两个动词对应的不同动作。

## 复用基础

魔改自 RoboTwin 原生 `press_stapler.py` + `move_stapler_pad.py`。

### 原生任务信息可信度核查（2026-08-20，[官方文档](https://robotwin-platform.github.io/doc/tasks/press_stapler.html)查证）

物体资产现成（高可信度）：两个原生任务都用 `048_stapler`，在已复用的120物体库里，不需要新建。**但判定逻辑细节文档没给**（中/低可信度）：

| 任务 | 文档给的信息 | 文档没给的 |
|---|---|---|
| `press_stapler` | "用一只手臂按订书机"，success rate 因具身差异大（Piper 59% ~ Franka-Panda 100%） | 按下判据的具体力度/位移阈值 |
| `move_stapler_pad` | "用合适的手臂把订书机移到彩色垫上"，92% success rate | "落在垫子范围内"的具体判据、垫子/订书机位置随机化范围 |

**TODO（实现前必做）**：判定阈值文档没公开，必须去读 submodule 里 `envs/press_stapler.py` / `envs/move_stapler_pad.py` 源码的 `check_success()` 实现，才能知道"按下""移到垫子上"具体怎么用坐标/接触判断——不能只参照文档页面。

## 实现记录

（待开始）

## Design 时候要想清楚的点

1. **同一场景要支持"角色翻转"**：pad 在 press episode 是干扰物、在 move episode 是目标，场景生成/判定逻辑不能写死"pad=目标"或"pad=干扰物"，要参数化，判定函数需读指令动词决定检查哪个物体的状态。
2. **误操作要能被判 False**：核心测试点是"操作了不该操作的物体"，`check_success()` 必须显式检查"是不是指令指定的那个动作+目标"，不能只检查"发生了某个物理事件"——对应下面 Layer B 反例验证要专门覆盖。
3. **干扰物数量是变量（1-2个）**：场景生成要处理干扰物数量随机，不是固定写死。
4. **垫子颜色随机化要跟指令模板对齐**：垫子颜色需要跟 description-gen 管线（阶段5）生成的颜色描述词对上，避免"场景是蓝色垫子，指令模板随机词是别的颜色"这种不一致——这个要在阶段5"指令模板接入"前想清楚。

## Layer B 验证（正反例）

- [ ] 正例：oracle 按指令操作正确目标 → `check_success()` 稳定 True
- [ ] 反例：oracle 操作干扰物 → `check_success()` 稳定 False

## 踩坑

（待开始）
