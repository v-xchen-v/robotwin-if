# Operate-Tabletop — 实现链路 + 验证证据

单实例（RoboTwin / aloha-agilex）。代码提交 `319bba0`。所有引用可顺路径复核：
- 实现：`tasks/envs/operate_tabletop.py`、`tasks/task_instruction/operate_tabletop.json`
- 证据：`evidence/layer-a-instructions.txt`、`evidence/layer-b-check-success.txt`、`evidence/collection-report.txt`

---

## 一、结果（验证方式 + 判据 + 证据）

三层验证，判据各不同：

| 验证 | 方式 | 判据（"算通过"） | 实际结果 | 证据 |
|---|---|---|---|---|
| **Layer-A** 指令路由 | 用 RoboTwin 真 `filter_instructions` 过滤三个 mode 的 params，纯 Python 无需仿真 | 每模板恰含一个 {A}/{B}/{C}；每动词 seen∩unseen=∅；filter 计数匹配 baseline（click 28/5、press 48/10、pick 12/4） | **23/23 PASS** | `evidence/layer-a-instructions.txt` |
| **Layer-B** 判定正反例 | 现场 `setup_demo` 构造终态，断言 `check_success()` 布尔。正例 C2/P2/K2 **真跑脚本专家**（接触/抬升判定没法用 set_pose 造假） | 每模式：正例 True、默认态 False、**拿错物体 K3 False** | **7/7 PASS**（aloha-agilex） | `evidence/layer-b-check-success.txt` |
| **Layer-C oracle 侧** 可操作性+分布 | 90-eps `collect_data`（use_seed=false，seed 0..91 顺序试），`report_operate_tabletop.py` 统计 | 每模式 oracle 成功率接近 native 基线；成功集三模式分布无偏 | **97.8%**（click 100/press 100/**pick 93.3**）；构成 **31/31/28** | `evidence/collection-report.txt` |

**为什么正例只能真跑专家（review 关注点）**：pick 的 held 判据 = 夹爪与目标有真实接触（`get_gripper_actor_contact_position`），click/press 判据 = 夹爪与目标顶部/cp2 有真实接触——都无法靠 `set_pose` 伪造，所以正例必须跑运动规划专家产生真接触；反例（默认态、拿错物体）则可用 set_pose 直接摆终态。K3 是关键反例：拿错物体（目标 `075_bread`、抬起干扰物 `081_playingcards`）时目标仍在桌面 → 正确判 False。

---

## 二、与相邻模块的关系（黑盒接口）

```
collect_data.py / eval_policy.py                     generate_episode_instructions.py
   │  kwags["seed"]                                     │ 读 scene_info[ep]["info"]
   ▼                                                    ▼
setup_demo(seed) ──► load_actors ──► play_once ──► self.info ──► scene_info.json
   (mode=seed%3)      (建场景)       (专家/埋info)      │              │
                                     check_success ◄────┘        report_operate_tabletop.py
                                     (keep/drop 或 eval success)  读 mode/objects
```
- **上游**：`collect_data`/`eval` 只传 `seed`（+共享的 `demo_clean` 配置）。mode 不是外部传入，是 env 内部 `seed%3` 派生。
- **下游**：`self.info["info"]`（{A}/{B}/{C}+{a}）喂离线 `filter_instructions` 生成语言；`self.info["mode"]/["objects"]`（顶层）喂 `scene_info.json` → 报告工具；`check_success()→bool` 喂采集(keep/drop)与 eval(success)。
- **桥接**：`bridge_tasks.sh` 把 env/json symlink 进 submodule 的 `envs/`、`description/task_instruction/`，类名=文件名=task_name。

---

## 三、Key mapping（逐字段，核心）

### 输入侧

| 来源 | 目标 key | 变换 | 代码 |
|---|---|---|---|
| `kwags["seed"]` | `self._seed` | 原样捕获 | `setup_demo` :81 |
| `self._seed` | `self.mode` | `["click","press","pick"][seed % 3]` | `load_actors` :99 |
| `np.random.choice([0,1])` | `self.bell_id` | 铃铛 model_id | :105 |
| `np.random.choice([0..6])` | `self.stapler_id` | 订书机 model_id | :118 |
| `_valid_model_ids(name)` | `self.graspable_ids[]` | 交集：`"stable":true` ∧ 有 mesh ∧ 有 `objects_description/base{N}.json` | :54-74, :149 |
| `np.random.choice([1,2])` | `num` | 可拿物体数量 | :137 |

### 输出侧

| 本模块产出 | 去向 key | 变换/layout | 代码 |
|---|---|---|---|
| click: `self.info["info"]` | `{"{A}":"050_bell/base{id}","{a}":arm}` | 仅 {A} → 路由到 touch 模板 | :190 |
| press: `self.info["info"]` | `{"{B}":"048_stapler/base{id}","{a}":arm}` | 仅 {B} → 路由到 press 模板 | :200 |
| pick: `self.info["info"]` | `{"{C}":"{modelname}/base{id}","{a}":arm}` | 仅 {C} → 路由到 pick 模板 | :208 |
| `self.info["mode"]` | scene_info.json 顶层 | 字符串，供报告按 mode 拆分 | :178 |
| `self.info["objects"]` | scene_info.json 顶层 | `["{name}/base{id}",...]` | :179 |
| `check_success()` | 采集 keep / eval success | bool | :212-245 |

**路由机制**：`filter_instructions`（native）只保留"非臂占位符集合 == params 非臂集合"的模板（{a} 可缺省）。三模式 params 分别是 {A}/{B}/{C} 单例 → 三向互斥路由，**零改动复用 native filter**。这是对 Stapler「{B} 有无二分」的三向推广。

**动词与 mode 解耦（易误解点）**：路由与判定都**不看指令动词**。`mode = seed%3` 在指令生成前定死；`filter_instructions` 按占位符 {A}/{B}/{C} 路由（Layer-A `leak=0` 证三池零串味）；`check_success` 按 `self.mode` 分支、不读指令文本。因此 click 分支借 native 而带的 "Press the bell's top" 与 press 分支撞动词，**只影响 policy 读到的语言难度（逼其 ground bell↔stapler），对 mode/场景/判据/路由零影响**。这是有意保留的设计（见 `understanding.md` 变更记录 #6）。

### 数值 provenance（每个魔法常量出处）

| 常量 | 值 | 出处（可核实） |
|---|---|---|
| click 接触 eps / z | `[0.025,0.025]` / `<0.03`；`contact_point_id=0` | 照搬 native `envs/click_bell.py::check_success` |
| click 下压位移 | `move_by_displacement(z=-0.045)` | 照搬 `click_bell.py::play_once` |
| press 接触 eps / z | `[0.03,0.03]` / `<0.03`；`contact_point_id=2` | 照搬 native `envs/press_stapler.py::check_success` |
| press 抓取序列 | pre=grasp=0.1 → close → pre=grasp=0.02 | 照搬 `press_stapler.py::play_once` |
| **pick 抬升阈值** | `target_z - target_origin_z > 0.02` | **类推自 `adjust_bottle`/`put_object_cabinet`（cabinet 用 0.007..0.12）；论文未确认**。已由 collection pick 93.3% 验证不偏严 |
| pick 抓取+抬升 | `grasp pre=0.1` → `move_by_displacement(z=0.1, move_axis="arm")` | 照搬 `adjust_bottle.py::play_once` |
| bell_id / stapler_id 范围 | `[0,1]` / `[0..6]` | 与 native click_bell/press_stapler 一致 |
| graspable resting qpos | `[0.707107,0.707107,0,0]` | glb 库标准静置朝向（90° about x），仅对 "stable" id 成立 |
| 摆放 | center_gap=0.05、min_sep=0.13、80 次重试；xlim/ylim 见 :103/:115/:150 | 自定（避开机械臂基座列 + 防重叠），经 collection 采集率验证（仅 2/92 失败） |
| target_origin_z 采集时机 | `load_actors` 里 `delay(2)` 沉降后 | 自定：eval 不跑 play_once，基线必须在 setup 采 :127-134 |

---

## 四、Core logic（一次完整调用的数据流）

```
setup_demo(seed):
  self._seed = seed                                  # :81
  _init_task_env_ → load_actors():
     mode = ["click","press","pick"][seed % 3]       # :99  ← 唯一的 mode 决定点
     bell  = create_actor(050_bell,  is_static=True) # 恒在场，click 目标 / 否则干扰
     stapler=create_actor(048_stapler,is_static=True)# 恒在场，press 目标 / 否则干扰
     graspables[1..2] = create_actor(pool, is_static=False)  # 恒在场，dynamic
        每个位姿 = _sample_pose(rejection: |x|≥gap ∧ 距已占≥min_sep)
     delay(2)                                          # 物理沉降
     if mode=="pick": target=graspables[0]; target_origin_z=target.z  # :130-134

  ── 分叉 ──
  (A) 采集/oracle: play_once():
        info["mode"], info["objects"] = ...           # 顶层埋点 :178-179
        if click: 抓铃铛顶(cp0)→下压 z-0.045→抬 z+0.045 ; info["info"]={A}
        if press: 抓订书机(cp2)→闭爪→再下压到 0.02   ; info["info"]={B}
        if pick : 抓 target→抬升 z+0.1(arm 轴)         ; info["info"]={C}
        collect_data 判定 plan_success ∧ check_success() → keep/drop seed
  (B) eval: policy 施加动作 → check_success()（mode 由 seed 已知）→ success

  check_success()  # mode-specific，只判当前目标：
     click: stage_tag 短路 | 动作臂夹爪闭合? | 夹爪∩铃铛cp0 在 eps 内
     press: stage_tag 短路 | 夹爪∩订书机cp2 在 eps 内
     pick : (target.z - target_origin_z > 0.02) ∧ 夹爪与target有接触

  ── 离线语言生成（另一进程）──
  generate_episode_instructions: scene_info[ep]["info"]（{A}/{B}/{C}+{a}）
     → filter_instructions(仅留占位符集合匹配的模板)
     → replace_placeholders({A}="050_bell/baseN" → objects_description/*.json → NL)
```
**quirk**：mode 纯 seed 派生（非 RNG 抽），因为 eval 对同一 seed 调两次 `setup_demo`，两次必须同 mode/同指令/同判定，与随机数抽取顺序解耦。

---

## 五、Policy eval 流程（下游接线，读自 `script/eval_policy.py`）

评测入口 `eval_policy.py`：`class_decorator(task_name)` → `importlib.import_module("envs.operate_tabletop")`（:29，桥接点）；`st_seed = 100000*(1+seed)`（:160，高位种子，评测场景与采集 0..N 不重叠）。主循环 `eval_policy`（:218 `while succ_seed < test_num`）每个候选 seed 两阶段：

```
① expert_check（:222-246）:
   setup_demo(seed=now_seed, is_test=True) → play_once()   # 跑脚本 oracle
   UnStableError/异常 → now_seed++ 跳过
   仅 plan_success ∧ check_success() → 该 seed 算"可解"有效题（否则跳过）
   ↳ 保证每道 eval 题 oracle 能解，policy 失败是 policy 的锅

② policy rollout（:256-307，同一个 seed 再来一次）:
   setup_demo(seed=now_seed)                         # ★同 seed → 同场景/同 mode
   episode_info["info"]（{A}/{B}/{C}+{a}）
     → generate_episode_descriptions(task, [info], ...)     # 走指令池 filter+replace
     → instruction = choice(results[0][instruction_type])   # ★ instruction_type=unseen
     → set_instruction(instruction)                          # policy 看到的语言
   while take_action_cnt < step_lim:
      obs = get_obs(); eval_func(model, obs)                 # policy 出动作、步进
      if eval_success: break                                 # eval_success ← check_success
   打印 Success!/Fail! + "Success rate: suc/test_num, current seed: N"
   now_seed++
```

**接线依赖我们的设计：**
- **同 seed 调两次 `setup_demo`（①②）** → mode 必须 `seed%3` 纯派生，两次才同 mode/同指令/同判据（这就是 §四 quirk 的 eval 侧根因）。
- **指令由 `info["info"]` 生成，取 `unseen`** → `{A}/{B}/{C}` 占位符路由；unseen = IF 核心（训练没见过的模板）。
- **`eval_success` ← 我们的 `check_success()`**（按 `self.mode` 分支）。

**结果：分 mode + 不分 mode。** `eval_policy.py` 自身只打**总和**（滚动 `suc/test_num`）+ 每题 `Success!/Fail!` + `current seed: N`，不分 mode。分 mode 靠 `tools/report_operate_tabletop.py --eval-log`（`report_eval_log`）：解析日志、`mode = seed%3` 反推，一份日志同出 **aggregate + click/press/pick 三档**（与 collection 报告同格式）。
```
<eval 启动> instruction_type=unseen | tee eval.log
python tools/report_operate_tabletop.py --eval-log eval.log
```

**未跑：** policy eval 需要一个训练好的 `policy_name` 模块；本轮全在 oracle 侧验证。policy eval + Layer-C（瞎猜 baseline）+ Layer-D（对论文量级）延到 policy/eval 阶段五任务一起做。report 工具已就绪。

---

## 六、证明了什么 / 不证明什么（边界）

**证明了：**
- **三向路由接线正确**：占位符互斥、seen/unseen 无重叠、native filter 计数匹配（Layer-A 23/23）。
- **判定逻辑正反例正确**，含"拿错物体判 False"这个 IF 命门（Layer-B 7/7，真跑专家产生真接触）。
- **场景可操作 + 分布无偏**：三分支专家稳定跑通（100/100/93.3%），成功集近均匀（31/31/28），物体池均匀无垄断（Layer-C oracle 侧，90 eps）。
- **数值约定与 native 一致**：click/press 阈值照搬 click_bell/press_stapler；pick 阈值虽为类推，但经 collection 成功率验证不偏严。

**不证明（防过度引用）：**
- **不证明任何 policy/model 效果** —— 全程没跑真 VLA policy，只有脚本 oracle 和构造终态。
- **不证明 Layer-C 区分度的另一半**（瞎猜/默认动作 baseline ≈ chance 1/3）—— 需 dummy policy 过 `eval_policy.sh`，**延到 policy/eval 阶段**（见 `understanding.md` 待确认，与 design.md 一致）。
- **不证明跨具身** —— 仅在 aloha-agilex 上验；换 Piper/Franka 抬升幅度不同，pick 的 0.02 阈值可能需重标。
- **不证明"人眼看单帧图分不出 mode"** —— 场景恒定假设逻辑上成立，但未实拍验证。
- **pick 的 2/30 失败根因未逐一定位** —— 大概率抓取失败/摆放太挤，不影响 93.3% 结论，但没深挖。
