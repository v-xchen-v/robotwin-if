# IF-Grasp-Approach — task design review（基准有效性）

> 由 `/task-design-review grasp_cube` 产出（三评测协议全评）。这不是代码 review，是"这个任务到底测没测到它声称要测的东西"。实现见 `tasks/envs/grasp_cube.py` + `tests/grasp_cube/`（本 session spike：顶 100% / 侧 100%（锁 `SIDE_FACE=6`）/ 反例 0%，固定中央位姿）。相关：[[grasp-approach-spike]]、[[if-tasks-need-in-repertoire-behaviors]]、姊妹任务 [../2026-08-31-laptop-verb/design-review.md](../2026-08-31-laptop-verb/design-review.md)（同款度量修法）。

## 核心结论（一句话）

**grasp_cube 是 laptop_verb 的"干净版"——两者共享同一个度量/协议短板，但 grasp_cube 没有那个致命的 OOD 前提问题。** laptop_verb 错在选了 native 从没演示过的 `close` 动词（被测行为出了 repertoire，见 [[if-tasks-need-in-repertoire-behaviors]]）；而 grasp_cube 的两个被测行为**都在能力库内**——native `handover_block` / `stamp_seal` 都做过侧面抓（接触组 [4,5,6,7]），顶抓更是遍地都是。所以侧抓只是"已见子技能的新方向"，不是新技巧。**唯一要修的是度量，任务本身地基是稳的。**

## 维度判定

| # | 维度 | 判定 | 理由 |
|---|---|---|---|
| 1 | 轴隔离 | **OK** | 同一 cube、同一固定位姿、同一只臂（x=0→右臂），跨顶/侧只有指令词变。IF-Ext 里隔离最干净的一个 |
| 2 | 干扰物/中性 | **OK** | 单 cube 无 grounding 歧义；cube 几何**最大中性**——不像杯子（把手→侧）/盘子（→顶）有天然抓取 affordance，顶/侧都不被视觉偏向 |
| 3 | oracle 可行性 | **OK** | 两值都 100%（顶 100 / 侧 100，锁 face 6）。过 [[mic-drawer-oracle-infeasible]] 那条线——没有够不到的值 |
| 4 | 视觉可分 | **OK** | 末态夹爪**竖直 vs 水平**，相机上一眼可分（check-video 抽帧已证：n50 水平侧入 → n88 抬离） |
| 5 | **ACTION-OOD** | **RISK**（比 laptop 轻） | 侧抓非新技巧（native handover_block/stamp_seal 已做侧抓 + 顶抓遍地），oracle 证明可执行；但小 cube 侧抓在 native 更少见 + 顶抓先验强 → zeroshot/native-ft 下侧抓 0 有轻度歧义；ifext-ft 下溶解 |
| 6 | 判据分辨率 | **RISK（最高杠杆）** | `check_success = lifted AND oriented` 二元 AND **恰好糊掉 dim-5 关心的失败模式**："朝向对了但没抬起"和"用错抓法"都记 0，无法区分 |
| 7 | 先验强度 | **RISK/优点两面** | 顶抓先验**数据接地**（native 小物体几乎只顶抓）→ 真实且强，是优点；但也让"顶"条件近乎无信息（policy 本来就顶抓），判别力几乎全在"侧"条件 + gap 上，别看原始平均 |
| 8 | 评测协议依赖 | **RISK（必须明写）** | 非对称：ifext-ft 干净（两值都在分布内）；zeroshot/native-ft 下侧抓轻度 OOD + 二值判据 → 侧抓 0 歧义 |

## 综合结论

**四项硬指标（隔离/中性/oracle/可分）都强，比多数 IF-Ext 任务干净。短板集中在度量，且好修。**

- **as-is（二元 AND 判据）**：只在 `ifext-ft` 协议下是干净单轴诊断。
- **`zeroshot` / `native-ft`**：侧抓轻度 OOD + 二值判据 → 侧抓 0 无法归因（"没读指令" vs "读了但没夹住"）。**注意**：比 laptop_verb 的同名问题**轻一档**，因为侧抓在 repertoire 内（"做不出"这一支概率低），不是真 OOD。

## 单点最高杠杆改动（成本低、不动 oracle/几何）

> **把 `check_success` 从"lifted AND oriented"拆成两个分别上报**：
> - **approach-orientation-match**（夹爪 approach 轴是否匹配指令方向）= **主 IF 信号**，抓取失败也能测——policy 摆对了水平朝向但没夹住，仍算"读懂了指令"；
> - **lift**（是否抬离）= 执行信号。
> 再永远报 **顶/侧 gap**。

已有 `_approach_axis_z`，改动极小。这一改让"摆对朝向但没抬起"不再和"用错抓法"混成 0 → **三种协议下都干净可读**，解掉维度 5/6 的混淆。诊断真正信号是 **顶↔侧 gap**，不是侧抓绝对成功率。

## 要不要退成 seen-vs-seen 对照？

**不建议**。侧抓只是轻度 OOD（native 已有侧抓先例），而数据接地的顶抓先验正是让"侧"有意义的核心——退成全 seen 会把这个有价值的先验扔掉。**留着先验、修度量**即可。（对比 laptop_verb：那里 OOD 是真问题也仍建议留 laptop；这里 OOD 更轻，更没理由退。）

## 量产前额外提醒（不在 8 维内但重要）

**固定位姿 = 零感知变化**。纯测 IF 隔离没问题（判别信号是词不是位姿），但：① policy 可能"记住场景 + 词 → 动作序列"而不真感知；② 采出的数据集高度同质。若要它也测感知/泛化，需引入位姿抖动——但这**重新打开 face-locking 问题**（`SIDE_FACE=6` 在抖动下失效，x 变号会换臂，需按臂动态选面）。真实张力，量产时二选一：**纯 IF 隔离（固定位姿）** vs **IF+感知（抖动 + 动态选面）**。

## 待办（从本 review 派生）

- [ ] 给 `grasp_cube` 加拆分度量：`orientation-match`（主 IF 信号，approach 轴匹配）+ `lift`（执行），评测主报 orientation + **顶/侧 gap**，二元 AND 降为"完全成功"严格档。
- [ ] 任务文档**明写协议依赖**（ifext-ft 干净 / zeroshot·native-ft 需方向性判据），不藏。
- [ ] 量产时决策固定位姿 vs 抖动+动态选面（记进 [[grasp-approach-spike]] 的 face-locking caveat）。
