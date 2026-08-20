# Operate-Stapler 问题理解（post-impl 重建）

> 实现完成后基于完整对话 + 代码 diff（主仓 commit `50c756b`）倒推重建。配套：同目录 `spec.md`（实现前 spec）、`gotchas.md`（已知隐患）。

## 当前理解

### 这个 feature 实际解决的是什么

在 RoboTwin 2.0 之上复刻 RoboTwin-IF 的 **Operate-Stapler** 任务集：把原生 `press_stapler` + `move_stapler_pad` **合并进同一个场景**（订书机 + 彩色垫 + 干扰物），用**指令里的动词**决定要做哪件事——诊断 VLA 是否真按语言控制动作（VLA→VA 退化）。垫子在两种指令下角色翻转：**press 时是干扰项，move 时是目标**。

实现落点（都在 `tasks/`，靠 `bridge_tasks.sh` symlink 进 submodule，不改 submodule 源码）：
- `tasks/envs/operate_stapler.py`：`class operate_stapler(Base_Task)`
- `tasks/task_instruction/operate_stapler.json`

核心机制是 **mode 枢纽**：`self.mode = ["press","move"][seed % 2]` 在 `load_actors` 里纯 seed 派生，一处采样、三处读取（建场景 / 专家+写 info / 判定）。指令措辞由 `info["info"]` 带不带 `{B}`（垫子颜色）**自动路由**到对应动词的模板，判定 `check_success` 按 `self.mode` 分支——指令和判定都是 mode 的下游投影，构造上永远一致。

### 边界（没做 / 明确排除）

- **不改 submodule 源码、不改 eval pipeline**（已确认零修改，靠现有多态契约）。
- **不跑 MLLM 重新生成指令模板**：直接合并两份原生 json 的 seen/unseen。
- **不训练模型**、不做 Layer C（基准区分度 baseline 对照）。
- **不做双臂**：单臂，按订书机 x 正负选臂。
- **不新建 asset**。
- **干扰物只用 stable 办公/文具物体**：明确排除无 stable id 的物体（`035_apple` 球 / `058_markpen`/`010_pen`/`083_brush`/`116_keyboard` 等），它们没有平躺静止姿态。用户想要"笔"感由 stable 的 `093_brush-pen` 顶替。
- **press mode ≠ 原生 press_stapler**：专家/判定逐字复用，但场景采用 move 的采样分布、且多了垫子+干扰物，比原生 press 更拥挤——合并同场景的必然代价，不可直接对齐原生 press 成功率。

### 验收标准

- **Layer A 集成**：`envs.operate_stapler` 可 import；bridge 后进采集/eval 调度不崩；`operate_stapler.json` per-verb `seen ∩ unseen = ∅`；press 集指令 0 处 pad 颜色、move 集每条含 pad 颜色（`{B}` 路由无泄漏）。
- **Layer B 判定**（oracle 正/反例，允许物理随机性）：
  - press：压订书机 → True；搬订书机/碰干扰物 → False（is_static=True 时错误"搬"物理上本就失败）。
  - move：订书机到对的垫子 → True；干扰物到垫子/订书机没到 → False。
- **mode 决定性**：同 seed 两次 `setup_demo` → mode 一致（`seed%2` 纯函数保证）。
- **物理真实**：干扰物自然平躺，无竖立/悬浮。

## 理解变更记录

1. **eval 是否"缺少对 mode 的判断"**（用户提问触发）：一开始把采集侧的单次 setup 心智直接套到 eval。读 `eval_policy.py` 后发现 eval 对一个 seed 会 **两次 `setup_demo`**（setup#1 跑专家产 info→指令；setup#2 policy rollout + 判定），mode 被采样两次，靠 seed 决定论保证一致——**当时以为"mode 判一次就行"，后来发现 eval 侧是两次独立采样、必须 seed 决定**，否则指令与判定错位且静默污染分数。据此把 mode 从 `np.random.choice` 改成 `seed % 2` 纯 seed 派生，免疫 RNG 消耗顺序。

2. **方向被用户纠正：不是 instruction→mode**：用户一度想让 eval"根据 instruction 反推 mode 再 setup"。**当时顺着想怎么解析指令，后来纠正为**：框架里 instruction 是从场景/info 生成的**下游产物**，没法反推；正确结构是 mode 当唯一枢纽，instruction 和 check 都是它的兄弟投影。

3. **`self.info` 初始化顺序坑**（真机报错触发）：第一次跑 `'operate_stapler' object has no attribute 'info'`。**当时以为 load_actors 里能写 self.info，后来发现** `_init_task_env_` 里 `self.info = dict()` 在 `load_actors()` **之后**才执行 → 把 `self.info["mode"]` 移到 `play_once`。

4. **干扰物 model_id 两个坑**（真机报错触发）：**当时以为 model_id 连续、按 count 采样即可，后来发现**：`071_can` id 不连续（缺 4）→ create_actor 返 None → crash；`108_block` 的 model_data 全缺 `"scale"` → config=None → `add_prohibit_area` 的 `.get` 崩。改成枚举实际存在的 id + None 兜底 + config-None 时用 pose 版 prohibit area。

5. **干扰物朝向：glb qpos 也不对**（用户反馈 pen 仍竖立）：**当时以为套 cluttered 的 glb qpos `[0.707,0.707,0,0]` 就平躺，后来发现**它对 markpen 反而把长轴转竖直。深挖 `rand_create_cluttered_actor` + `get_all_cluttered_objects` 发现：cluttered 只收 `"stable": true` 的物体，那个 qpos **只对 stable 物体成立**。

6. **markpen 能不能当干扰物**（用户质疑排除 markpen 不对）：investigate 全 submodule 发现 **RoboTwin 50 任务无一摆 markpen**（stable=false，被动态 clutter 主动排除；只在物体描述和调试查看器出现），**没有现成 qpos 可抄**。**当时以为要给 markpen 硬调 qpos/z，后来和用户定了"省事路线"**：改用 stable 的办公/文具物体池（phone 家族 + pencup + brush-pen + notebook + …），全部用 glb qpos 自然平躺、零手调；要"笔"用 stable 的 `093_brush-pen` 替 markpen。

7. **指令模板数据卫生**（合并时发现）：**当时以为直接拼接两份 json 即可，后来发现** move 池有 1 条漏 `{B}`（会带 `{A,a}` 泄漏进 press mode）、press/move 各有 intra 重复、move 有 1 条 seen/unseen 重叠。合并脚本加了：过滤无 `{B}` 的 move 模板、去重、强制 seen/unseen 不相交。

## 待确认

- [ ] **step_lim 对 move mode 是否够**：`_eval_step_limit.yml` 无 operate_stapler 项 → 吃 1000 fallback，两 mode 共用。move（抓取+搬运，步数更多）若 1000 步跑不完会被判失败。**要真机大批量采集/eval 观察 move 的步数分布确认**；不够就得单配更大值。
- [ ] **两 mode 专家成功率是否均衡**：eval 的 expert_check gate 会跳过专家失败的 seed，若 move 专家偶发失败率明显高于 press，会导致 move mode 在 eval 被系统性少采、偏离 50/50。**要统计两 mode 的专家 pass 率确认**。
- [ ] **新干扰物池是否都自然平躺**：pool 已换成 12 个 stable 办公物体（理论上都能用 glb qpos 平躺），但**用户尚未对新池重跑并肉眼核对 video**（之前竖立的是旧池 markpen）。要 `rm -rf data/operate_stapler && bash collect_data.sh operate_stapler demo_clean 0` 后看 video + `scene_info.json` 的 `distractors` 字段确认。
- [ ] **干扰物 z 落位**：静态干扰物 spawn 在默认 z=0.741，依赖 stable 物体的 mesh 原点恰好贴桌。绝大多数应 OK（stable 已验证），但个别物体可能略悬浮/穿模，要 video 核对。
- [ ] **mode 决定性在真实 eval loop 未端到端验证**：`seed%2` 纯函数逻辑上保证两次 setup mode 一致，但没在实际 `eval_policy.sh` 跑通里验证过（当前只跑了 `collect_data`）。要真机跑一次 eval 确认指令 mode 与判定 mode 对齐。
- [x] **press 指令是否泄漏 pad 颜色**：已验证——episode0(press) 200 条指令 0 处 pad/mat；episode1(move) 196/200 含 `Magenta mat`。`{B}` 路由正确。
- [x] **两 mode 能否跑通专家**：已验证——`collect_data` 中 seed0(press)/seed1(move) 均成功产出轨迹+video。

## 待优化（非阻塞，之后做）

- [ ] **干扰物向论文图对齐**：Qwen-RobotManip 的 Operate-Stapler 未开源，但论文配图里有具体候选干扰物。若能把干扰物池换成/补上图里那些物体，复刻更贴近原设计。**已知未解**：图里有一个"黄色圆角物体"暂未在物体库里定位（候选：`107_soap`/`073_rubikscube`/`095_glue`/`080_pillbottle`/`019_coaster`，待拿到论文图逐个渲染比对）。当前池是我们按"办公桌面语境 + stable 可平躺"自选的等价物，非论文原物。
