# 实现验证：任务桥接（task bridging）

> 类型：「实现链路 + 验证结果」证据底稿。逐字段讲清 task_name → 文件解析的 key mapping、指令模板 → 逐-episode 指令的数据流，并附跑通证据与边界。
> 配套：黑盒高层视角见同目录 `architecture.md`；需求/为什么见 `docs/design.md`。
> 实现提交：`9a6cec2`（"Set up RoboTwin env and validate task bridging (feature-01)"）。

---

## 一、结果（验证方式 + 判据 + 证据）

分两步验，对应两个桥接点，判据递进：

### Step 1 —— envs 桥接点（无仿真，秒级）
- **怎么验**：symlink `smoke_click_bell.py` 进 submodule `envs/` 后，模拟 `collect_data.py` 的发现方式跑：
  ```python
  import importlib
  m = importlib.import_module("envs.smoke_click_bell")
  getattr(m, "smoke_click_bell")
  ```
- **判据**：import 不报错 + `getattr` 拿到类 + 是 `Base_Task` 子类。
- **实际结果**：`OK: imported envs.smoke_click_bell -> <class 'envs.smoke_click_bell.smoke_click_bell'>`，基类 `Base_Task`。
- **证明**：文件系统层的 symlink 对 `importlib` 透明；"文件名==task_name && 类名==task_name" 规则成立。为什么这一步能脱离仿真单独验：任务发现（import+getattr）在 `collect_data.py` 里先于任何 SAPIEN 调用，纯 Python 层，不需要 GPU/渲染。

### Step 2 —— 完整链路（含 task_instruction 桥接点）
- **怎么验**：`bridge_tasks.sh` 再注入 `smoke_click_bell.json` 后，端到端跑 `python script/collect_data.py smoke_click_bell demo_smoke`（`episode_num=3`, `language_num=100`）。
- **判据**：① 仿真 `failed 0 / 3 tries`；② 每 episode 结尾 `assert TASK_ENV.check_success()` 不抛 `Collect Error`（`collect_data.py:230`）；③ 三类产物齐全；④ 生成的指令内容确实源自我们注入的模板。
- **实际结果**：
  - `simulate data episode 0/1/2 success!` → `Complete simulation, failed 0 times / 3 tries`
  - 输出 `data/smoke_click_bell/demo_smoke/`：**3 份 `data/episode*.hdf5` + 3 份 `instructions/episode*.json` + 3 份 `video/episode*.mp4`**
  - `instructions/episode0.json`：`seen=100, unseen=100`，样例 seen = `"Click the white dome bell's top center using the left arm."`（"bell/dome/click" 与 `smoke_click_bell.json` 模板语义一致）
- **证据**（`evidence/`）：
  - `smoke_click_bell_episode0.mp4` —— 渲染视频，证明仿真+渲染整条链路在**桥接进来的任务**上跑通。
  - `smoke_click_bell_episode0_instructions.json` —— 逐-episode 指令产物，证明指令生成读到了我们 symlink 的模板并展开成功。

---

## 二、与相邻模块的关系（单实例）

桥接是一层**文件系统级透明注入**，夹在"RoboTwin 的 task_name 查找"和"我们仓库的任务文件"之间：

```
[CLI: task_name] --> collect_data.py（读取方，未改） --按约定路径查找--> [注入点: symlink] --指向--> [robotwin-if/tasks/（我们维护）]
                                     |
                                     +--> SAPIEN/mplib/curobo（黑盒，接口未变）
```

- **上游（读取方）** `collect_data.py` / `generate_episode_instructions.py`：一字未改，仅按既有 `task_name` 约定查找，查到的是 symlink。对"实体 vs 软链"无感知——这是方案成立的根本。
- **下游（黑盒）** SAPIEN/mplib/curobo：桥接只决定"加载哪个类、读哪份模板"，不触碰仿真接口。

---

## 三、Key mapping（逐字段）

### 3.1 输入侧：`task_name` 字符串 → 文件解析

| 来源 | 目标 key / 路径 | 变换 | 代码锚点 |
|---|---|---|---|
| CLI arg `task_name="smoke_click_bell"` | Python 模块 `envs.smoke_click_bell` | `importlib.import_module(f"envs.{task_name}")`，经 symlink `envs/smoke_click_bell.py -> ../../../tasks/envs/smoke_click_bell.py` 命中 | `collect_data.py:23` |
| `task_name` | 环境类对象 | `getattr(envs_module, task_name)` → **强制类名 == task_name** | `collect_data.py:25` |
| `task_name` | `description/task_instruction/smoke_click_bell.json` | `os.path.join(..., f"../task_instruction/{task_name}.json")`，经 symlink `-> ../../../../tasks/task_instruction/smoke_click_bell.json` 命中 | `generate_episode_instructions.py:133` |

### 3.2 指令生成：模板 json → 逐-episode 指令

| 来源（`smoke_click_bell.json`） | 目标（`instructions/episode*.json`） | 变换 | 代码锚点 |
|---|---|---|---|
| `seen[]`（**50** 条模板，含 `<placeholder>`/`{A}`/`{a}`） | `seen[]`（**100** 条具体指令） | `filter_instructions` 按 episode 参数过滤 → 循环 `replace_placeholders` 填充至 `max_descriptions=100` | `generate_episode_instructions.py:202,212-219` |
| `unseen[]`（**10** 条模板） | `unseen[]`（**100** 条） | 同上，用 `replace_placeholders_unseen` | `:203,224-230` |
| `full_description` / `schema` / `preference` | （不进 episode json） | 仅 `seen`/`unseen` 被写出 | `save_episode_descriptions:177-178` |

### 3.3 数值 provenance（每个约定的出处）

| 约定 / 常量 | 值 | 出处（从哪核实的） |
|---|---|---|
| 文件名必须 == task_name | — | `importlib.import_module(f"envs.{task_name}")` `collect_data.py:23` + json 路径 `:133` |
| 类名必须 == task_name | — | `getattr(envs_module, task_name)` `collect_data.py:25`（getattr 的 key 直接是 task_name，非文件名） |
| `max_descriptions` | 100 | `demo_smoke.yml` `language_num: 100` → `collect_data.py:232` 传给 `gen_episode_instructions.sh` 第三参 → `generate_episode_descriptions(max_descriptions=...)` |
| 模板 seen/unseen 条数 | 50 / 10 | `smoke_click_bell.json` 逐字复制自上游 `click_bell.json`（未改内容） |
| 我们对源文件的唯一改动 | 第 8 行类名 | `tasks/envs/smoke_click_bell.py:8` `class smoke_click_bell(Base_Task)`，与 `click_bell.py` 逐行 diff 仅此一行 |

### 3.4 输出侧 layout（下游产物，非桥接产出，仅供核对链路完整）

`episode0.hdf5`（`smoke_click_bell/demo_smoke`，80 帧）：
- `joint_action/`：`left_arm(80,6)`、`right_arm(80,6)`、`left_gripper(80,)`、`right_gripper(80,)`、`vector(80,14)`
- `endpose/`：`left_endpose(80,7)`、`right_endpose(80,7)`、左右 gripper
- `observation/{front,head,left,right}_camera/`：`rgb(80,)` (bytes `|S*`, 变长 JPEG)、`intrinsic_cv(80,3,3)`、`extrinsic_cv(80,3,4)`、`cam2world_gl(80,4,4)`
- `pointcloud(80,0)`（demo_smoke 未开点云）

> 说明：这份 layout 由 RoboTwin 的数据 saver 产出，桥接不介入。列在此仅证明"桥接进来的任务能一路跑到正常落盘"。

---

## 四、Core logic（一次完整 collect 调用的数据流）

```
collect_data.sh smoke_click_bell demo_smoke 0
  └─ collect_data.py main(task_name="smoke_click_bell", task_config="demo_smoke")
       │
       ├─[桥接点1] class_decorator(task_name)                       # collect_data.py:22-29
       │     importlib.import_module("envs.smoke_click_bell")       #  :23  → symlink → tasks/envs/smoke_click_bell.py
       │     env = getattr(m, "smoke_click_bell")()                 #  :25-26 类名必须匹配
       │
       ├─ for episode in range(episode_num=3):
       │     env.play_once()  ── grasp_actor/move_by_displacement → SAPIEN/mplib/curobo（黑盒）
       │     merge_pkl_to_hdf5_video()          → data/…/episode{i}.hdf5 + video/episode{i}.mp4
       │     assert env.check_success()          #  :230  判据②
       │
       └─[桥接点2] os.system("cd description && bash gen_episode_instructions.sh \
                              smoke_click_bell demo_smoke 100")     #  :232
             └─ generate_episode_instructions.py
                  load_task_instructions("smoke_click_bell")        #  :133 → symlink → tasks/task_instruction/…json
                  for each episode: filter → replace_placeholders(×循环到100)
                  save → data/…/instructions/episode{i}.json {seen[100], unseen[100]}
```

quirk：指令生成是仿真**全部结束后**才起子进程跑（不是逐 episode），且靠 `scene_info.json`（仿真阶段落盘的 episode 参数）来做 placeholder 替换——所以两个桥接点在时序上是"先 import 跑完仿真，再读 json 生成指令"，彼此独立，这也是 Step1/Step2 能分开验的原因。

---

## 五、证明了什么 / 不证明什么（边界）

### 证明了
- **两个桥接点接线正确**：`envs/` import（Step 1）和 `task_instruction/` json read（Step 2）都命中我们 symlink 的文件，产物内容源自我们注入的模板。
- **命名对齐规则成立**：文件名 == task_name（import + json 路径）、类名 == task_name（getattr）——两条都被实测覆盖。
- **完整链路可跑通**：桥接进来的任务 3/3 episode success，`check_success` assert 通过，hdf5/instructions/video 三类产物齐全并正常落盘。
- **symlink 可移植**：用相对 `ln -srf`，repo 换位置不断（软链目标为 `../../../tasks/...`）。

### 不证明
- **不证明 smoke_click_bell 的任务判定逻辑正确**：它逐字复制自 `click_bell.py`（仅改类名），`check_success` 逻辑本身未针对性验证；本次只验"桥接后能跑通且 success"，任务逻辑等价性靠"逐字复制"保证，非本次关注点。
- **不证明桥接点3（objects_description）**：smoke 复用现有物体，未 exercise；`bridge_tasks.sh` 里已预留 glob 但为空跑。
- **不证明评测侧桥接**：只验了 `collect_data` 采集侧；`eval_policy.sh multitask` 虽用同一 `importlib` 发现机制，但未实跑（留待 feature-08 合并评测）。
- **不证明 seen/unseen 零重叠**：设计文档 Layer A 的"模板池断言无重叠"本次未做（模板 seen=50/unseen=10 是否内容隔离未断言）。
- **不证明其他 task_config / 多任务并发** 下的行为；**不证明 policy 效果**（这是脚本化数据采集，非训练/评测）。

---

## 附：一句话给 reviewer
桥接 = 两处 `ln -srf` 软链（`envs/*.py`、`description/task_instruction/*.json`），让 RoboTwin 的 `task_name` 查找透明命中 `robotwin-if/tasks/` 下我们维护的文件；已用 `smoke_click_bell`（复制自 click_bell、仅改类名）实测两点接线，3/3 episode 跑通、指令产自注入模板。要核对映射直接对 `collect_data.py:23/25/232` 和 `generate_episode_instructions.py:133`。
