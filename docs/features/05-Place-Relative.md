---
status: in-progress
parent: "[[RoboTwin-IF 复刻]]"
tags: [robotwin, vla, benchmark]
---

# Place-Relative

对应主文档「时间评估」阶段3（新建型任务，高风险：成功判定无原文细节，需自行设计）。

## 论文原文依据（高可信度）

来自论文 §6.2.1：

> "Place-Relative: Two named objects and 1–3 distractors are on the table. The instruction specifies picking up object A and placing it in a spatial relation ("beside" or "on top of") with respect to object B, testing spatial-relation understanding."

能确认：2 个具名物体（A=被移动、B=参照）+ 1–3 干扰物、指令指定「拿起 A 放到 B 的 beside / on top of」、测**空间关系理解**、单臂。**论文没给**：物体清单、"beside/on-top" 的成功判据（距离/高度阈值）、位置随机化、干扰物规则——均自行设计（低可信度，见下）。

## 两处「把论文措辞收紧」的设计决策（标注为我们的选择，非原文）

1. **"beside" = 非方向性**（任一侧都算），与论文字面一致（旁边=next to）。曾考虑收紧成 left/right 方向性（更强的 IF 区分），但用户定为非方向性。→ 被考核的空间轴退化为**二元 beside vs on-top**：policy 仍必须读懂关系词（相邻 vs 堆叠），只是不再区分左右。
2. **颜色 = grounding 辅助，非考核项**（用户明确）。指令里 A、B 都写成 `the {color} {noun}`，但**唯一被打分的是空间关系**。因此干扰物用**不同名词**、不构造「同名异色」混淆项（那是 Pick-Diverse 的考点）。

## 关键机制：按关系路由模板（无字面关系词）

RoboTwin 的 `filter_instructions` 只选用**占位符集合与 episode info 键完全匹配**的模板（arm 可选）。利用这点，让**参照物的占位符键随关系不同**来自动路由：

- beside episode → `info={"{A}":mover,"{B}":ref,"{a}":arm}` → 只匹配 beside 模板（用 `{A}`,`{B}`）
- on-top episode → `info={"{A}":mover,"{C}":ref,"{a}":arm}` → 只匹配 on-top 模板（用 `{A}`,`{C}`）

`{B}`≠`{C}` → 两族**不可能串味**，场景↔句子恒对齐，且保留各族原生措辞多样性。Layer A 已验证零串味。

## 复用基础（原生任务）

| 用途 | 原生任务 | 复用内容 |
|---|---|---|
| beside 指令池 | `move_can_pot`（非方向性 next to/beside/near/by，50 seen/10 unseen） | 句式原样搬，mover/ref 占位符互换（原生 {A}=pot 参照、{B}=can mover，与我们相反） |
| on-top 指令池 | `stack_blocks_two` 的 on-top 词汇（on top of/atop/onto/on/above） | 词汇；句式沿用 move_can_pot 单臂结构，ref 键改 `{C}` |
| on-top oracle | `place_object_stand` | 逐字复用：grasp `pre_grasp_dis=0.1` → lift → `place_actor(target=..., constrain="free", pre_dis=0.07)`；并提供多样 mover 池（mouse/stapler/toycar/remotecontrol…，非方块） |
| beside oracle | `place_a2b_left/right` | 放置偏移 `B.xy ± 0.13`、3 元素 target_pose |

> ⚠️ `move_can_pot` 原生 seen/unseen **本身有重叠**（如 "Lift beside" 两边都有）+ seen 内部有重复。IF 要求 seen∩unseen=∅，故生成时去重：unseen 为准，seen 减去 unseen。生成脚本 `/tmp` 一次性，产物已落盘。
> ⚠️ `stack_blocks_two` 是**双臂、两块都搬到中心**的堆叠，不是干净的单臂「A 放到 B 上」，故只借它的 on-top 词汇，句式另写。

## 物体池设计（自建，贴图验色）

**可信度：低（自建）。** 论文未给物体清单。方法遵循「按贴图验色」：渲每个候选的真实 `base{K}.glb` baseColor 人眼核校（`tools/render_place_pool_candidates.py`，留证 `notes/2026-08-24-place-relative/evidence/pool/`）。

**核心 IF 约束——场景不泄露关系**：若 on-top 才出现某类物体、beside 不出现，policy 能靠「看物体猜关系」绕过读指令（正是要防的退化）。故 **mover 池、base 池在两种关系下完全相同**，每个场景都含一个承接面 base，去 beside 还是 on-top **只由指令词决定**。

### Movers（A，被抓被移，clean 色，pre_grasp_dis=0.1）
| noun | 资产 | 颜色 |
|---|---|---|
| mouse | 047_mouse/base0 | gray |
| toycar | 057_toycar/base3 | green |
| stapler | 048_stapler/base4 | red |
| remotecontrol | 079_remotecontrol/base0 | black |
| can | 071_can/base3 | red |
| soap | 107_soap/base2 | blue |

### Bases（B，平顶盒承接面，高度足够区分 beside/on-top）
| noun | 资产 | 颜色 |
|---|---|---|
| coffee-box | 113_coffee-box/base0 | brown |
| tea-box | 112_tea-box/base1 | red |

**剔除**（记录避免重踩）：bell（半球会滚，不宜堆叠）、rubikscube（唯一纯色变体是全黑，语义怪）、plate（太扁，on-top 与 beside 的 z 差仅 1–2cm，判据不稳）、displaystand/scale（是支架/仪器，非日常物体）。跨名词撞色（stapler/red + can/red）无所谓——grounding 靠名词，颜色只是辅助。

### 采样（seed 派生，可复现）
- `relation = seed % 2`（beside/on_top 均衡）
- `mover = MOVERS[(seed//2) % 6]`、`reference = BASES[(seed//12) % 2]`（seed%N 轮转，连续 seed 均匀）
- **1–3 干扰**：数量用**混合种子流** `default_rng([seed, const]).integers(3)`，**不能**用 `default_rng(seed).integers`——后者**首抽**对小连续 seed 严重聚簇（低 seed 里 10/16 抽到 3，看起来"每次都 3 个"，正是 pick_diverse 踩过的首抽聚簇坑）。混合种子流可复现、1/2/3 均匀、且与 mover/relation 解耦。干扰身份仍用主 rng 的 `permutation` 从全池（movers+bases）去掉 A/B 名词后抽不同名词。

### beside 放置点避开已有物体
beside 的落点不能直接 `B.x±0.13` 拍死——那个点可能已经有干扰物，A 会砸上去。`_beside_target` 在 B 周围按「抓取臂侧 → 反侧 → 前 → 后」试 ~0.13 半径的候选点，选**第一个离所有干扰物 >0.10 且在桌面可达范围内**的；全被占才退回臂侧。实测放置后 mover 距最近干扰物 0.19–0.43，无重叠。

### 场景布局（两种关系完全一致，防泄露 + 保证 oracle 可达 + 杜绝空操作）
布局在 beside/on_top **完全相同**（只有指令词区分关系）。三条约束都来自实测踩坑（见下）：
1. **reference B 居中**（`xlim=[-0.13,0.13], ylim=[-0.15,-0.03]`）：把「拿着物体放到 B 顶上（有高度）」的目标点放进手臂舒适可达区——照 `place_object_stand` 把承接物摆中间。B 摆太偏 → 举高放置规划失败。
2. **mover A 摆到 B 的同侧**（`|x|>0.18`，x 符号=B 的符号）：抓取臂按 A 的侧别就近选，若 A 与 B 异侧 → 跨身体放置、规划几乎必失败（实测 on-top 成功率腰斩的元凶）。同侧后 on-top 诊断 **12/12**。
3. **A 与 B 间距 > 0.22**（> beside 判据上界 0.20）：保证**空操作（什么都不做）永远无法满足 beside 的 [0.08,0.20] 判据**——A 必须真被移动才算成功，堵住「不读指令、原地不动也能蒙对 beside」的退化漏洞。

## 成功判定设计（自行摸索）

`tasks/envs/_if_relative.py`，按 `self.relation` 分派，两者按平面距离**互斥**：
- **beside**：`planar_dist(A,B) ∈ [0.08,0.20]` ∧ `|A.z−B.z|<0.04`（没叠起来）∧ 双爪张开
- **on-top**：`planar_dist(A,B) < 0.05` ∧ `(A.z−B.z) > 0.02`（抬升到 B 上）∧ 双爪张开

**target-specific 天然成立**：判定绑定到具名的 A、B actor → 抓错/放到干扰物 → A 没到位 → False。
**on-top 放置目标 z**：盒子 functional_point 为空，故由 B 的 `extents×scale` 经落定后旋转投影到世界 z 算半高（`_base_half_height_z`），target=`[B.x,B.y,B.z+半高+0.03]`。

**可信度标注**：beside 距离带类推自 `place_a2b`；on-top 对齐/抬升类推自 `stack_blocks_two`+`place_object_stand`，**论文未确认**。

## 产出物

- `tasks/envs/place_relative.py`：`class place_relative(Base_Task)`
- `tasks/envs/_if_relative.py`：`placed_beside` / `placed_on_top`
- `tasks/task_instruction/place_relative.json`：beside 48 seen/10 unseen（move_can_pot 换键去重）+ on-top 24 seen/6 unseen
- `tests/place_relative/test_instructions.py`（Layer A）+ `test_check_success.py`（Layer B）
- `tools/report_place_relative.py`：按关系 + mover/reference 名词拆成功率
- `tools/render_place_pool_candidates.py`：验色工具
- `bash scripts/bridge_tasks.sh` 自动 symlink；**不需要** objects_description（字面注入）

## 验证结果

- **Layer A** `tests/place_relative/test_instructions.py` → **11/11 PASS**：seen∩unseen=∅；beside/on-top 两族在 seen 与 unseen 都在场；**路由零串味**（beside 参数→仅 48/48 beside 帧、on-top→仅 24/24）；字面 color+noun 成句干净。
- **Layer B** `tests/place_relative/test_check_success.py` → **9/9 PASS**（aloha-agilex）：
  - R1 默认→False；R2 beside 正例、R3 on-top 正例→True
  - **R4 错关系（关键）**：要 beside 却叠到 B 上→False；要 on-top 却放 B 旁→False
  - **R5 错参照（关键）**：放到干扰物旁/上→False（coffee-box half_z≈0.048）
  - R6 oracle 正例（两种关系真实 grasp+place）→True

## collect_data 冒烟（2026-08-24，`pr_bench.yml` episode_num=6）

全流程跑通（seed.txt + scene_info + hdf5/video + instructions 全产出）。**端到端路由验证通过**——desc-gen 按关系渲染正确句子：

| episode | relation | 渲染指令（seen[0]） |
|---|---|---|
| seed0 beside | "Place the gray mouse **next to** the brown coffee-box" |
| seed3 on_top | "**Stack** the green toycar **on** the brown coffee-box with the right arm" |
| seed8 beside | "...place it **close to** the brown coffee-box" |
| seed11 on_top | "Place the blue soap **atop** the brown coffee-box" |
| seed12 beside | "...move it to the red tea-box's **side**" |
| seed14 beside | "...**beside** the red tea-box" |

beside↔on-top 句子与关系**一一对齐**、color+noun 字面注入干净、seen/unseen 都渲染正确。

**oracle 成功率**（`tools/report_place_relative.py --collection`）：

| 阶段 | aggregate | beside | on_top |
|---|---|---|---|
| 修复前（宽随机布局，12 ep） | 40% | 50%（含空操作蒙对） | 29% |
| 修复后（12 ep） | 92.3%（12/13） | 85.7%（6/7） | 100%（6/6） |
| **修复后（50 ep，定版）** | **92.6%（50/54）** | **92.6%（25/27）** | **92.6%（25/27）** |

**50-episode 定版采集（2026-08-25）**：export 全流程跑通（50 hdf5 + 50 video + 50 instructions + scene_info 全产出），仅 4/54 失败。
- **按关系完美均衡**：beside 25、on_top 25，两者成功率同为 92.6%——on-top 修复后已和 beside 齐平（起点是 29%）。
- **按 mover**：mouse/remotecontrol/soap 100%，toycar/stapler 90%，**can 75%（6/8，最弱——圆柱直立偶尔翻/滚）**。
- **按 reference**：coffee-box 96.7%、tea-box 87.5%。
- **干扰物数量分布**（验证聚簇修复）：1 个×11、2 个×21、3 个×18——真正随机 1–3，不再卡在 3。

### 踩坑：on-top oracle 率低的真因（不是物理/抓取，是放置规划）
诊断（`/tmp/diag_ontop.py`：逐 seed 打印 plan_success / moved / planar / rise）发现失败几乎全是 **`plan=False, moved=0`**（抓+举成功但**放置规划失败**），非物体滑落。两个元凶，均靠布局修复：
1. **B 摆太偏** → 举高放置超出手臂可达 → 照 place_object_stand 把 B 摆中间。
2. **mover 与 B 异侧** → 抓取臂**跨身体**放置必失败 → mover 摆到 B 同侧后 on-top 诊断 0/2→**12/12**。
另外发现 **beside 空操作蒙对**漏洞（两物体恰好 spawn 在 [0.08,0.20] 内 → 不动也 True）→ 强制 spawn 间距 >0.22 堵死。

### 踩坑：collect 双跑竞态
用 `run_in_background` 时**不要**再在命令里加 `&`——会二次后台化，shell 立刻返回、python 被孤儿化，与后续 rm/重跑抢同一 data 目录 → `_traj_data` pkl 缺失、export 崩在 `load_tran_data`。清掉孤儿进程、单次不打断跑即正常（export 本身无 bug，pick 用同一 flow 正常）。

### 踩坑：干扰物数量"看起来永远是 3"（首抽聚簇）
`default_rng(seed).integers(1,4)` 作为**首抽**对小连续 seed 严重聚簇——低 seed 里 10/16 抽到 3，采出来的数据看着"每次都 3 个"（其实是重度偏 3，非严格全 3）。正是 pick_diverse 踩过的首抽聚簇坑。**改用混合种子流** `default_rng([seed, const]).integers(3)`：可复现、1/2/3 均匀、且与 mover/relation 解耦（`seed%3` 虽均匀但会让每个 mover 锁死只出现 2 种数量）。50 ep 实测分布 1×11 / 2×21 / 3×18。

### 踩坑：beside 落点砸到已有物体
早期 beside 直接 `B.x±0.13` 拍死，那个点可能已有干扰物 → A 砸上去。`_beside_target` 在 B 周围按「抓取臂侧→反侧→前→后」试候选，选第一个离所有干扰物 >0.10 且在可达桌面内的点。实测放置后 mover 距最近干扰物 0.19–0.43，无重叠。

## 后续 / 待定

- **`can` 抓放最弱（50 ep 75%）**：圆柱直立态偶尔翻/滚。可给 can 换更稳的直立 resting pose 或降低质心；非关键（agg 仍 92.6%）。
- **base 池偏小**（仅 2 个盒）：reference 近乎二元，grounding 诊断维度弱；grounding 非本任务考点，可后续加平顶物体扩充。
- **`pr_bench.yml` provenance**：现落在 submodule `task_config/`（沿 pick 的 `pdo_bench.yml` 先例），未纳入本仓库；后续可连同 bridge 一并规整。
- **`{a}`（臂）vestigial**：oracle 就近选臂，policy 忽略也不影响（同 Pick-Diverse）；本任务不测手臂跟随。
- ~~on-top oracle 率低~~ **已修复**（50 ep on-top 92.6%，与 beside 齐平）。
