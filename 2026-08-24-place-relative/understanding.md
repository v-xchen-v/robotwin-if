# Place-Relative — understanding

> feature: RoboTwin-IF 第 5 个任务集 Place-Relative（空间关系理解）
> 代码产出见 `docs/features/05-Place-Relative.md`（设计定稿）+ `tasks/envs/place_relative.py` 等。
> 本文件是"问题理解"的重建，跟着对话+代码 diff 倒推，不是最初那句话。

## 当前理解

### 这个 feature 实际解决的是什么
在 RoboTwin 2.0 上复刻论文 §6.2.1 的 **Place-Relative** 任务集：桌上有 2 个具名物体（A=被移动的 mover、B=参照的 receiver）+ 1–3 个干扰物，指令要求"拿起 A，放到 B 的 **beside**（旁边）或 **on top of**（上面）"，用来诊断 VLA policy 是否真的**读懂空间关系词**、而不是退化成看图做默认动作（VLA→VA）。

实际代码做的事（倒推）：
- **被打分的唯一轴 = 空间关系（beside vs on-top 二元）**。同一套物体池在两种关系下完全一样，场景本身不泄露是哪种关系——policy 只能靠指令里的关系词判断。
- **颜色只是 grounding 辅助**：指令写 `the {color} {noun}`，但不构造"同名异色"混淆项（那是 Pick-Diverse 的考点），颜色不作为考核维度。
- **关系→模板路由靠占位符签名**：beside 的参照物用 `{B}`、on-top 用 `{C}`，RoboTwin 的 `filter_instructions` 只选占位符集合匹配的模板 → 天然把 beside/on-top 两族句子分开，无需在指令里写死关系词、保留原生措辞多样性。
- **判定绑定到具名 A/B actor** → 抓错/放到干扰物 → A 没到位 → False，target-specific 与 relation-specific 同时成立。
- **oracle 可靠可跑通**：脚本专家能真实抓起 mover、放到 B 旁/上，采集 12/13≈92%。

### 边界（没做 / 明确排除）
- **beside 是非方向性**（任一侧都算），不区分左右——用户中途明确改成非方向（更贴论文字面"旁边"），放弃了我最初提的 left/right 方向性方案。空间轴因此是二元 beside vs on-top。
- **不测颜色 grounding**（颜色是辅助）、**不测手臂跟随**（`{a}` vestigial，oracle 就近选臂，policy 可忽略）。
- **base 池只有 2 个盒**（coffee-box/tea-box）→ reference 近乎二元，grounding 诊断维度弱（可接受，非考点）。
- **只做 Layer A+B**（结构正确 + 判定正反例）；**未做 Layer C/D**（真实 policy 跑分、区分度、与论文数值对齐）。
- 只用 oracle 专家验证，**没跑真实 VLA**。

### 验收标准（怎么算做对）
- **Layer A**（`tests/place_relative/test_instructions.py`，11/11）：seen∩unseen=∅；beside/on-top 两族在 seen 与 unseen 都在场；`filter_instructions` **路由零串味**（beside 参数→仅 beside 帧、on-top→仅 on-top）；`the {color} {noun}` 字面注入成句干净。
- **Layer B**（`tests/place_relative/test_check_success.py`，9/9）：R1 默认→False；R2 beside、R3 on-top 正例→True；**R4 错关系→False**（要 beside 却叠上/要 on-top 却放旁）；**R5 错参照→False**（放到干扰物旁/上）；R6 oracle 两关系真实 grasp+place→True。
- **端到端**：collect 跑通，desc-gen 按关系渲染正确句子（beside→"next to/beside"、on-top→"stack on/atop"）。
- **oracle 率合理**：修复后 aggregate 92.3%、on-top 100%、beside 85.7%。

## 理解变更记录

1. **最初以为 beside = 方向性 left/right**（更强的 IF 区分：policy 必须分左右），并打算用 native `place_a2b_left/right` 直接复用。
   → **后来用户明确改成非方向性 beside**（贴论文字面"旁边"）。因为 left/right 是我自己加的收紧，用户要的是论文原义。空间轴随之退化为二元 beside vs on-top，beside 指令源也从 place_a2b 换成 `move_can_pot`（非方向性 next to/beside/near）。

2. **一度担心"两族模板混在一个池里，beside episode 会抽到 on-top 句子"**。
   → **读 `generate_episode_instructions.py` 发现 `filter_instructions` 按占位符签名精确匹配**，于是用"参照物键 beside={B}/on-top={C}"路由，问题消失且保留措辞多样性。这是从"以为要写死 `{rel}` 字面词"到"发现能靠签名路由"的关键转变。

3. **本以为 on-top 可以借 `stack_blocks_two` 的指令池**。
   → **打开一看它是双臂、两块都搬到中心的堆叠**，不是干净的单臂"A 放到 B 上"，占位符还带 `{a}{b}` 双臂。于是只借它的 on-top 词汇（on top of/atop/onto），句式沿用 move_can_pot 单臂结构自写。

4. **最初想把 on-top 的 mover 限定成小方块/盒**（怕物理不稳）。
   → **用户否决"限方块"，要求去 raw task 找合适物体**。查到 `place_object_stand` 已证一批多样物体（mouse/stapler/bell/rubikscube/toycar/remotecontrol）能可靠抓+放到面上，统一 `pre_grasp_dis=0.1`。于是 mover 用多样物体，不限方块。

5. **实现时才补上"场景不能泄露关系"这条 IF 约束**：如果 on-top 才出现某类物体，policy 能看物体猜关系。→ 定成 **A 池、B 池两种关系完全相同**，每个场景都含一个承接面 B。

6. **首轮 collect 冒烟发现 oracle 率只有 40%（on-top 29%，stapler/remotecontrol 0/2）**，一度以为是"细长物体放盒顶物理不稳"。
   → **写诊断逐 seed 打印后发现真因是放置规划失败（`plan=False, moved=0`），根本不是物理**。两个元凶：(a) B 摆太偏→举高放置超出可达；(b) mover 与 B 异侧→跨身体放置必失败。修：B 居中 + mover 同侧 + 间距>0.22。on-top 诊断 0/2→12/12，aggregate 40%→92%。

7. **顺带发现 beside 有"空操作蒙对"漏洞**：两物体恰好 spawn 在 [0.08,0.20] 内，policy 什么都不做也判 True（正是要防的退化）。→ 强制 spawn 间距 >0.22（>beside 判据上界 0.20）堵死。这是第 6 点修复时附带发现的 IF 有效性 bug。

8. **collect 第二次跑数据 export 崩了**（`_traj_data/episode0.pkl` 缺失），一度怀疑是任务 bug。
   → **查明是我自己用 `run_in_background` 时又在命令里加了 `&`**，二次后台化让第一个 collect 孤儿化、与后续重跑抢同一 data 目录。清孤儿、单次不打断跑就正常（pick 用同一 flow 一直正常，export 无 bug）。

9. **用户指出 beside 落点没检查是否已有物体**——早期直接 `B.x±0.13` 拍死，那个点可能已被干扰物占据、A 会砸上去。
   → 改成 `_beside_target`：在 B 周围按「抓取臂侧→反侧→前→后」试候选，选第一个离所有干扰物 >0.10 且在可达桌面内的点。实测放置后距最近干扰物 0.19–0.43，无重叠。这是我最初没想到的边界（只想着"放旁边"，没想"旁边可能有人"）。

10. **用户先说"干扰物太多"（我改成 1–2），又说"改回 1–3，但为什么每次都是 3 个"**——我一度以为 `rng.integers(1,4)` 就是随机的。
    → 一查发现 `default_rng(seed).integers` 的**首抽**对小连续 seed 严重聚簇（低 seed 10/16 抽到 3），正是 pick_diverse 早就踩过的坑，我没联想到。改用混合种子流 `default_rng([seed,const]).integers(3)`（比 `seed%3` 更好：后者会让每个 mover 锁死只出 2 种数量）。50 ep 实测 1×11/2×21/3×18。教训：凡"按 seed 派生的离散量要在连续 seed 上均匀"，先想起首抽聚簇。

11. **50-episode 定版采集**确认修复在规模上成立：agg 92.6%、beside=on_top=92.6%（完美均衡）、export 干净。之前 12 ep 的 on-top 100% 是小样本，50 ep 回落到与 beside 齐平的 92.6% 才是真实水平。

## 待确认

- [x] **关系→模板路由端到端是否真对** — 已解决：6-episode collect 冒烟里 beside episode 全渲染 beside 句、on-top 全渲染 on-top 句，`{B}`/`{C}` 路由在真实 desc-gen 里生效。
- [x] **on-top oracle 率过低** — 已解决：诊断出是放置规划（非物理），改场景布局（B 居中/mover 同侧/间距>0.22），on-top 100%、agg 92%。
- [x] **beside 空操作蒙对漏洞** — 已解决：spawn 间距 >0.22 保证不动必 False（Layer B R1 + 结构性保证）。
- [x] **beside 落点砸到已有物体** — 已解决：`_beside_target` 选离干扰物 >0.10 的空位（变更记录 9）。
- [x] **干扰物数量"永远是 3"** — 已解决：改混合种子流，50 ep 实测 1×11/2×21/3×18（变更记录 10）。
- [ ] **`can` 抓放最弱（50 ep 75%，6/8）**：圆柱直立态偶尔翻/滚。非关键（agg 92.6%），但想更稳可给 can 换更稳的 resting pose / 降质心。
- [ ] **成功判定阈值是自定、论文未确认**：beside 距离带 `[0.08,0.20]`、`|Δz|<0.04`；on-top `planar<0.05`、`rise>0.02`。类推自 place_a2b / stack_blocks_two / place_object_stand。错了会误判正例/反例。Layer B 用极端 teleport 验过方向正确，但**具体数值是判断，不是从论文抠出来的**——若日后有真实数据或论文细节，这是首要回头点。
- [ ] **盒子 resting qpos `[0.707,0.707,0,0]` 是否真的平顶朝上**：靠 50 ep on-top 92.6% 跑通间接确认可放稳，但没显式验证盒顶朝上（万一是侧躺、只是恰好能放）。要真实渲一帧场景图确认。
- [ ] **base 池只有 2 个盒**：reference 近乎二元，grounding 诊断弱。非考点、不影响正确性，但想让 reference 有多样性需再验色扩充平顶物体。
- [ ] **只有 oracle、没有真实 policy 跑分（Layer C/D）**：任务是否真能区分"读指令 vs 瞎猜"的 policy、数值量级是否和论文 Table 8 一个级别——完全未验证。需要接一个真实 VLA 或瞎猜/作弊 baseline 才能确认基准有区分度。
- [ ] **`pr_bench.yml` 落在 submodule `task_config/`、未纳入本仓库**：换机器/重装 submodule 会丢。后续应连同 bridge 机制把 collect config 纳入 repo。
- [x] **分布均匀性** — 50 ep 已看：relation 完美均衡（25/25）、mover 各 8–10、干扰物数量 1–3 均衡。大规模（含稳定性筛选偏置）的细致分布仍可再扩样。
- [ ] **未提交**：本 feature 代码尚未 commit；`notes/` 与主仓库是两次独立 git 操作。
