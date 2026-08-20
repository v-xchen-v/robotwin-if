---
status: not-started
parent: "[[RoboTwin-IF 复刻]]"
tags: [robotwin, vla, benchmark]
---

# Operate-Tabletop

对应主文档「时间评估」阶段2（复用型任务）。

## 场景设计

铃铛 + 订书机 + 1-2 可拿取物体同时出现。指令三选一：摇铃 / 按订书机 / 拿指定物体。测试维度：**three-way verb-and-target discrimination in a multi-affordance scene**——比 Operate-Stapler 更难，既要分清动词（摇/按/拿）也要在"拿"分支里选对具体目标物体，且三个物体都真实可交互（不是摆设式干扰物）。

## 复用基础

魔改自 RoboTwin 原生 `click_bell.py` + `press_stapler.py` + 拾取类任务组合。

### 原生任务信息可信度核查（2026-08-20，[官方文档](https://robotwin-platform.github.io/doc/tasks/click_bell.html)查证）

物体资产现成（高可信度）：`click_bell` 用 `050_bell`、`press_stapler` 用 `048_stapler`，都在已复用的120物体库里。**判定逻辑细节文档没给**（中/低可信度）：

| 任务 | 文档给的信息 | 文档没给的 |
|---|---|---|
| `click_bell` | "点击铃铛顶部中心"，success rate 91-100% | "顶部中心"判据的容差范围 |
| `press_stapler` | 同 [[02-Operate-Stapler]] 表格 | 同上 |

**TODO（实现前必做）**：需要读 submodule `envs/click_bell.py` / `envs/press_stapler.py` 源码的 `check_success()`，才能确认接触点判定的具体容差，不能只参照文档页面。

## 实现记录

（待开始）

## Design 时候要想清楚的点

1. **三个可交互物体要各自有独立判定**：铃铛判"是否被点击"、订书机判"是否被按下"、可拾取物判"是否被正确的那个被拿起"，三套判据要能互斥组合，还要防止"顺手碰到另一个也触发了它的判定"这种假阳性——比 Stapler 的二选一更容易漏检。
2. **误操作要能被判 False**：跟 Operate-Stapler 一样，`check_success()` 要显式检查"是不是指令指定的那个动作+目标"，不能只看"某个物理事件发生了"。
3. **干扰物数量是变量（1-2个可拾取物体）**：场景生成要处理数量随机。
4. **"拿指定物体"分支要复用 Pick-Diverse-Object 的目标 grounding 逻辑**：这个子分支本质是"多物体里选一个"，跟 [[04-Pick-Diverse-Object]] 的核心判定逻辑同源，实现时可以考虑抽出共用的目标物体判定函数，避免两处各写一遍、逻辑漂移。

## Layer B 验证（正反例）

- [ ] 正例：oracle 按指令操作正确目标 → `check_success()` 稳定 True
- [ ] 反例：oracle 操作干扰物 → `check_success()` 稳定 False

## 踩坑

（待开始）
