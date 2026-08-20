# Operate-Stapler 实现前 spec + 关键设计发现

> 维度：这份是**实现前**的假设澄清 + spec 落盘（走 `vibe:pre-impl-clarify`）。问题层面（RoboTwin-IF 是什么、5 个任务集）见 `docs/design.md`；桥接机制见 `2026-08-19-task-bridging/architecture.md`。
>
> 状态：spec 已与用户确认，准备开工。

## 一句话定位

Operate-Stapler = 把原生 `press_stapler` + `move_stapler_pad` 合并进**同一个场景**（订书机 + 彩色垫 + 干扰物），指令的**动词**决定做哪件事——测 VLA 是否真按语言控制动作（诊断 VLA→VA 退化）。垫子在两种指令下角色翻转：press 时是干扰项，move 时是目标。

## 核心设计：mode 是唯一枢纽

**不要**设计成 `instruction → mode → 场景/判定`（框架不支持：指令是从场景生成出来的下游产物，不是输入）。正确结构是一处采样、三处读取：

```
seed → self.mode → ┬─ load_actors:   按 mode 建场景（仅 is_static 不同）
                   ├─ play_once:     按 mode 出专家轨迹 + 写 info（带不带 {B}）
                   ├─ (info → generate_episode_descriptions → instruction)
                   └─ check_success: 按 mode 判定
```

instruction 和 check_success 是**兄弟**，都从 `self.mode` 派生 → 天然一致，不需要"从指令反推 mode"。

## 关键约束 / 非显然的坑（实现必守）

### 1. mode 必须 seed 决定（eval 侧致命）

eval 一个被接受的 seed 会 `setup_demo` **两次**（[eval_policy.py:224 / :256](../../third_party/robotwin/script/eval_policy.py)）：
- setup#1 → load_actors 采 mode(m1) → 专家 play_once → 产出 `episode_info`（**指令从这生成**）→ close
- setup#2（同 seed）→ load_actors **重采** mode(m2) → 不再跑 play_once，policy 上场 → `check_success` 读 **m2**

指令 mode=m1、判定 mode=m2 是**两次独立采样**，没有任何代码把 m1 传给 setup#2、也没有从指令反推 mode。m1==m2 **完全靠 seed 决定论**。若不满足，eval 会**静默地**用与指令不符的 mode 打分、不报错、直接污染分数。

- 采集侧（`collect_data.py`）只有一次 setup，play_once/check/轨迹共享同一内存 `self.mode`，一致性结构性自动保证——所以这个坑**只在 eval 侧**、比采集侧更要命。
- 安心点：RoboTwin eval **本来就依赖** load_actors 全字段 seed 决定论（原生 `move_stapler_pad` 的 `{B}`=颜色同样 setup#1 采、setup#2 复现）。mode 只是又一个 seeded 参数，搭已有保证。
- mode 比 color 多的新风险：mode 改变 load_actors/play_once 的**控制流分支**，分支里 RNG 消耗数不同。对策：**用纯 seed 派生、免疫 RNG 顺序**：
  ```python
  def setup_demo(self, **kwags):
      self._seed = kwags.get("seed", 0)
      super()._init_task_env_(**kwags)
  def load_actors(self):
      self.mode = ["press", "move"][self._seed % 2]   # load_actors 第一行
  ```

### 2. is_static 冲突 → 随 mode 切（方案 A）

`press_stapler` 里订书机 `is_static=True`（否则一按就倒），`move_stapler_pad` 需要非静止才能抓。共享场景没法同时满足 → `is_static=(mode=="press")`。这是物理属性，静止画面上几乎不可见，不破坏"视觉一致"的诊断前提。附带好处：press mode 下订书机被 weld，policy 若误去"搬"物理上本就失败，判定自然 False。

### 3. 指令靠 `{B}` 有无自动路由

`filter_instructions`（[generate_episode_instructions.py:18](../../third_party/robotwin/description/utils/generate_episode_instructions.py)）只保留**占位符集合与 episode 参数精确相等**的模板（`{a}` 臂占位符是唯一可选例外）。episode 参数就是 play_once 写的 `info["info"]`。于是：
- press：`info={"{A}":.., "{a}":..}`（无 B）→ 带 `{B}` 的 move 模板被过滤掉
- move：`info={"{A}":.., "{B}":.., "{a}":..}` → 缺 `{B}` 的 press 模板被过滤掉

**硬约束**：press 模板绝不含 `{B}`，move 模板必须含 `{B}`。且**每个动词必须在 seen 和 unseen 都出现**（生成器对 seen/unseen 分别 filter，eval 的 `instruction_type` 由 config 定死；某动词若在 unseen 缺席，该 mode 在 unseen 评测下 filter 完为空 → 测不到）。占位符拼错会**静默丢 episode**（filter 空只 print 后 continue）。

### 4. step_lim 是 per-task 不是 per-mode

[_base_task.py:142-148](../../third_party/robotwin/envs/_base_task.py) 按 task_name 取，查不到 fallback 1000。一个 task_name 两个 mode 共用一个 step_lim → 按较长的 move mode 定，或直接吃 1000 fallback（不碰 submodule 的 `_eval_step_limit.yml`）。

### 5. expert_check gate 按当前 seed 的 mode 跑

setup#1 专家（在 m1 下）不成功该 seed 直接跳过 → **两个 mode 的专家都得稳**，否则谁脆谁的 mode 在 eval 被系统性少采。

## 架构结论：eval pipeline 零修改

pipeline 对"做什么/怎么算成功"**完全多态**——只调 `play_once()` / `check_success()`，不关心内部分支：
- `check_success` 每 `scene.step()` 后在 [_base_task.py:1657](../../third_party/robotwin/envs/_base_task.py) 被调，跑在 setup#2 env（`self.mode`=m2），True 置 `eval_success`、外层 break。我们的 `if self.mode` 对它透明——**这正是 50 个原生任务已在用的多态**。
- 两次 setup 一致性是框架既有不变量，mode 搭车即可。

**唯一 stock pipeline 给不了的**：它只按 task_name 汇总一个**混合成功率**（[eval_policy.py:319](../../third_party/robotwin/script/eval_policy.py)），不按 mode 拆分。复刻分数够用（只会 press 的退化 policy 混合率掉到 ~50%，诊断成立）；想要分动词细分率就自己在 check/episode 末落一行 `self.mode` 日志，**不改 pipeline**。

---

## Spec（已确认）

### 要做什么

**文件（走现有桥接，不碰 submodule）**
- `tasks/envs/operate_stapler.py` — `class operate_stapler(Base_Task)`
- `tasks/task_instruction/operate_stapler.json`
- 复用 `bridge_tasks.sh` symlink，不新增 objects_description

**mode（纯 seed 派生）**
- `setup_demo` 里 `self._seed = kwags.get("seed", 0)`
- `load_actors` 第一行 `self.mode = ["press","move"][self._seed % 2]`
- `self.mode` 写进 `info` 供 per-mode 日志

**场景（两 mode 视觉一致，仅 is_static 变）**
- 订书机 `048_stapler`，model_id 随机 0–6，`is_static=(mode=="press")`，按压点 `contact_point_id=2`
- 垫子 `create_box`，`half_size=[0.055,0.03,0.0005]`，8 色 seeded，两 mode 都放，沿用 `move_stapler_pad` 同侧摆放采样
- 干扰物：池 `bottle/cup/apple/mouse/can/phone/markpen/block`，随机 1–2 个，model_id 按各 asset 实际可用数随机，加 prohibit_area，重叠重采样

**专家 play_once（单臂，按订书机 x 正负选臂）**
- press：复用 press_stapler 抓→合爪→下压；`info={A,a}`（不含 B）
- move：复用 move_stapler_pad 抓→抬→align 放置；`info={A,B,a}`

**check_success（`if self.mode` 分支）**
- press：复用夹爪-订书机 contact_point 2 接触检测 + `stage_success_tag` latch
- move：复用 pose 对齐 + 姿态一致 + 双爪张开

**指令**
- 一份 `operate_stapler.json`，**复用合并** `press_stapler.json`（无 `{B}`）+ `move_stapler_pad.json`（含 `{B}`）的 seen/unseen，保留各自原始 seen/unseen 划分；靠 `{B}` 有无自动路由

### 不做什么
- 不改 submodule 源码 / 不改 eval pipeline（已确认零修改）
- 不跑 MLLM 重生成模板、不训练、不做 Layer C baseline、不做双臂、不新建 asset
- step_lim 吃 1000 fallback，不动 `_eval_step_limit.yml`（move mode 若不够再议）

### 验收标准（Layer A + B）
- **A 集成**：`envs.operate_stapler` 可 import；bridge 后进 eval 调度不崩；`operate_stapler.json` per-verb seen∩unseen = ∅ 断言通过
- **B 判定**（oracle 正/反例，允许物理随机性）：
  - press mode：压订书机 → True；去搬订书机 / 碰干扰物 → False（is_static=True 时错误"搬"物理上本就失败）
  - move mode：订书机上对的垫子 → True；干扰物上垫子 / 订书机没到垫子 → False
- **mode 决定性**：同 seed 两次 setup → mode 一致（可断言）
