---
status: in-progress
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

（2026-08-21 实现，沿用 [[02-Operate-Stapler]] 的四件套 + 桥接方式）

**产出物**：
- `tasks/envs/operate_tabletop.py`：`class operate_tabletop(Base_Task)`
- `tasks/task_instruction/operate_tabletop.json`：click/press/pick 三组模板
- `tests/operate_tabletop/test_instructions.py`（Layer A）+ `test_check_success.py`（Layer B）
- `tools/report_operate_tabletop.py`：三向成功率报告
- `bash bridge_tasks.sh` 已把上面两份 symlink 进 submodule

**关键设计**：
1. **场景三模式恒定**：铃铛(050_bell, static) + 订书机(048_stapler, static) + 1-2 个可拿取物体(dynamic) 每个 episode 都在，静止时三种模式的画面一致（IF 要求"看图不能反推指令"）。
2. **mode = seed % 3**（click/press/pick），纯 seed 派生——和 Stapler 的 `seed % 2` 同理，保证 eval 两次 `setup_demo(同 seed)` 生成同一条指令+同一套判定，不受 RNG 抽取顺序影响。
3. **三向指令路由用三个不同占位符**：`{A}`=铃铛(仅 click 模板)、`{B}`=订书机(仅 press 模板)、`{C}`=被拿物体(仅 pick 模板)。原生 `filter_instructions` 按"非臂占位符集合精确匹配"路由，每个 episode 的 `info["info"]` 只填其中一个 → 三向路由零改动复用原生 filter。**这是对 Stapler「用 {B} 有无二分」机制的三向推广。**
4. **指令池 = 借用三个 raw task 的 native 池**（跟 Stapler 的 press 组照搬 `press_stapler.json` 同一套路，不手写）：
   - click ← `click_bell.json`（`{A}` 不变，取带 `{A}` 的子集、丢掉 `<...>` 字面量）→ **措辞是 touch/click/tap/press the bell's top center，坐实是"触碰铃铛顶部"而非"摇铃"**
   - press ← `press_stapler.json`（全取，`{A}`→`{B}`）
   - pick ← `adjust_bottle.json`（RoboTwin 里唯一的**单臂纯拿起**任务，`{A}`→`{C}`，丢掉 head-up/upright/orientation/"bottle" 这些瓶子专属措辞）
   - 由一次性脚本按上述规则从三个 native 池生成（规则见本条，可据此复现）。计数 click 28/5、press 48/10、pick 12/4（seen/unseen）。
5. **判定 target-specific（用户确认选项）**：click 判铃铛顶部接触(照搬 `click_bell`)、press 判订书机 cp2 接触(照搬 `press_stapler`)、pick 判"被点名那个物体 z 抬离桌面 >0.02 且仍被夹爪接触"(类推自 `adjust_bottle`/`put_object_cabinet` 的 grasp+lift)。做错动作会让本模式的判定条件不满足而自然 False，不额外做互斥交叉检查。
6. **pick 基线高度在 setup 期采集**（`self.target_origin_z`，`load_actors` 里 `delay(2)` 沉降后取）——eval 不跑 `play_once`，基线不能放那里。
7. **可拿物体池 `GRASPABLE_NAMES`**：从 `put_object_cabinet` 已验证可抓的桌面物里选，且 model_id 需同时满足 stable + 有 mesh + **有 objects_description/base{N}.json**（否则 description-gen 里 `replace_placeholders` 会 hard-exit）。pick 目标靠**品类(名词)区分**，不做颜色 grounding（用户确认）。

**可信度标注（对齐 design.md 约定）**：pick 分支的 lift 阈值 0.02 / 判定逻辑 = 类推自原生 `adjust_bottle`/`put_object_cabinet`，**论文未确认**；click/press 判定分别照搬 `click_bell`/`press_stapler`。指令措辞全部来自 native 池，非自撰。

**验证状态**：
- Layer A（指令路由）：`python tests/operate_tabletop/test_instructions.py` → 23/23 PASS（本机可跑，无需仿真）。
- Layer B（judgement 正反例）：`conda run -n RoboTwin python tests/operate_tabletop/test_check_success.py` → **7/7 PASS**（2026-08-21，aloha-agilex 具身）。含 K3 拿错物体（目标 075_bread、抬起干扰物 081_playingcards）稳定判 False。pick 的 0.02 lift 阈值实测正例稳定 True，无需调。

## Design 时候要想清楚的点

1. **三个可交互物体要各自有独立判定**：铃铛判"是否被点击"、订书机判"是否被按下"、可拾取物判"是否被正确的那个被拿起"，三套判据要能互斥组合，还要防止"顺手碰到另一个也触发了它的判定"这种假阳性——比 Stapler 的二选一更容易漏检。
2. **误操作要能被判 False**：跟 Operate-Stapler 一样，`check_success()` 要显式检查"是不是指令指定的那个动作+目标"，不能只看"某个物理事件发生了"。
3. **干扰物数量是变量（1-2个可拾取物体）**：场景生成要处理数量随机。
4. **"拿指定物体"分支要复用 Pick-Diverse-Object 的目标 grounding 逻辑**：这个子分支本质是"多物体里选一个"，跟 [[04-Pick-Diverse-Object]] 的核心判定逻辑同源，实现时可以考虑抽出共用的目标物体判定函数，避免两处各写一遍、逻辑漂移。

## Layer B 验证（正反例）

- [x] 正例：oracle 按指令操作正确目标 → `check_success()` 稳定 True（C2/P2/K2）
- [x] 反例：oracle 操作干扰物 → `check_success()` 稳定 False（K3 拿错物体；C1/P1/K1 默认态）

## 踩坑

（待开始）
