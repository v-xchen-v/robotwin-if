---
status: in-progress
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

## 12 物体池设计（自建，论文未给清单）

**可信度：低（自建）。** 论文 §6.2.1 只说"从 12 个日常物品池随机采 4 个"，**没有给出这 12 个具体是什么**（已沿"原生 `Pick Diverse Bottles` / 资产库"这条线穷尽搜索确认，无现成清单可借）。因此 12 物体池由我们自建，颜色词表、目标选取规则同为自建。以下逻辑与锁定表是本项目的设计决策，非论文事实——若日后原仓库开源或论文补充细节，此表是首要回头对照点。

### 选池逻辑

1. **"12 items" 按品类(名词)计数**：同一物体的不同颜色变体只算 **1 个品类**（例如 `cup` 有蓝/绿两色，仍只占 12 之一）。颜色是品类内属性，用于 grounding。
2. **只收"已确认可抓 + 颜色干净"的品类**：
   - *已确认可抓*：该物体在某个原生任务里**真的是 `grasp_actor` 的抓取目标**（不是静止干扰物），单臂可拿起。仅"stable（放得住）"不够。
   - *颜色干净*：**以贴图为准，人眼核校**。⚠️ native `objects_description` 里的颜色词是 MLLM 文本、有噪（单变体主色覆盖仅 33%–92%），**用文本覆盖率阈值筛颜色是错的方法**（实测卡 ≥70% 全过滤光）。真正的裁判是资产 `visual/base{N}.glb` 的 baseColor 贴图：用 `tools/render_pick_pool_thumbs.py` 把每个候选变体的**真实贴图** contact sheet 渲出来（不是单一中位色球，多材质物体会被中位色洗白）逐个眼看。留证：`notes/2026-08-21-pick-diverse-object/evidence/pool/`（`snapshots.png` + `contact_sheet.png` + `color_audit.json`）。
3. **目标变体额外要求"有抓取标注"**（实现期发现）：能当目标(被 oracle 抓)的变体必须有非空 `contact_points_group`（model_data 里的抓取点分组），否则 `grasp_actor` 算不出抓取位姿。**颜色最干净的变体未必有抓取标注**——如 `021_cup/base8`(最蓝)、`base12`(黑) 的 group 是空的，故 cup 目标改用有标注的 `base0`(blue)/`base3`(green)（native `place_empty_cup` 正是用 base0）。干扰变体不被抓，无此要求。
4. **保留多色名词 + 让颜色跨名词重叠**：这样两类"迷惑项"都造得出来（见下）。

### 锁定表（16 个变体 / 12 品类，已眼验 + 抓取标注核查）

> 变体已用真实贴图人眼核校（2026-08-21，见 evidence 路径）。留证含两套渲染：`snapshots.png`（SAPIEN 真实贴图 3D 快照，`tools/render_pick_pool_snapshots.py`，最直观）与 `contact_sheet.png`（贴图展开图，`tools/render_pick_pool_thumbs.py`）。
> **⚠️ 下表"角色"列已过时**：2026-08-24 改为 12 品类等概率目标后，**全部 12 品类都可当目标或干扰**（都有抓取标注 + 逐物体配好 oracle 抓取参数，Layer B 16/16 实测全可抓）。列内容仅作历史保留。

| 品类(名词) | 颜色 | 资产/变体 | 角色 |
|---|---|---|---|
| bottle | red | `001_bottle/base0` | 🎯 目标 |
| bottle | green | `001_bottle/base22` | 🎯 目标 |
| bottle | orange | `001_bottle/base5` | 🎯 目标 |
| cup | blue | `021_cup/base0` | 🎯 目标 |
| cup | green | `021_cup/base3` | 🎯 目标 |
| shoe | red | `041_shoe/base8` | 🎯 目标 |
| shoe | green | `041_shoe/base4` | 🎯 目标 |
| mug | black | `039_mug/base0` | 干扰（同色可用） |
| can | red | `071_can/base3` | 干扰（同色可用） |
| toycar | green | `057_toycar/base3` | 干扰（同色可用） |
| phone | black | `077_phone/base4` | 干扰（同色可用） |
| soap | blue | `107_soap/base2` | 干扰（同色可用） |
| hamburg | yellow | `006_hamburg/base4` | 干扰 |
| bread | golden | `075_bread/base4` | 干扰 |
| coffee-box | brown | `113_coffee-box/base0` | 干扰 |
| mouse | gray | `047_mouse/base0` | 干扰 |

**眼验/核查中剔除或替换的**（记录，避免以后又踩）：
- `woodenblock/green 086/base2` → **半橙半绿双色**，无干净单色，剔除。
- `french-fries/red 005/base1` → **红盒 + 金黄薯条混色**，"red" 不可靠，剔除。
- `bottle/yellow 114/base1` → 贴图**绿/灰/黄三拼**，黄不占主导，去掉此变体（bottle 保留 red/green/orange）。
- `cup blue/black` 最干净变体 `base8/base12` → **无抓取标注**，不能当目标 → 改用有标注的 `base0`(blue)/`base3`(green)（见选池逻辑第 3 条）。
- 补入 `coffee-box/brown`、`mouse/gray`（均为 [[03-Operate-Tabletop]] 已验证可抓的 `GRASPABLE_NAMES`，各引入新颜色 brown/gray）。

颜色分布（12 品类 / 16 变体）：green×4(bottle,cup,shoe,toycar)、red×3(bottle,can,shoe)、blue×2(cup,soap)、black×2(mug,phone)、orange/yellow/golden/brown/gray 各×1。
颜色跨名词重叠（撑"同色不同名词"迷惑项）：**green** bottle/cup/shoe/toycar、**red** bottle/can/shoe、**blue** cup/soap、**black** mug/phone。

**已知弱点（保留现状，记录备查）**：`cup`(021) 与 `mug`(039) 渲染形状相近（都是带把手的杯子）。现池里 cup 是蓝/绿、mug 是黑，二者不同色 → 不会构成"同色异名"迷惑对，弱点已被动缓解；但若日后给 cup 或 mug 加同色变体，需注意名词区分公平性。（2026-08-21 用户确认先不特意换 mug）

### 采样规则（2026-08-24，贴合论文"随机采 12" + 12 品类等概率目标）

论文原文是 **uniform sample 4-of-12**。演进过程（都记着，便于回看权衡）：
- **option A**（最初）：强制每 episode 含"同名异色"+"同色异名"干扰以保证颜色+名词联合必要。副作用：把物体分布压偏（target 必 ∈{bottle,cup,shoe}、confuser 又锁定同名/同色 → off-color 的 mug/phone/hamburg/bread/coffee-box 几乎不出现）。**已否决。**
- **option B**（改）：target 限 bottle/cup/shoe（可抓）、干扰从 12 均匀抽。修好了干扰分布，但 **target 仍只 3 类** → bottle/cup/shoe 整体出场 ~0.5、其余 9 类 ~0.25，**12 个仍不等概率**（用户 2026-08-24 指出）。
- **当前（12 等概率目标）**：让**全部 12 品类都能当目标**。

**当前采样**（`load_actors`，seed 派生）：
- **target noun = `品类[seed % 12]`**（确定性轮转，连续 seed 严格均匀，见踩坑"低 seed 聚簇"）；颜色按 `seed // 12` 在该名词内轮转。→ 每品类当目标概率 **1/12**。
- **前提**：12 品类全部可当目标——都有抓取标注 + 逐物体配好 oracle 抓取参数（见实现记录 §grasp）。Layer B 实测 12 类全可抓。
- **3 干扰** = 从 12 品类 uniform 抽 3 个不同名词（target 名词可复现 → 自然"同名异色"），各随机颜色、排除 target 精确变体；只保证 target (色,名) 在 4 个里唯一。
- **整体出场 ~均匀**：每品类 P(target)=1/12 + P(干扰)≈0.23 ≈ **0.31**，12 类基本一致。
- **grounding 自然发生**：抽到同名词干扰→逼读颜色、同色干扰→逼读名词；多数 episode 4 个不同名词（名词即可辨）。角色 same_noun/same_color/other **事后计算**（供 Layer B 反例测试扫种子）。

**权衡**：忠实"随机采 12"、12 类等概率，但**不保证每 episode 都联合必要**（有时名词就够辨）。

## 实现记录

（2026-08-21 实现，沿用 [[03-Operate-Tabletop]] 的四件套 + 桥接方式）

**产出物**：
- `tasks/envs/pick_diverse_object.py`：`class pick_diverse_object(Base_Task)`
- `tasks/envs/_if_grounding.py`：抽出的共用 `named_object_lifted_and_held()`，operate_tabletop 的 pick 分支也重构为调它（DRY，feature-03 建议）
- `tasks/task_instruction/pick_diverse_object.json`：借 `adjust_bottle` orientation-free 子集（12 seen / 4 unseen），占位符 `{A}`=目标、`{a}`=臂
- `tests/pick_diverse_object/test_instructions.py`（Layer A）+ `test_check_success.py`（Layer B）
- `tools/report_pick_diverse_object.py`：按目标 noun/color 拆成功率
- `bash bridge_tasks.sh` 自动 symlink（glob，无需改脚本）；**不需要** `objects_description`（指令用字面量）

**关键设计**：
1. **seed 派生确定性组合**：`load_actors` 开头 `rng = np.random.default_rng(self._seed)`，派生 3 干扰（先于全局 np 位姿采样）→ eval 两次 `setup_demo(同 seed)` 生成同一 episode，可复现。**目标 noun = `品类[seed % 12]`、颜色 = `seed // 12` 轮转**（确定性，非 rng 抽取，见踩坑；reporter 据此从 seed 反推目标，无需额外 logging）。
2. **12 品类等概率目标**：target noun 按 `seed % 12` 轮转全部 12 品类（连续 seed 严格均匀）；3 干扰从 12 品类 uniform 抽不同名词，只保证 target (色,名) 唯一。整体出场 ~均匀、贴合论文"随机采 12"。详见上「采样规则」。
3. **受控指令**：`info["info"]={"{A}":"the {color} {noun}","{a}":arm}`。value 无 `/` → native `replace_placeholders` 字面替换（不走 objects_description 随机描述）→ 颜色+名词受控、每条指令必含。seen/unseen 隔离在句式模板层（借 adjust_bottle 划分）。
4. **判定复用**：`check_success` = `named_object_lifted_and_held`（目标 z 抬离 >0.02 且仍被夹爪接触），与 operate_tabletop 共享。
5. **bottle 50/50 站/躺**（2026-08-24，参考 `pick_dual_bottles`）：seed 派生硬币决定——**站立**用 `qpos=[0.66,0.66,-0.25,-0.25]`（底座平贴桌面、默认 z 就稳，非 `[0.5×4]`——那个底座歪会倒）+ 抓取 `pre_grasp_dis=0.08`；**躺放**用 `[0.707,0,0,±0.707]`（adjust_bottle，x 符号朝向抓取臂）+ 抓取 0.1。目标 bottle 的站/躺记在 `self._target_bottle_upright` 供 play_once 选抓取参数。
6. **oracle 抓取逐物体调参**（12 品类都可当目标，都照各自原生抓取任务配参）：cup `contact_point_id=[0,2][arm==left]`（place_empty_cup）、shoe `gripper_pos=0`（place_shoe）、mug `0.05`（hanging_mug）、phone `0.08` + **专属 resting qpos `[0.5,-0.5,0.5,-0.5]`**（place_phone_stand，见踩坑）、bottle `0.08`站/`0.1`躺；其余（can/hamburg + put_object_cabinet 组 toycar/soap/coffee-box/bread/mouse）`0.1`。**抬起统一用世界系 `move_by_displacement(z=0.12)`**（非 `move_axis="arm"`，见踩坑）。Layer B 实测 12 类全可抓。
7. **随机旋转（yaw）**：非对称物体加随机 yaw、对称的不加。`[0.707,0.707,0,0]` 组用 `[0,π/3,0]`（±60°，照 put_object_cabinet——全 π 会让 phone/mug 这类薄/带把手物体落到难抓朝向）；phone 用专属 qpos + `[0,0.7,0]`（place_phone_stand）；cup/can 径向对称不转；bottle 站立 `[0,±1,0]`、躺放 `±0.4` 抖动。不同 qpos 约定 yaw 轴不同，必须逐物体照抄原生 `rotate_lim`。

## 成功判定设计（需自行摸索，记录尝试过程）

判据：**目标物体 z 抬离桌面 >0.02 且仍被夹爪接触**（`named_object_lifted_and_held`，`tasks/envs/_if_grounding.py`）。抓错干扰物 → 目标静止 → False；抬起但没夹住（如撞飞）→ False。

**可信度标注（对齐 design.md）**：lift 阈值 0.02 / 判定逻辑 = 类推自 [[03-Operate-Tabletop]] pick 分支（其又类推自 `adjust_bottle`/`put_object_cabinet`），**论文未确认**。指令措辞借 `adjust_bottle` native 池；12 池 + 颜色词表为自建。

## Layer B 验证（正反例）

`conda run -n RoboTwin python tests/pick_diverse_object/test_check_success.py` → **16/16 PASS**（2026-08-24，aloha-agilex）：
- [x] 正例：oracle 能抓+抬起**全部 12 品类**目标 → check_success True（D2，每品类给多次机会、至少成功一次；单次抓取非 100%，正常）
- [x] 反例 confuser_B（同色异名，如目标 cup/green、抬起 toycar/green）→ False（D3，逼读名词）
- [x] 反例 confuser_A（同名异色，如目标 shoe/red、抬起 shoe/green）→ False（D4，逼读颜色）
- [x] 反例：目标被抬但没夹住 → False（D5，验"held"半边）；默认态 → False（D1）

Layer A：`conda run -n RoboTwin python tests/pick_diverse_object/test_instructions.py` → **9/9 PASS**（seen∩unseen=∅、`{A}` 路由、字面量注入成句）。
回归：operate_tabletop Layer B 未受本任务改动影响，仍 **7/7 PASS**。

## 数据采集 / Oracle 成功率（2026-08-24）

`python script/collect_data.py pick_diverse_object <config>` 全流程跑通（seed.txt + scene_info.json + hdf5/video + instructions 全产出；指令在真实 desc-gen 管线渲染正确，如 "Find the blue cup on the table and raise it using the left arm."）。

12-episode 采集（config `pdo_bench.yml`，episode_num=12，**option B 采样**）：**oracle expert 成功率 = 12/13 = 92.3%**（`tools/report_pick_diverse_object.py --collection`）。
- **1 个失败是 UnStableError（001_bottle 翻倒），零抓取/grounding 失败** → 稳定场景 oracle 抓取可靠。
- **干扰物分布均匀**（option B 效果）：bread=5/hamburg=5/shoe=4/coffee-box=4/cup=4/can=3/bottle=3/phone=3/soap=2/mug=2/mouse=1 —— 对比 option A 旧数据（cup=8/shoe=7/can=6…，mug/phone/hamburg 几乎不出现），off-color 名词已恢复正常频率。
- 目标色含 red/green/blue/orange（orange 来自扩展的第 7 个目标变体）。
- 说明：这个"成功率"混了**场景稳定性**与**oracle 抓取**；对 pick-diverse 而言前者是主要损耗项（~8% 不稳定），非 grounding 问题。样本偏小时目标名词分布有噪（本次 shoe=7/cup=4/bottle=1，rng 驱动，样本大会趋近 target 变体 uniform）。

## 后续决策（待定）

- **站立瓶子的避障**（2026-08-24 记）：bottle 竖立时是**侧向抓取**，但现在的 oracle 脚本 `grasp_actor` + `move_by_displacement` **不做避障**——手臂伸向站立瓶子的接近/抬起过程会**撞开桌上其他物体**（把干扰物推走）。躺放瓶子和从上方抓的物体不明显，站立瓶子最突出。待决：是否给抓取运动加避障（碰撞感知规划 / 调整接近角度 / 抬起前先退让），还是接受"偶尔推开干扰物"（对 grounding 判定无影响，但视觉上不干净、且可能改变场景布局影响后续）。暂记为 TODO，未处理。

- **IF 视角的 grounding 强化**（2026-08-24 review，用户确认暂缓、留 TODO）：从 instruction-following 诊断看，核心（读指令才能选对物体、判定 target-specific、seen/unseen 模板隔离）**成立**；主要短板是**颜色 grounding 被均匀采样稀释**——现 option B（均匀采 4/12）下多数 episode 是 4 个不同名词，光靠名词就能定位，"颜色必要"只在 ~10-15% 的 episode 发生，task 名为"color+noun"实则偏名词。两个改进方向（**已实现过一版又回退，暂不做**）：
  1. **强制颜色必要**：目标是多色名词（bottle/cup/shoe）时强制放 1 个同名词异色干扰 → 颜色必要率提到天花板 ~25%（=目标∈多色名词的比例，因 9 个单色单例名词永远无法要求颜色）。代价：轻微增加 bottle/cup/shoe 当干扰的频率（目标分布不变）。要更高需加物体的颜色变体（asset 活）或放弃目标均匀。
  2. **分层报告**：reporter 按「颜色必要 / 名词必要 / 任一即可」拆成功率（用 scene_info 的 target + distractors 判定），让颜色 grounding 能力可测量、不改采样。**最轻量、无副作用，建议优先。**
- **指标应条件化于稳定场景**（2026-08-24 记）：现 success rate 混了 grounding 与 ~17% 场景不稳定（瓶子/mug 翻倒），完美 grounding 也超不过 ~83%。IF 干净口径应在稳定场景内算 grounding 率（需 collect_data/eval 记录每个 seed 的稳定性，reporter 暂无此输入）。
- **本 task 的 `{a}`（手臂）指令是 vestigial**：指令里的臂恒等于目标所在侧（oracle 就近选臂），policy 忽略也不影响——本 task 不测手臂跟随。可考虑去掉 `{a}` 模板让指令更纯聚焦"选对物体"（手臂跟随是 Operate-Mic-Drawer 的考点）。

## 踩坑

- **颜色最干净 ≠ 能抓**：`021_cup/base8`(最蓝) 的 `contact_points_group` 是空的 → `grasp_actor` 返回 None、`move` 报 "target_pose cannot be None"。目标变体必须另核查抓取标注（见选池逻辑第 3 条），cup 目标改用 base0/base3。
- **瓶子朝向要对臂**：固定 qpos 时左侧瓶子抓取规划失败（plan_success=False）；照 adjust_bottle 按 x 符号选 `[0.707,0,0,±0.707]` 才稳。
- **stable ≠ 有抓取标注 ≠ 有 visual glb**：三者要分别核查；`_valid` 类筛选只保证放得住/有描述，不保证可抓。
- **`default_rng(seed).integers(k)` 对低连续 seed 聚簇**：用 `np.random.default_rng(self._seed).integers(7)` 选 target，实测 seed 0/2/3/4/8/10 全落到同一变体（shoe/red）→ 从 seed 0 顺序采的小规模数据集 red-shoe 目标占比高达 46%（200 seed 上才均匀）。**修法：改 `变体[seed % 7]` 确定性轮转**（同 operate_tabletop 的 `mode = seed % 3`），任意连续 seed 区间严格均匀。教训：凡"按 seed 派生的离散选择要在连续 seed 上均匀"，用 `seed % N` 而非 rng 抽取。
- **kept 分布 ≠ tried 分布（选择偏置）**：collect_data 拒绝 UnStableError 的 seed，若某类目标所在场景更易翻（如含 bottle 的场景），kept 里该类会被压低。报成功率时要意识到这是稳定性筛选、非采样问题。`seed % N` 确定性目标能保证 **tried** 均匀（bottle 场景多翻只是 kept 里 bottle 少、需多采）。
- **通用 resting qpos 对某些物体是错的**：扩到 12 目标时，phone(`077_phone/base4`) 用通用 `[0.707,0.707,0,0]` 摆成难抓朝向 → oracle 17 次全失败。改用 place_phone_stand 的**专属** `ori_quat[4]=[0.5,-0.5,0.5,-0.5]` + `pre_grasp_dis=0.08` 后 5/5 成功。教训：每个可抓目标的 resting qpos 要照它自己的原生抓取任务，别套通用值。
- **全 yaw `[0,π,0]` 太大**：薄/带把手物体（phone/mug）在全 yaw 下偶尔落到难抓朝向。put_object_cabinet 对这些物体原生只用 `[0,π/3,0]`（±60°）——照抄后稳。
- **单次抓取非 100%（正常）**：12 类里多数第 1 次就抓起，少数（bread 等）第 2 次；随机位姿下 grasp_actor 偶尔返回 None。这是 RoboTwin 常态（原生 oracle 也 <100%），collect_data 会换 seed 重试。Layer B 的正例测试因此改成"每类多次机会至少成功一次"，真实每物体成功率看采集 reporter。
- **站立瓶子的 qpos 要精确**（2026-08-24，用户提示参考 `pick_dual_bottles`）：想让高瘦的 001_bottle 直立，试过 `[0.5,0.5,0.5,0.5]`（底座歪→倒）和 `[0.707,0.707,0,0]`（侧躺另一向→抓不到），一度误判"高瓶站不住"。**正解是 pick_dual_bottles 的 `[0.66,0.66,-0.25,-0.25]`**——底座平贴桌面，默认 z 就稳（无需改质量/z）。带 scale 渲染才看清朝向（不带 scale 物体巨大、看不出）。教训：别轻易下"asset 做不到"的结论，先去 raw task 找它到底怎么做的。
- **`move_axis="arm"` 抬起对侧抓无效**：`move_by_displacement(z, move_axis="arm")` 沿夹爪接近轴移动——顶抓(躺物)接近轴≈竖直→能抬；侧抓(站立瓶)接近轴≈水平→"抬"变平移，物体没升起（plan_success=True 但 dz≈0、check_success=False，极隐蔽）。**统一改世界系 `move_by_displacement(z=0.12)`**（默认 `move_axis="world"`），对任意抓取方向都竖直抬起。
