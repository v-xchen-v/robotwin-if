# Pick-Diverse-Object — 理解文档

> feature-04，RoboTwin-IF 复刻的阶段3新建型任务。本文档基于 2026-08-21~24 的实现会话重建。

## 当前理解

### 实际解决的问题
在 RoboTwin 2.0 上实现 IF 基准的 **target-object grounding** 任务：桌上 4 个物体（从 12 品类池采样），指令用"颜色+名词"点名 1 个目标（如 "the blue cup"），单臂把它拿起，其余 3 个是干扰项。产出可跑 oracle 专家演示 + 评测任意 policy 的 harness——诊断 policy 是否真读指令选对物体，而非退化成"看图做默认动作"。

**最终代码实际做的事**（倒推自实现，非最初那句话）：
- **12 品类池**（bottle/cup/shoe/mug/can/toycar/phone/soap/hamburg/bread/coffee-box/mouse），颜色贴图眼验锁定（16 变体）。
- **12 品类等概率目标**：目标 noun = `品类[seed % 12]`、颜色 = `seed // 12` 轮转（确定性、连续 seed 严格均匀）；3 干扰从 12 品类均匀抽不同名词；只保证目标 (颜色,名词) 在 4 个里唯一。
- **受控指令**：`info["info"]={"{A}":"the {color} {noun}","{a}":arm}`，字面量走 native `replace_placeholders`（不走 objects_description 随机描述）→ 颜色+名词受控、每条必含；seen/unseen 隔离在句式模板层（借 adjust_bottle orientation-free 子集 12/4）。
- **bottle 50/50 站/躺**：站立 `[0.66,0.66,-0.25,-0.25]`（pick_dual_bottles）、躺 `[0.707,0,0,±0.707]`（adjust_bottle，x 符号朝向抓取臂）。
- **逐物体抓取参数** + **世界系抬起**（`move_by_displacement(z=0.12)`，非 `move_axis="arm"`）。
- **判定** `check_success` = 目标 z 抬离 >0.02 且仍被夹爪接触（`_if_grounding.py` 共用 helper，operate_tabletop 也重构为调它）。
- **reporter** 按目标 noun/color 拆成功率（从 seed 确定性反推目标，无需额外 logging）。

### 边界 / 明确没做
- **不训练模型**、不绑定具体 VLA——只做基准 harness。
- **不做 Layer C**（区分度：瞎猜 baseline vs 作弊 oracle）——本轮只做 Layer A（结构）+ Layer B（判定正反例）。
- **不改 submodule 源码**——靠 `bridge_tasks.sh` glob symlink 接入。
- **不需要** objects_description（指令用字面量）。
- IF review 提出的强化（强制颜色必要、分层报告、指标条件化、去掉 `{a}`）**已明确留作 TODO 未实现**（见 docs/features/04 后续决策）。
- 站立瓶子侧抓的**避障未做**（会撞开干扰物），留 TODO。

### 验收标准（怎么算做对）
- Layer A：`python tests/pick_diverse_object/test_instructions.py` → 9/9（seen∩unseen=∅、`{A}` 路由、字面量注入成句）。
- Layer B：`conda run -n RoboTwin python tests/pick_diverse_object/test_check_success.py` → **16/16**（12 类目标 oracle 都能抓 + 同色/同名/未握住三反例判 False）。
- 回归：operate_tabletop Layer B 仍 7/7。
- 集成：`bash bridge_tasks.sh` 后 `import envs.pick_diverse_object` 通；collect_data → reporter 全流程跑通，oracle ~82.8%（失败几乎全是场景不稳定、非 grounding）。
- 目标 tried 分布 12 类均匀、干扰分布均匀。

## 理解变更记录

1. **颜色标签来源**：一开始想直接用 native `objects_description` 里的颜色词。后来发现那是 **MLLM 文本、有噪**（单变体主色覆盖 33%-92%），用文本覆盖率阈值筛颜色是错的（卡 ≥70% 全过滤光）。改为**渲染真实 baseColor 贴图人眼核校**（且要看整块贴图/3D 快照，不是单一中位色球——多材质物体会被中位色洗白，如可乐罐红标+银顶中位成近白）。

2. **"能放住" ≠ "能抓起"**：以为 model_data 的 `stable=True` 就够了。后来发现 stable 只保证"平稳静置"，**graspability 要看该物体是不是某原生任务里真正的 `grasp_actor` 目标**（不是静止干扰物）。三个信号（stable / 有 visual glb / 有抓取标注）要分别核查、可以互相矛盾。

3. **"颜色最干净" ≠ "能抓"**：把 cup 目标定成最蓝的 `021_cup/base8`。实测 grasp 失败——base8 的 `contact_points_group` 是空的（无抓取标注）。改用有标注的 base0(blue)/base3(green)（native place_empty_cup 就用 base0）。

4. **option A → option B**（用户纠正）：最初实现"每 episode 强制含同名异色+同色异名干扰以保证颜色+名词联合必要"（option A）。用户指出这把物体分布压偏（bottle/cup/shoe 高频、off-color 名词几乎不出现）。改为 option B：均匀采 4/12、只保证目标 (色,名) 唯一，grounding 自然发生。

5. **seed 派生的离散选择会聚簇**（用户发现症状）：用户注意到 red-shoe 目标出现概率极高。查出根因是 `default_rng(seed).integers(N)` 对低连续 seed 聚簇（seed 0/2/3/4/8/10 全 → shoe/red），而 collect_data 从 seed 0 顺序采、小规模正好吃满这个簇。改成 `seed % N` 确定性轮转（同 operate_tabletop 的 `mode=seed%3`）。

6. **随机旋转漏了**（用户指出）：一开始为避开"不同 qpos 约定 yaw 轴不同"的坑，把 `rotate_rand=False`——物体只随机位置不随机朝向。用户指出应有随机旋转。改为逐物体照原生 `rotate_lim`（非对称全/部分 yaw、cup/can 对称不转、bottle 抖动）。后来又发现全 `[0,π,0]` 对 phone/mug 太大（落到难抓朝向），降到 `[0,π/3,0]`（put_object_cabinet 原生值）。

7. **目标限 3 类 ≠ 12 等概率**（用户要求）：option B 下目标仍只从 bottle/cup/shoe 出（可抓约束），用户指出这样 12 个不等概率。查证 9 个非目标物体**都有抓取标注**，遂扩到**全部 12 品类都可当目标**（逐个配抓取参数）。

8. **通用 resting qpos 对某些物体是错的**：扩到 12 目标时 phone 用通用 `[0.707,0.707,0,0]` 摆成难抓朝向、17 次全败。改用 place_phone_stand 的专属 `[0.5,-0.5,0.5,-0.5]` + pre_grasp 0.08 → 5/5。

9. **误判"高瓶站不住"→ 被用户纠正**：用户要 bottle 有站立姿态。我试 `[0.5,.5,.5,.5]`（倒）、`[0.707,.707,0,0]`（侧躺抓不到）后一度下结论"高瘦瓶子 drop-settle 站不稳、RoboTwin 也不站它"。用户反问"pick_dual_bottles 能让瓶子竖立，为什么，能不能参考？"——去查发现正解是 `[0.66,0.66,-0.25,-0.25]`（底座平贴桌面），默认 z 就稳。**教训：遇到"asset 做不到"先去 raw task 看它到底怎么做。**

10. **`move_axis="arm"` 抬起对侧抓无效**：站立瓶子 plan_success=True 但 check_success=False。查出 `move_by_displacement(z, move_axis="arm")` 沿夹爪接近轴移动——顶抓≈竖直能抬、侧抓（站立瓶）≈水平变平移。改世界系 `move_by_displacement(z=0.12)`。

11. **IF review 的改进 → 用户暂缓**：从 IF 角度 review 后提出"强制颜色必要 + 分层报告"等改进，实现了一版又按用户要求回退，留作 TODO。

## 待确认

- [x] 12 类目标 oracle 都能抓 —— Layer B 16/16 实测确认（每类多次机会至少成功一次）。
- [x] 站立瓶子稳定 + 可抓 —— bottle 专项探针 7/7、Layer B 通过。
- [x] 指令在真实 desc-gen 管线渲染正确 —— 采集产出的 instructions/episode*.json 实测含 "Find the blue cup on the table and raise it using the left arm." 等。
- [x] 目标分布均匀 —— reporter tried 分布 12 类均匀确认。
- [ ] **颜色 grounding 被稀释**：现均匀采样下颜色必要仅 ~10-15% episode，task 偏名词 grounding。要不要强化（TODO 已记）需用户定；错了的后果是"色盲 policy 也高分"、task 名不副实。
- [ ] **成功率口径混了稳定性**：~17% 是场景不稳定、非 grounding。干净 IF 口径应条件化于稳定场景——需 collect_data/eval 记录每 seed 稳定性，reporter 暂无此输入。
- [ ] **站立瓶子侧抓会撞开干扰物**（无避障）——对 grounding 判定无影响，但改变场景布局、视觉不干净。要不要加避障待定。
- [ ] **判定阈值 0.02 / 各物体抓取参数**均类推自原生任务，**论文未确认**（design.md 低可信度约定）。真值需原仓库开源或论文补细节才能对照。
- [ ] **oracle 单次抓取非 100%**（RoboTwin 常态）：每物体真实成功率需更大样本采集才稳定，本轮只 24-episode 小样本。
