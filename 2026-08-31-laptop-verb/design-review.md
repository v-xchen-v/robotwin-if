# IF-Verb-Select — task design review（基准有效性）

> 由 `/task-design-review laptop_verb` 产出（三评测协议全评）。这不是代码 review，是"这个任务到底测没测到它声称要测的东西"。实现见 commit `56f1149`。相关：[understanding.md](understanding.md)（与 native 的关系）、[decisions.md](decisions.md)、[gotchas.md](gotchas.md)。

## 维度判定

| # | 维度 | 判定 | 理由 |
|---|---|---|---|
| 1 | 轴隔离 | **OK** | `scene=seed//2` 让 (2k,2k+1) 像素级同帧，唯一变量是动词；初始帧零混淆（已验同 model_id/位姿/qpos） |
| 2 | 干扰物/中性 | **OK** | 单物体、50% 半开是**最歧义**态，几何不泄答案，动词是唯一区分信号 |
| 3 | oracle 可行性 | **OK** | 子集 {1,9} 开 90%/关 100%，两值都过 ~90%；成对门控保证每个场景双向可演。过 [[mic-drawer-oracle-infeasible]] 那条线 |
| 4 | 视觉可分 | **OK** | 50%→开 ~78%/关 ~5–15%，三档相机上清楚可分（check-video 已证） |
| 5 | **ACTION-OOD** | **RISK**（zeroshot/native-ft 下近 BLOCKER） | close 非新技巧（抓盖=native 见过 + 往下移=见过，只是新方向/组合），oracle 证明可执行；但对 native-only 模型 OOD，**叠加二值判据 → close=0 歧义**（没跟随 vs 做不出），污染单轴 |
| 6 | 判据分辨率 | **RISK** | `check_success` 是**二值**（qpos≥70%/≤20%），OOD close 易 floor；反例正确（Layer-B 12/12），但**无方向性/分级度量**，分不清"往关方向压了但没到底"和"走错方向" |
| 7 | 先验强度 | **OK（且是优点）** | **强 + 数据支撑**：58 个 native 里 laptop 只被开过、零闭合动作 → "laptop→开"是数据层面惯性，非仅语义。是更硬更真实的测试；但它和维度 5 的 OOD 是**一枚硬币两面**（强先验正因为 close 是 native 没演示的那个值） |
| 8 | 评测协议依赖 | **RISK（必须明写）** | 有效性随协议翻转（见下） |

## 综合结论

**as-is（二值判据）只在 `ifext-ft` 下是有效的单轴动词诊断。**

- **`ifext-ft`**（在含我们 close 演示的 IF-Ext 数据上微调）：close in-distribution + 强先验保留 → **干净有效**。
- **`zeroshot` / `native-ft`**：close OOD + 二值判据 → close=0 无法归因（"没读动词" vs "读了但执行不出"），单轴坍塌 → **当前形态不成立**，除非换判据。

## 单点最高杠杆改动（成本低、不动 oracle）

> **主判据从二值 band 改成方向性/分级**：记 Δqpos 朝指令端的**符号**（方向对不对）+ **覆盖比例**（走了多少）；二值 band 降为"完全成功"严格档；**永远报 open/close 分开 + gap**。

这一改让任务在**三种协议下都能干净读**：方向性把"读了动词但欠执行"和"走错方向"分开，解掉维度 5/6 的混淆，`zeroshot`/`native-ft` 也不再 floor 成一团。诊断的真正信号是 **open↔close 的 gap**，不是 close 绝对成功率。

## seen-vs-seen 对照（可选）

若主评测是 `zeroshot`/`native-ft` 且想要**无混淆**读数，值得再加设计文档候选 C（同物体 pick vs press，两动作都 native）当 baseline——但**别用它替掉 laptop**：laptop 的数据支撑强先验是更有价值的真实测试。两者三角互证：**laptop = 强先验 + 带 OOD；seen-action = 纯隔离 + 弱先验**。

## 待办（从本 review 派生）
- [ ] 给 `laptop_verb` 加方向性/分级度量（`_direction_progress()` 之类），评测时主报方向 + gap、二值 band 作严格档。
- [ ] 在任务文档里**明写评测协议依赖**（ifext-ft 干净 / zeroshot·native-ft 需方向性判据），不藏。
- [ ] （可选）评估是否加 seen-vs-seen 动词对照任务。
