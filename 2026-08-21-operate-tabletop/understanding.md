# Operate-Tabletop — understanding

Feature: RoboTwin-IF 第 3 个复刻任务（复用型），对应 `docs/features/03-Operate-Tabletop.md`。
实现提交：`319bba0`（主仓库 master）。

## 当前理解

### 这个 feature 实际解决的是什么问题

在**同一个恒定的桌面场景**（铃铛 `050_bell` + 订书机 `048_stapler` + 1–2 个可拿取物体）里，做**三选一的"动词+目标"判别**，用来诊断 VLA policy 是否真按语言选动作（IF 的核心：防止 VLA→VA 退化成"看图做默认动作"）。画面在三种模式下静止时完全一致，只有指令变 → 正确动作变：

- **click**：触碰铃铛顶部中心（一个向下的 touch，**不是摇铃/发声**）——复用 `click_bell`
- **press**：原地按下订书机——复用 `press_stapler`
- **pick**：拿起指令点名的那**一个**物体——复用 `adjust_bottle`（单臂纯拿起）的 grasp+lift

模式由 `seed % 3` 纯派生（保证 eval 两次 `setup_demo(同 seed)` 生成同一指令+同一判定）。三向指令路由靠**三个不同占位符**：`{A}`=铃铛(仅 click 模板)、`{B}`=订书机(仅 press 模板)、`{C}`=被拿物体(仅 pick 模板)，每个 episode 的 `info["info"]` 只填其中一个，原生 `filter_instructions` 按"非臂占位符集合精确匹配"零改动路由——这是对 Operate-Stapler「用 `{B}` 有无二分」机制的三向推广。

指令池**全部借自 native raw-task 池**（不手写）：click←`click_bell.json`（`{A}` 不变）、press←`press_stapler.json`（`{A}→{B}`）、pick←`adjust_bottle.json`（`{A}→{C}`，丢瓶子专属措辞）。

`check_success` 是 **target-specific**：只判当前模式那个目标的动作条件（click=铃铛顶接触；press=订书机 cp2 接触；pick=点名物体抬离桌面 >0.02m 且仍被夹爪接触）。做错动作/拿错物体会让本模式条件不满足而自然 False。

### 边界：没做什么 / 明确排除

- **不做颜色+名词 grounding**：pick 的 1–2 个物体总是**不同品类**，靠名词即可区分，不放同品类撞色物体（用户确认；design-point 4 的"复用 Pick-Diverse-Object grounding"仅指 check 逻辑同源，不是颜色消歧）。
- **不做 check 的跨物体互斥守卫**：只判本模式目标，不额外断言"其它物体没被碰"（用户确认，与 Stapler 一致）。
- **不接 eval 任务列表**（`all_tasks_plus_if.yml`）、不代跑 collection/eval——留到设计阶段 6/7。
- **不用 MLLM description-gen**、不新增 `objects_description` 文件（复用现成）。
- **不现在抽 task-04 共用的 pick-grounding helper**（inline now, refactor later）。
- 指令措辞不手撰，全来自 native 池。

### 验收标准

- **Layer A**（指令路由，本机可跑）：`python tests/operate_tabletop/test_instructions.py` → 全 PASS。检查三向占位符互斥、每动词 seen∩unseen=∅、native filter 路由计数（click 28/5、press 48/10、pick 12/4）。
- **Layer B**（judgement 正反例，需 RoboTwin 环境）：`test_check_success.py` → 每模式正例 True、默认态 False，**K3 拿错物体 → False**。
- `py_compile` 全绿 + bridge symlink 在位。

## 理解变更记录

1. **click 动词：以为是"摇铃/ring"，实为"touch the bell top"。**
   最初实现 + 第一版指令模板我用了 ring/shake/strike/sound/ding 这类"发声"措辞（设计文档里"摇铃"的中文标签误导了我）。用户纠正"不是摇铃铛是 touch the bell"。查 native `click_bell.json` 坐实措辞全是 "touch/tap/press/click the bell's top center" —— 行为和判定我其实一直写对（下压触顶再抬起 + 顶部接触判定），**只有指令措辞错了**。

2. **指令池：以为要手写，实为借用 native raw-task 池。**
   前两轮我按"手写 ~16/verb"推进，还在跟用户敲定手写模板的规模/主题。用户点出"从两个 raw task 可复用的 click_bell 和 press_stapler，instruction 的构造不借鉴一下吗"——这才是项目既定套路（Stapler 的 press 组就是 `press_stapler.json` 原样搬的）。改为整组借 native 池 + remap 占位符，"~16/verb"的决定被覆盖。

3. **pick 借用源：以为"没有单臂纯拿起的原生任务"，实为有 `adjust_bottle`。**
   我一开始断言 pick 分支没有对应原生任务，退而选 `grab_roller`（双臂抓），并据此提问。用户push back："没有 single arm pick 的任务吗？搜搜，如果有的话参考它是最好的。" 穷举所有 `full_description` 后找到 `adjust_bottle`（"Pick up the bottle ... with the correct arm"），它的 env 动作（`grasp_actor` + `move_by_displacement(z, move_axis="arm")`）跟我 pick play_once 写的一模一样——比 grab_roller 贴太多。教训：下结论"没有 X"前先搜穷尽。

4. **pick 成功判定基线的采集时机：从 play_once 挪到 setup。**
   参照 `put_object_cabinet` 时它在 `play_once` 里记 `origin_z`，但 eval **不跑 play_once**（那是 oracle），基线会失效。改成在 `load_actors` 里 `delay(2)` 沉降后采 `self.target_origin_z`，check 才在 eval 下可用。

5. **可拿物体 model_id 需过滤"有 objects_description"。**
   实现中发现：`{C}` 解析走 `replace_placeholders`，若物体缺 `objects_description/{name}/base{N}.json` 会 hard-exit。于是 `_valid_model_ids` 在 stable + 有 mesh 之外，再加"有 description json"的交集。

（没有为了凑数编造——以上均是本次会话真实发生的调整。）

## 待确认

- [x] **click 动作语义 = touch 非 ring** —— 已由 native `click_bell.json` 措辞 + 用户纠正确认；指令池已用 native 措辞重建（`319bba0`）。
- [x] **pick 借用源 = `adjust_bottle`（单臂纯拿起）** —— 已穷举 `full_description` 确认是 RoboTwin 里唯一单臂纯拿起任务（`319bba0`）。
- [x] **三向路由正确性** —— Layer-A 23/23 PASS（本机，无需仿真）。
- [x] **判定正反例（含拿错物体）** —— Layer-B 7/7 PASS（`conda run -n RoboTwin ...`，2026-08-21，aloha-agilex）：C1/P1/K1 默认态 False、C2/P2/K2 正例 True、K3 拿错物体（目标 075_bread、抬起干扰物 081_playingcards）False。
- [ ] **pick 的 0.02m lift 阈值是类推值（论文未确认）。** 实测正例稳定 True、拿错物体 False，当前够用；但若换具身（如 Piper/Franka）或换物体池，抬升幅度不同可能需要重标。靠更大规模 collection 的 oracle 成功率来验证是否偏严/偏松。
- [ ] **场景恒定 across 三模式 是最 load-bearing 的假设**（IF 命门：看图不能反推指令）。当前实现三类物体每 episode 都在场、bell/stapler 恒 static、graspable 恒 dynamic。逻辑上成立，但"人眼看单帧图确实分不出模式"这点没有实拍验证；错了会让 policy 能靠场景布局作弊、benchmark 失去区分度。要靠 Layer-C（瞎猜 baseline 接近 chance、作弊 oracle 接近 100%）来验证，本轮未做。
- [ ] **1 个可拿物体时 pick 分支没有"可拿型干扰物"**（只有 bell/stapler 当错动作干扰）。num∈{1,2} 随机，num=1 时 pick 的目标 grounding 退化到"场上唯一可拿物"。是否可接受取决于论文对"1-2 物体"的原意，无法从公开信息确认。
- [ ] **物体池摆放拥挤度**：`_sample_pose` 用 min_sep=0.13 + 80 次重试在 ~0.5×0.25 桌面塞 3–4 个物体，偶发 `UnStableError`/放不下会靠 seed 重试跳过。大规模 collection 时若某些 seed 长期失败会拉低 oracle 采集率，需 collection 报告观察（`tools/report_operate_tabletop.py` 有 per-episode 物体数 + 分布统计）。
