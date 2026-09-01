# IF-Sequence-Container — task design 讨论（实现前，待拍板）

> status: 讨论中 / 未开始实现。这不是实现记录，是"序列任务往哪个方向落地"的选型讨论 + 过拟合分析。
> 触发约束（用户给定）：**action in-domain**（不超出 raw task 动作范围）+ **object in-domain**（自然复用资产）。
> 母设计：[docs/features/09-IF-Ext-六轴扩展任务设计.md](../../docs/features/09-IF-Ext-六轴扩展任务设计.md) §5。
> 相关：[[if-tasks-need-in-repertoire-behaviors]]、[[ifext-eval-test-only]]、[[mic-drawer-oracle-infeasible]]、上一个 verb 任务 [../2026-08-31-laptop-verb/design-review.md](../2026-08-31-laptop-verb/design-review.md)。

## 1. 出发点

母文档 §5 原设计 = "3 个物体**依次单臂放入同一容器**，顺序不能错"，诊断失败模式 = **顺序盲假阳性**（3 个都放进去了但无视顺序）。用户要求收紧到 in-domain，于是先盘 native raw task。

## 2. Native raw task 盘点（序列 / 多物体有序操作）

| Native 任务 | 物体 | 动作 | check 查顺序? | 顺序编码在哪 |
|---|---|---|---|---|
| **`stack_blocks_three`** | 3×`create_box`(红绿蓝) | 单物体 pick→place 堆叠 ×3 | ✅ block2 在 block1 上、block3 在 block2 上 | **末态竖直 z 栈序** |
| **`blocks_ranking_rgb/size`** | 3×`create_box` | 单物体 pick→place 到位 ×3 | ✅ x: block1<block2<block3 | **末态水平 x 序** |
| `place_cans_plasticbox` | 2×`071_can` + `062_plasticbox` | **双臂同时**入盒 | ❌ 只查"都在盒里" | 无 |
| `put_bottles_dustbin` | 3×`114_bottle` + `011_dustbin` | 双臂 handover 入桶，按**位置**排序填 | ❌ 只查"都在桶里" | 无 |

## 3. 核心洞见：§5 原设计恰好踩在"没有顺序 check"的两个 native 上

母文档 §5 的容器-时序设计，对应的 native（`place_cans_plasticbox` / `put_bottles_dustbin`）**末态不编码顺序**，这正是 §5 自己列的三大风险的根：

1. 末态编码不了顺序 → 被迫写**轨迹-based 逐 step 采样**判定（novel，要查 eval 管线能否 rollout 中途采样）
2. 单臂 3× place-into-container **复合** → oracle ≈0.9³ 天花板低（native 容器任务还都是双臂）
3. 判定逻辑全新写

而 **`stack_blocks_three` / `blocks_ranking`** 把"顺序"编码进**末态几何**（竖直栈序 / 水平排序）→ 三个风险**同时消失**：动作是 native 原样单物体 pick+place、资产 `create_box`（颜色白嫖）、`check_success` native 已在读顺序。完全 in-domain。

IF 改造思路（复用 `laptop_verb` 的 `scene_seed`/`mode` 同帧对照）：指令指定 N 种排列之一、场景固定同 3 块、查 policy 是否按**指令顺序**而非**默认先验顺序**摆放。相邻种子对 = 同 3 块、不同指令顺序。

## 4. 语义分叉（三条路，都 in-domain）

- **堆叠 stack**：`stack_blocks_three`。"先红再绿最后蓝"→红底绿中蓝顶。时序=竖直序，**物理强制先放底块**，真·时序语义；末态静态可判。
- **排序 rank**：`blocks_ranking_rgb`。"左到右红绿蓝"→水平排列。空间排布，时序不强制（任意先后都能摆出）；更接近 §6 spatial 的三物体推广。
- **容器-时序**：§5 原设计，语义最纯的时序，但吃轨迹判定 + 3× 复合 oracle（第 3 节的三风险）。

## 5. 过拟合分析（本次讨论的核心，用户的两个疑问）

### 5a. Stack 的过拟合 —— 是**先验（可测）**，不是 **OOD（致命）**

用户疑问：finetune 见过的 stack 都是**红底→绿→蓝**这**一种**顺序，会不会过拟合？

关键区分：policy 被要求"蓝底"却摆成"红底"，两种解读——
- **(a) 读了但没服从**：用了默认先验 → **指令跟随失败**，正是 IF 要诊断的，**可归因**。
- **(b) 根本执行不出**：没见过这个动作 → IF 塌成 OOD，**不可归因**（close-laptop 的坑，[[if-tasks-need-in-repertoire-behaviors]]）。

**Stack 落 (a) 不落 (b)**，因为 `stack_blocks_three` 的**块初始位置本来就每局随机**：
- "先抓哪个颜色" = 纯 **grounding 决策**；"抓某块→放栈上" = **同一 native 运动程序**执行过无数遍。
- policy **motorically 完全能**摆蓝底栈，摆不摆取决于读没读指令 → **in-repertoire、可归因**。

**oracle 不受过拟合影响**：oracle 是脚本、无先验，6 种排列都能 ~90%（只是按指定顺序执行）。→ **过拟合不威胁任务成立性**（oracle 双向可行、Layer-B 反例照样过）。过拟合只塑造**被测 policy 的跟随率**——而那正是要测的量。

**处理方式 = §1 laptop 已定机制**：方向性/分级指标 + 报 **default-order vs non-default-order 的 gap**。按 [[ifext-eval-test-only]]，ifext **无 finetune 数据、只有 zeroshot/native-ft 两协议**，这个先验**必然存在、无法用全排列数据抹掉** → 方向性指标是**强制项**。所以过拟合是"用已定机制处理"，不是"推倒重设计"。

**唯一比纯 grounding 多的真实皱褶**：**色→高度纠缠**——native 里蓝块永远放最高、红块永远最低，policy 可能把"蓝=最高"学死。但"放低位/放高位"两动作都在库内，只是没跟"错误颜色"配过 → 仍是 (a) 类。极端情况先验太强 → 非默认跟随率贴地、**分辨率**差（像 close≤20%），这是 spike 要实测的量、不是归因问题。

### 5b. 容器版 —— 不同，而且是**镜像相反的 trade**

用户疑问：容器版会不会跟 stack 一样过拟合？**答案：反过来**。容器版过拟合**更小**，代价换到判定端。

| | 判定成本 | 过拟合/先验 | 根因 |
|---|---|---|---|
| **Stack** | **低**（末态竖直栈序） | **较高** | native 固定红底 + 色→高度纠缠 |
| **Container** | **高**（末态无序→需轨迹逐step） | **低** | 全进同一 bin（无每色专属落点）+ native 按**位置**排序填（`put_bottles_dustbin` sort by x/y，非按身份）→ 无色→顺序、无色→位置纠缠 |

容器版过拟合小的两个原因：① 三物体最终都落进**同一个 bin**，末态没有"每种颜色专属落点"可过拟合；② native 容器任务填入顺序**空间位置驱动**（随机），policy 没学到"某身份先放"的固定先验。

代价 = 第 3 节的两条（末态无序→轨迹逐 step 判定 + 单臂 3× 复合 oracle），恰好是 stack 白送避开的。

> **一句话**：**stack 用"末态好判"换"先验较强"；container 用"先验较弱"换"末态难判"。** 同一条 trade 曲线的两端，都 in-domain。互补，不是重复。

### 5c. 桥接想法：约束式容器（想两头都要时的后备）

若想要容器版**弱先验**又不吃**轨迹判定**：用**几何锁顺序的容器**（窄槽/托盘，物体进去不能重排），插入时序→末态槽位序，末态又能静态判。但会往 rank 靠、且 native 无现成多槽约束容器（plasticbox 只有 2 个 functional point），要自造 → 偏离 in-domain。**后备，不首选。**

## 6. 当前倾向（用户口径，未最终拍板）

- **先做 stack**（最省事、判定零风险），把过拟合当**已知的方向性测量**处理：spike 实测 oracle 6 排列都 ~90% + policy 非默认阶的分辨率；报 default/non-default gap。
- **再做 container 作为互补第二个**——价值恰在"弱先验"补上 stack 的短板，但要先付轨迹判定 + 3× 复合 oracle 两笔成本。
- 两者关系：不是二选一，是 trade 曲线两端的互补 pair。

## 7. 剩余待定 / 下一步

**stack 已拍板（§8）+ spike 已过（§9）+ 量产件齐（§10）**，剩下：

- [x] ~~stack spike：oracle 全 6 排列都稳 ~90%~~ → **过**，§9（worst 95%）
- [x] ~~stack 量产：指令池 + Layer A/B~~ → **过**，§10
- [ ] stack：真实 collect 一批 demo + `/check-video` 抽验（可选，机制已验）
- [ ] container：eval 能否 rollout 中途逐 step 采样物体位置（查 `_base_task`/eval 管线）——决定容器版可行性
- [ ] container：选哪个 native 容器基（plasticbox 开口 / basket），单臂 3× 复合率 spike

## 8. Stack 场景/指令/判定设计（已拍板 2026-09-01）

基本盘 = native `stack_blocks_three` 原样（3×`create_box` 红绿蓝、5cm 立方、桌面随机位、按 x 符号选臂、栈到固定中心点），加 IF 改造。四个拍板点：**3 块 / 全 6 排列 / L1+L2 纯 bool / 固定 RGB**。

### 8a. 场景
- **同帧对照**：`scene_seed = seed // 6` 决定场景（3 块随机位+颜色，`load_actors` 顶部按 `scene_seed` 重播种），`mode = seed % 6` 决定指令排列（3!=6）。同一 `scene_seed` 的 6 连续种子 = 像素级同帧、只有指令顺序不同。复用 laptop_verb 结构。
- **块位随机保留**：是轴隔离的关键——"先抓哪色"无法从几何读出 → 逼 policy 读指令。
- **颜色固定 RGB**（拍板 3）：红/绿/蓝是指代名，固定三原色 → grounding 最 trivial。**已接受的 confound + 假定**：指令要 policy 同时 ground RGB + 排序，失败时 grounding/order 有耦合；假定三原色 grounding trivial（纯 grounding 是 §2 的活），本任务只测 order。诚实标注。
- **块数 = 3**（拍板 1）：真序列语义（底/中/顶）；2 块退化成二值。代价 = 3-高栈复合 oracle，native 已调过。

### 8b. 指令（位置槽占位符）
- **`{A}/{B}/{C}` = 栈序第 1/2/3 层，不是颜色**（laptop `{V}` 技巧推广：模板恒定、映射随 mode 变）。
  - 模板固定：`"先放{A}，再放{B}，最后放{C}"`（先放=底，后放=顶，时序=竖直序天然一致）。
  - default 排列（红底，对齐 native 先验）：`{A}=红块 {B}=绿块 {C}=蓝块`；某非默认（蓝底）：`{A}=蓝块 {B}=绿块 {C}=红块`。
  - **6 排列共享同一占位符集 `{A,B,C}`** → 框架标准路由无法区分 → 干净，不 hack 框架。顺序只编码在"哪个颜色填哪个槽"。
- **模板多样性 10 seen / 2 unseen**，全部语义等价于"A 底→C 顶"、只用 `{A}/{B}/{C}`。
- **硬约束（模板作者须知）**：绝不混入翻转解读的措辞（如"从上往下"）——`先放`(时序)与`放最下面`(空间)在堆叠里都=底，一致才行；方向词一反 ground truth 就错。

### 8c. 判定（L1/L2 分层，纯 bool，拍板 2）
native check 硬编码红→绿→蓝；IF 版把 `(底,中,顶)` 三元组**参数化到 mode**：查 `中块在底块上(xy 近、z≈底+0.05)` + `顶块在中块上` + 夹爪开。静态末态-based。**分两层布尔、不做 partial credit**：
1. **L1 执行**：有没有堆成 3-高栈（**任意**顺序）→ 纯执行、不含 order 信号。
2. **L2 跟随**：成栈前提下顺序对不对 → 干净"读没读指令"信号。

堆不起来 → 挂 L1（执行问题非 order）；堆成默认红底却被要求蓝底 → 过 L1 挂 L2（干净"无视指令"）。叠 §5a 方向性：分 **default / non-default 两桶**报成功率 + **gap**，非默认桶低是预期（先验），**gap 是诊断量**。

### 8d. 反例（Layer B，必过）
oracle 故意反序堆（指令红底→oracle 蓝底）→ check False；塌栈/没堆全 → False；正序 → True。镜像 laptop Layer B。

## 9. Spike 结论（2026-09-01，锁定 stack）

- **实现**：spike env `tasks/envs/stack_sequence.py`（复用 native `stack_blocks_three` 的 `pick_and_place_block` 逐块 pick+place；`MODE` override 固定命令顺序、`ORACLE_MODE` 让 oracle 堆**不同**顺序造反例；`check_success`=L2 正序+夹爪开，`eval_signals` 拆 L1/L2）。sweep `tests/stack_sequence/sweep_per_perm.py`（劫持 `collect_data.run` 抓 task/args，逐排列 N 局 + 1 反例相位）。
- **N=20 结果（gate 90%）**：

  | perm | 顺序(底→顶) | L1 成栈 | L2 正序 | 判定 |
  |---|---|---|---|---|
  | 0 | red>green>blue（默认/先验） | 20/20 | **100%** | PASS |
  | 1 | red>blue>green | 19/20 | **95%** | PASS |
  | 2 | green>red>blue | 19/20 | **95%** | PASS |
  | 3 | green>blue>red | 19/20 | **95%** | PASS |
  | 4 | blue>red>green | 20/20 | **100%** | PASS |
  | 5 | blue>green>red | 20/20 | **100%** | PASS |
  | CE | 命令 red 底 / oracle 堆 blue 底 | 20/20 | **0%** | PASS（拒）|

  worst 95% ≥ 90%，全 6 排列过；CE 20/20 全拒。

- **关键读数（比通过率更重要）**：
  - **每个相位 L2 == L1**——3 个失败**全是 `NO-STACK`（L1=0）**，纯执行失误（3-高栈没堆成），**没有一个是 WRONG-ORDER**。即 **"只要堆成了，顺序永远对"** → 顺序机制确定性正确，`ORACLE_MODE` 反例是唯一制造 L2≠L1 的途径。
  - spike 最担心的 **"不同顺序→不同臂切换→某排列掉链子"没有发生**：~5% 损耗是 native 3-高栈 place 复合、对称分布在非默认序上，与顺序逻辑无关。
  - **CE 干净**：oracle 堆有效但反序的栈 → L1=1、L2=0、check=0，Layer-B 对"顺序盲假阳性"的防御成立（正是 §5 要抓的失败模式）。
- **结论**：**stack 设计锁定**，oracle 可行性闸门通过。下一步进量产（指令池 + Layer A 接入），判定按 §8c 的 L1/L2 双层布尔 + default/non-default gap（zeroshot/native-ft 下先验预期压低非默认序的 policy 跟随率——但**那是被测量、非任务缺陷**，§5a）。

## 10. 量产 + Layer A/B（2026-09-01，全过）

同一个 `tasks/envs/stack_sequence.py` 兼作生产 env（`MODE=None` 时走 `scene=seed//6`/`order=seed%6` 配对）。产出对齐 bottle_verb 那次 commit 的 footprint（env + json + sweep + check_success test），并多加一个路由测试：

- **指令池** `tasks/task_instruction/stack_sequence.json`：28 seen + 10 unseen，**位置槽 `{A}`=底/`{B}`=中/`{C}`=顶**（借 native `stack_blocks_three.json` 的"A 底 C 顶"位置语义，但颜色→槽随 mode 变、并**剔掉所有没说全顺序的模板**如"stack them"）。schema 明确禁止翻转/省略措辞，全部模板不含臂槽（顺序单轴、路由统一）。
- **Layer A** `tests/stack_sequence/test_instruction_routing.py`（复用框架 `filter_instructions`/`replace_placeholders`）：**6/6**——38 模板全含 `{A}{B}{C}`、零臂槽、全部路由（arm-free 走 `filter_instructions` 的"省略全部臂"分支）、颜色→槽渲染出**命令顺序**（perm0 红底、perm5 反序蓝底）。
- **Layer B** `tests/stack_sequence/test_check_success.py`（`set_pose` 直接摆位、测 `_l2_ordered`/`_l1_any_stack` 纯谓词）：**11/11**——含关键反例 perm0/perm5 的**反序有效栈 → L2 fail、L1 true**；场景解耦（seeds 0..5 同一场景、覆盖全 6 序）；xy 超 eps/只堆两个/散开 均正确判负；full `check_success`（含夹爪开）正例一致。
- **判定分层**：`check_success`=L2 正序 + 夹爪开（collect gate）；`eval_signals()` 拆 `l1_stacked`/`l2_ordered`/`is_default`，policy eval 报 default/non-default gap（§5a/§8c）。
- **未接入**：`all_tasks_plus_if.yml` 合并清单在本仓**尚不存在**（laptop/bottle_verb 也没接，真实 eval 走 task_config + eval 脚本）——非本任务遗漏，留待整体 eval 清单统一时接。
