# Operate-Stapler 实现链路 + 验证结果（impl-verify）

> 可核对证据底稿。事实全部核对自实际代码（`tasks/envs/operate_stapler.py`，主仓 commit `50c756b`）与磁盘验证产物（`evidence/`）。配套：`spec.md`（实现前 spec）、`understanding.md`（问题理解）、`gotchas.md`（已知隐患）。
> 相关代码位置：任务 `tasks/envs/operate_stapler.py`；指令 `tasks/task_instruction/operate_stapler.json`；上游依赖 `third_party/robotwin/`。

## 一、结果（验证方式 + 判据 + 证据）

**验证方式**：用 RoboTwin 自带的**脚本化 oracle 专家**（`script/collect_data.py`，非训练模型）在 `demo_clean` 配置下采集。这是 Layer B 的正例验证——oracle 按 mode 正确操作，`check_success` 应稳定 True。

**判据**：`plan_success and check_success()` 为 True → episode 落盘（含轨迹+video+指令）。附加 `{B}` 路由判据：press 集指令 0 处含垫子颜色、move 集每条含垫子颜色。

**实际结果**（`evidence/scene_info.json`，seed 0/1）：

| episode | seed | mode | 结果 | `info["info"]` | 干扰物（新 stable 池） |
|---|---|---|---|---|---|
| 0 | 0 | press | ✅ success | `{A:048_stapler/base1, a:left}`（无 `{B}`） | `021_cup/base0`, `081_playingcards/base1` |
| 1 | 1 | move | ✅ success | `{A:048_stapler/base0, B:Magenta, a:right}` | `095_glue/base0` |

- `mode = seed%2` 得证：seed0→press、seed1→move，与 scene_info 落盘一致。
- 干扰物来自新办公池（cup/playingcards/glue），非旧池（markpen）——video mtime(08-20 08:30) 晚于代码(08:25)，确系新池运行。

**`{B}` 路由验证**（`evidence/instructions_episode*.json`，各 200 条 = seen100+unseen100）：

| episode | mode | 含垫子颜色 | 含字面 "mat" |
|---|---|---|---|
| 0 | press | **0 / 200** | 0 / 200 |
| 1 | move | **200 / 200** | 196 / 200 |

- press 集 0 条提垫子/颜色——`info` 不写 `{B}`，带 `{B}` 的 move 模板被 `filter_instructions` 过滤掉。
- move 集 **200/200 全含颜色** `Magenta`；其中 196 条用 "mat" 字样，另 4 条措辞为 "…shift it to Magenta"（无 "mat" 但有颜色）。**故按"含 pad 颜色"口径是 100%**。
- press 指令里频繁出现的 "black" 是**订书机自身颜色描述**（来自 `048_stapler` objects_description），非垫子颜色——不算泄漏。

**证据文件**（`evidence/`）：
- `scene_info.json` — 证明 mode/seed 对应 + 干扰物为新池。
- `instructions_episode0_press.json` / `instructions_episode1_move.json` — 证明路由（press 无颜色 / move 全颜色）。
- `episode0_press.mp4` / `episode1_move.mp4` — 证明两 mode 专家行为可跑通（按压 / 抓取-抬-对齐放置）。

## 二、与相邻模块的关系

RoboTwin 从不 import 本仓；靠 `task_name` 在固定目录按名找文件（`bridge_tasks.sh` symlink 注入）。本任务对采集/评测 pipeline **零侵入**，靠现有多态契约：

- 上游给：`setup_demo(seed, **args)` → 触发 `load_actors`（建场景+采 mode）。
- 本模块给专家：`play_once()` → 轨迹 + `self.info`。
- 指令生成：`info["info"]` → `generate_episode_instructions.py` → 每 episode 的 seen/unseen 指令。
- 判定：pipeline 每 `scene.step()` 后调 `check_success()`（多态，按 `self.mode` 分支）。

## 三、Key mapping（逐字段）

### 输入侧（seed / 场景采样 → state）

| 来源 | 目标 key | 变换 |
|---|---|---|
| `kwags["seed"]` | `self._seed` | `setup_demo` 捕获（[:61]） |
| `self._seed` | `self.mode` | `["press","move"][seed % 2]`（[:69]，纯 seed 派生，免疫 RNG 顺序） |
| `np.random.choice([0..6])` | `self.stapler_id` | 订书机实例（[:87]） |
| `np.random.choice(8 colors)` | `self.color_name`/`self.color_value` | 垫子颜色（[:118-120]） |
| `_stable_model_ids(name)` 采样 | `self.distractor_info[i]` = `f"{name}/base{id}"` | 只从 `"stable":true` 且 mesh 存在的 id 采（[:143-147]） |

### 输出侧（`self.info` → 下游）

| 本模块输出 | 去向 | 变换 / layout |
|---|---|---|
| `info["info"]`（press）`{"{A}","{a}"}` | `generate_episode_instructions.filter_instructions` | 占位符集合 = `{A,a}` → 只匹配 press 模板（[:201-204]） |
| `info["info"]`（move）`{"{A}","{B}","{a}"}` | 同上 | 占位符集合含 `{B}` → 只匹配 move 模板（[:219-223]） |
| `{A}=f"048_stapler/base{id}"` | `replace_placeholders`：识别为 objects_description 路径 | 替换成随机物体描述（如 "the black stapler with rectangular base"） |
| `{B}=self.color_name` | 同上：普通字符串 | 字面替换（"Magenta"） |
| `{a}=str(arm_tag)` | 同上：单字母臂占位符 | 替换成 "the {left/right} arm" |
| `info["mode"]` / `info["distractors"]` | scene_info.json 顶层 | **顶层键，不进 `info["info"]`**（否则会被当占位符参数、静默丢 episode）——供 per-mode 日志（[:190-191]） |

### 数值 provenance（每个常量的出处）

| 常量 | 值 | 出处（可核对） |
|---|---|---|
| press 抓取点 | `contact_point_id=2` | 原生 `envs/press_stapler.py` 逐字复用 |
| press 判定 eps | `[0.03,0.03]` + z<0.03 | 同上 |
| move 判定 eps | `[0.02,0.02,0.01]` | 原生 `envs/move_stapler_pad.py` 逐字复用 |
| 垫子 half_size | `[0.055,0.03,0.0005]` | 同上 |
| 垫子目标姿态四元数 | `[0.707,0,0,0.707]` | 同上 |
| 订书机基准 qpos | `[0.5,0.5,0.5,0.5]`, rotate_lim `[0,π,0]` | 原生两任务 |
| 干扰物平躺 qpos | `[0.707107,0.707107,0,0]` | `envs/utils/rand_create_cluttered_actor.py` 的 glb 默认 |
| stable 过滤 | `cfg["stable"]==true` | `rand_create_cluttered_actor.get_all_cluttered_objects` 同款过滤 |
| mode 派生 | `seed % 2` | 本任务设计（见 understanding.md 变更记录 1） |

## 四、Core logic（一次 episode 数据流）

```
setup_demo(seed)                         # eval 会对同一 seed 调两次
  └─ self._seed = seed
  └─ _init_task_env_:  np.random.seed(seed)   # 播种（[base:58]）
       └─ load_actors():
            mode = ["press","move"][seed%2]           # ← 枢纽，第一行
            stapler = create_actor(048_stapler, id=rand,
                        is_static = (mode=="press"))   # press 焊死 / move 可抓
            pad = create_box(color=rand)               # 两 mode 都建
            _load_distractors():  1~2 个 stable 办公物体, glb 平躺 qpos
play_once():                              # 专家；eval 的 setup#1 也跑它产 info
  arm = left if stapler.x<0 else right
  info["mode"], info["distractors"] = ...             # 顶层日志
  if mode==press:  grasp(cp2,0.1)→close→grasp(cp2,0.02); info["info"]={A,a}
  else (move):     grasp(0.1)→lift(z=0.1)→place(align,pad); info["info"]={A,B,a}
  return info
        │
        └─(info["info"])→ generate_episode_instructions
              filter_instructions: 占位符集合精确匹配 → 路由到对应动词模板
              replace_placeholders: {A}→物体描述, {B}→颜色, {a}→"the X arm"
check_success():                          # rollout 每 step 调（[base:1657]）
  if mode==press:  夹爪-cp2 接触在 eps 内 → True（stage_success_tag latch）
  else (move):     stapler.pose≈pad.pose(eps) 且姿态一致 且双爪张开 → True
```

关键 quirk：eval 对一个 seed **两次 setup_demo**（setup#1 跑专家产指令，setup#2 policy rollout+判定），两次的 `mode` 靠 `seed%2` 保证一致，否则指令与判定错位且静默污染分数（详见 understanding.md）。

## 五、证明了什么 / 不证明什么

**证明了**：
- **接线正确**：任务可被 `envs.operate_stapler` 发现、采集 pipeline 跑通、两 mode 专家都产出成功轨迹（`evidence/*.mp4` + scene_info success）。
- **mode 枢纽 + `{B}` 路由正确**：seed→mode 对应；press 指令 0 处颜色、move 指令 100% 含颜色（`evidence/instructions_*.json`）。
- **数值复用忠实**：press/move 的专家序列与判定 eps 逐字来自对应原生任务（见 provenance 表）。
- **新干扰物池生效**：episode 用的是 stable 办公物体（cup/playingcards/glue），非旧 markpen。

**不证明**（适用范围边界）：
- **不证明干扰物视觉朝向已"自然平躺"**：数据是新池、物体均为 stable（理论应平躺），但**未逐帧肉眼核对 video 里每个物体的姿态**。需人工看 `evidence/*.mp4` 确认无竖立/悬浮。
- **不证明反例判定**：只跑了正例（oracle 正确操作→success）。**未测**"操作干扰物/错动词→check_success 应 False"（Layer B 反例）。
- **不证明 eval loop 端到端**：只跑 `collect_data`（单次 setup）。**未在真实 `eval_policy.sh` 的双 setup 流程里验证** setup#1/setup#2 的 mode 一致（逻辑上 `seed%2` 保证，但未实测）。
- **不证明 step_lim 足够 / 两 mode 专家成功率均衡**：样本仅 2 条（各 1）。move 是否总在 1000 步 fallback 内完成、两 mode pass 率是否接近 50/50，需大批量采集统计。
- **不证明模型效果**：本任务只做基准场景/判定，不涉及任何 policy 训练或评分。
