# Operate-Stapler 已知隐患 / 技术债（gotchas）

> 维度：这份记的是「即使理解/设计对齐了，实现本身仍存在的已知风险、边界情况、技术债」。设计与必守约束见同目录 `spec.md`。
>
> 最重要的一条（① 库对象随机 model_id）**会在其余 4 个用到干扰物/多物体随机 model_id 的 IF 任务复发**：Pick-Diverse-Object、Place-Relative、Operate-Tabletop。`_valid_model_ids` helper + config-None 兜底是可直接复用的缓解。

## ① 库对象随机 model_id / 朝向的坑（跨任务，高优先级）

RoboTwin 的 `assets/objects/<name>/` 资产库**数据不规整 + 朝向约定不统一**。对某个 asset 随机采 `model_id` 并摆放时，有三类静默问题：

### 坑 A：model_id 不连续 → 采样越界 → `create_actor` 返回 None

- 现象：`'NoneType' object has no attribute 'get_pose'`（偶发）。
- 根因：不能假设 model_id 是连续的 `0..N-1`。例：`071_can` 的 id 是 `{0,1,2,3,5,6}`——**缺 4**。若用「`model_data*.json` 文件数当上界 + `randint(0, count)`」，既会采到不存在的 4（`create_actor` 打印 `... is not exist model file!` 后 `return None`），又永远采不到有效的 6。
- 下游：`None` 传给 `add_prohibit_area` → `actor.get_pose()` 崩。

### 坑 B：model_data 缺 `"scale"` 键 → `actor.config` 为 None → `.get` 崩

- 现象：`'NoneType' object has no attribute 'get'`（每次选中该 asset 必崩）。
- 根因：`create_actor` 里 `try: model_data=json.load(f); scale=model_data["scale"]`，若 JSON **有文件但没有 `"scale"` 键**（例：`108_block` 的**所有** model_data 都缺 scale），KeyError → except → `model_data=None`，但 mesh 存在 → 返回一个 `config=None` 的 actor（不是 None actor！）。
- 下游：`add_prohibit_area` 里 `actor_data = actor.config; actor_data.get("scale", 1)` → `.get` on None 崩。

### 坑 C：物体朝向 —— 只有 `stable` 物体能用统一 qpos 平躺（跨任务，重要）

- 现象：干扰物竖立/悬浮，物理不真实——如 `058_markpen` 笔竖在桌上。
- 根因（两层）：
  1. 每个 mesh 的 canonical 坐标系不同，不能把任务主物体（订书机 `[0.5,0.5,0.5,0.5]`）的 qpos 套给别的物体。
  2. **更关键**：不是每个物体都有"平躺静止姿态"。RoboTwin 在 model_data 里用 `"stable"` 标志区分——球（`035_apple`）、圆柱/细杆（`058_markpen`/`010_pen`/`083_brush`）、`116_keyboard` 等都是 `stable:false`，会滚或立不住，RoboTwin 自己的动态 clutter 直接**排除**它们。
- 正解（省事且正确）：**干扰物只从 `"stable": true` 的 model_id 里采**（就是 `get_all_cluttered_objects` 用的同一套过滤），这些被验证过能用 **glb 平躺 qpos `[0.707107,0.707107,0,0]`** + 绕竖直随机 yaw 自然躺平，**零逐物体调参**。非 stable 的物体不要用作静态干扰物。
  - 注：我们的干扰物是 `is_static=True`，所以"会滚"对我们其实无所谓；但"没有平躺姿态"意味着没有现成 qpos，硬摆要逐物体手推 qpos+z（`rand_pose` 的 `rotate = qpos ⊗ euler`）并靠重跑校准——不值得，直接换等价的 stable 物体（如要"笔"就用 stable 的 `093_brush-pen` 替 `058_markpen`）。
- 调研旁证：RoboTwin **50 个原生任务无一**把 markpen 当放置物体；它只在物体描述（语言）和 `create_messy_data.py` 的调试查看器里出现，从没被"静置到桌上"过。
- z 不用精确：`check_stable` 会先 step 2000 帧让物体自然沉降，轻微悬空/穿模自解。

### 复用缓解（已在 `tasks/envs/operate_stapler.py`）
1. **`_stable_model_ids(modelname)`**（带类级缓存）：只返回「`model_data{N}.json` 标了 `"stable": true` **且** mesh 存在」的 id 列表，`np.random.choice` 采样 → 一并根治坑 A（不存在的 id 不可能 stable）+ 坑 C（只用能平躺的物体）。
2. **create_actor 返回 None 就 `continue`** → 兜底坑 A。
3. **config 为 None 时用 pose 版 prohibit area**：`add_prohibit_area(actor if actor.config is not None else actor.get_pose(), ...)`。传 Pose 时用空 config + 默认 extents，绕开 `.get` → 根治坑 B。
4. **glb 平躺 qpos**：干扰物统一用 `qpos=[0.707107,0.707107,0,0]` + `rotate_lim=[0,π,0]`（仅对 stable 物体正确，故与第 1 条配套）→ 根治坑 C。
5. **干扰物池只收 stable 办公/文具物体**（phone/phonestand/remotecontrol/pencup/brush-pen/notebook/glue/playingcards/seal/scanner/mouse/cup），全部自然平躺、无需逐物体调 qpos/z。

> 注：坑 B 未检查 `"scale"` 键本身——若某 stable 物体的 model_data 缺 scale（如 `108_block`/`017_calculator`），create_actor 仍返回 config=None 的 actor，靠第 3 条兜底。若未来任务要**抓取/放置**这类对象（需 contact/functional point，都在 config 里），config=None 不可用——那时换 asset 或补 model_data。

### 干扰物池实测 stable model_id（截至 2026-08-20，submodule commit `0aeea2d`）

| asset | stable model_id | 备注 |
|---|---|---|
| 077_phone | 0–4 | |
| 078_phonestand | 0–6 | |
| 079_remotecontrol | 0–6 | |
| 059_pencup | 0–6 | 笔筒 |
| 093_brush-pen | 0,1,2,4,5 | stable 的"笔"，替代 markpen |
| 092_notebook | 0–2 | |
| 095_glue | 0,1,2,4,5,6 | |
| 081_playingcards | 0–2 | |
| 100_seal | 1,2,3,4,6 | |
| 024_scanner | 2 | 仅 1 个 stable id |
| 047_mouse | 0–2 | |
| 021_cup | 0–12 | |

> 被排除的：`035_apple`/`058_markpen`/`010_pen`/`083_brush`/`116_keyboard`/`117_whiteboard-eraser`（无 stable id）；`108_block`/`017_calculator`（stable 但缺 scale → config=None，本池未用）。`071_can` 虽 stable 但缺 id 4（不连续），是坑 A 的实例。

## ② 其他已知隐患 / 技术债（本任务范围内）

- **base 初始化顺序**：`_init_task_env_` 里 `self.info = dict()` 在 `self.load_actors()` **之后**才执行。⇒ `load_actors` 内**不能碰 `self.info`**（已把 `self.info["mode"]` 移到 `play_once`）。这是所有 task 类通用坑。
- **step_lim per-task 不 per-mode**：`_eval_step_limit.yml` 按 task_name 取，一个 task_name 两个 mode 共用一个 step_lim。当前吃 1000 fallback。若 move mode（抓取+搬运，步数更多）在 1000 步内跑不完，会被判失败——**待实测确认**，不够就得给 operate_stapler 单独配一个更大的值。
- **expert_check gate 对脆弱 mode 的 under-sampling**：eval 中 setup#1 专家跑不成功的 seed 直接跳过。两个 mode 的专家鲁棒性若不均衡（如 move 抓取偶发失败率高于 press），会导致该 mode 在 eval 中被系统性少采、mode 分布偏离 50/50。**待实测确认**两个 mode 的专家成功率是否接近。
- **干扰物 prohibit area 近似**：config=None 的对象（block）用默认 extents（~0.1m 盒）而非真实尺寸，keep-out 区域可能与实物略有偏差。本任务干扰物已在放置时与订书机/垫子保持 0.12m 间距、prohibit area 基本冗余，可接受；属轻度技术债。
- **UnStableError 偶发**：干扰物/物体落定时偶发物理不稳，被 gate 跳过换 seed，属正常，不是 bug。
