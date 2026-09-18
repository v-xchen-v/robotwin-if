# robotwin-if

在 [RoboTwin 2.0](https://github.com/RoboTwin-Platform/RoboTwin) 上维护六个单轴 instruction-following diagnostic tasks。RoboTwin 以 git submodule 锁定；任务通过软链注入，**不 fork、不修改上游源码**。

| 诊断轴 | Task name | 对比值 |
|---|---|---|
| Verb-Select | [`bottle_verb`](#bottle-verb) | pick / shake |
| Noun-Grounding | [`pick_diverse_object`](#pick-diverse-object) | 仅按名词从同 familiarity group 中选择目标 |
| Attribute-Select | [`attribute_select`](#attribute-select) | color / decal / shape / size |
| Arm-Select | [`arm_select`](#arm-select) | left / right |
| Sequence | [`stack_sequence`](#stack-sequence) | 六种 bottom-to-top 顺序 |
| Spatial-Direction | [`place_relative`](#place-relative) | left / right / on top |

Grasp-Approach 已于 2026-09-15 暂时下线；实现、配置、测试和 probe 归档到 [`bak/grasp_cube_approach/`](bak/grasp_cube_approach/README.md)。当前默认生成、安装与评测均只包含以上六项。

唯一正式维护的 IF inventory 是 [`eval_cfg/if_tasks.yml`](eval_cfg/if_tasks.yml)。其他 env/JSON 可以为历史或实验目的留在仓库中，但只要没有列入该文件，就不属于 active suite。Manifest membership 与 production readiness 分开管理：例如 `pick_diverse_object` 属于上述六项，其已锁定的四类 Unseen production pool 仍由独立测试 gate 持续约束。

本仓库维护 benchmark task（场景、干扰物、指令模板、成功判定与评测语义），并在 [`policies/`](policies/README.md) 中维护 X-VLA、LingBot-VA 等开源策略的独立推理环境与适配代码，**不在本仓库训练模型**。模型服务与 RoboTwin 仿真使用不同的 Conda 环境；也可由外部 CogACT/X-VLA 集成提供推理。

**当前结果包：[`result/robotwin-if-arm-only-v2-20blocks/`](result/robotwin-if-arm-only-v2-20blocks/README.md)** ·
[HTML 报表](result/robotwin-if-arm-only-v2-20blocks/results.html) ·
[逐回合 CSV](result/robotwin-if-arm-only-v2-20blocks/episodes.csv) · [历史结果](result/README.md)。

当前 [RoboTwin-IF Arm-only-v2 taskset](seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md)
已完成六个 policies × 六任务 × 每任务 20 blocks：460 回合/policy，共 2760 回合、720 blocks。
本轮按 `target-arm-only-lift-v2` 重跑 Arm-Select 240 回合；其余五任务逐字节复用 Attribute-v2 的 2520 回合。
保留 cube-v3 场景、Attribute target-only-lift-v2、Bottle v6 terminal 和 Spatial 三模式。
详见[Arm 成功判据](docs/arm-select-target-arm-only.md)和[完整结果](result/robotwin-if-arm-only-v2-20blocks/README.md)。
Seed 清单的当前入口与使用方法见 [seed-manifests](seed-manifests/README.md)；12 份旧版实体已移入 [历史清单归档](seed-manifests-archive/README.md)，旧路径保留兼容软链接。
历史七任务 [IF-Ext v2 wide 20-block 结果](result/if-ext-v2-wide-20blocks/README.md)保留六个 policies × 七任务的 3240 回合及其校验证据。

<a id="policy-results"></a>

## 六个 Policies 的评测结果

2026-09-18 05:26 UTC 完成并校验：**2760/2760 回合、720/720 blocks**。
Arm-Select 重新运行 **240 回合**；其余五任务的 **2520 回合**及其统计与[上一版 Attribute-v2](result/robotwin-if-attribute-v2-20blocks/README.md)一致。
六份 seed manifest、checkpoint 和推理参数沿用上一版，全部新回合初始观测逐数组匹配。
4 次推理前 oracle 初始化失败用原 seed 恢复；完成的 policy 成功和失败没有重跑。
VLAct 使用 `StarVLA/VLAct_Qwen3OFT_Robotwin_all_Finetune`（All 100K）。

**微调数据差异：** X-VLA 使用在 RoboTwin **clean** 数据上微调的 checkpoint，其余五个 policies 使用在
**clean + randomized** 数据上微调的 checkpoint。由于 X-VLA 目前没有开源的 clean + randomized checkpoint，
本次比较采用其公开的 clean checkpoint。因此，各模型的微调数据设置并不完全一致，解读结果时需考虑这一差异。

任务列为**成功数 / 已评测回合数**，成功与已完成的 policy failure 均计入分母。
**Overall (%) = 六个任务成功率的等权平均**，每个任务内部对 modes 等权；它不等于把 460 个回合合并后的成功率。

| Policy | Verb | Noun | Attribute v2 | Arm cube-v3 / only-v2 | Sequence | Spatial | Overall (%) | 完成回合 | 完成 blocks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| [X-VLA](policies/xvla/README.md) | 20/40 | 15/40 | 73/160 | 5/40 | 0/120 | 6/60 | 25.9 | 460/460 | 120/120 |
| [LingBot-VA](policies/lingbot_va/README.md) | 20/40 | 30/40 | 108/160 | 37/40 | 17/120 | 26/60 | 57.1 | 460/460 | 120/120 |
| [LingBot-VLA](policies/lingbot_vla/README.md) | 20/40 | 13/40 | 77/160 | 18/40 | 14/120 | 3/60 | 32.0 | 460/460 | 120/120 |
| [VLAct All](policies/vlact/README.md) | 36/40 | 28/40 | 108/160 | 29/40 | 15/120 | 19/60 | 57.4 | 460/460 | 120/120 |
| [DM05](policies/dm05/README.md) | 40/40 | 25/40 | 88/160 | 25/40 | 9/120 | 20/60 | 53.5 | 460/460 | 120/120 |
| [Hy-VLA](policies/hy_vla/README.md) | 20/40 | 11/40 | 83/160 | 17/40 | 15/120 | 7/60 | 32.7 | 460/460 | 120/120 |

**Attribute-Select 判定修正（2026-09-17）：** 新规则要求目标当前抬升超过 5 cm，且干扰物在整回合中从未越过该阈值。
先抓错再抓对仍失败。上表 Attribute/Overall 已使用新判据重新评测；旧结果包保持原始计数。
新旧差异包含判据变化及重新推理的影响。见[修正与回放证据](docs/attribute-select-target-only.md)。

**待复核记录：** Hy-VLA 的 `pick_diverse_object` seed `100052`（coffee box）被用户指出视频表现失败，
其归档自动判定仍为成功；该片段已从 README 演示中撤下。上表保持归档计数，尚未据此人工修订分数，
详见 [例子替换记录](docs/assets/task-demos/README.md)。

<details>
<summary>展开各任务、各模式的成功个数</summary>

下表仍为成功数 / 已评测回合数，Avg. 为任务成功率（%）。Attribute 按子轴合并两个 target values，
每个子轴共 40 回合；其余每个 mode 共 20 回合。Sequence 的 R/G/B 表示从底层到顶层的颜色顺序，
Spatial 的 Top 表示 on_top。每个 policy 的每项任务均已完成 20/20 blocks。

### Verb — `bottle_verb`

| Policy | Pick | Shake | Avg. (%) |
|---|---:|---:|---:|
| X-VLA | 0/20 | 20/20 | 50.0 |
| LingBot-VA | 0/20 | 20/20 | 50.0 |
| LingBot-VLA | 0/20 | 20/20 | 50.0 |
| VLAct All | 16/20 | 20/20 | 90.0 |
| DM05 | 20/20 | 20/20 | 100.0 |
| Hy-VLA | 0/20 | 20/20 | 50.0 |

### Noun — `pick_diverse_object`

| Policy | Seen | Unseen | Avg. (%) |
|---|---:|---:|---:|
| X-VLA | 7/20 | 8/20 | 37.5 |
| LingBot-VA | 14/20 | 16/20 | 75.0 |
| LingBot-VLA | 10/20 | 3/20 | 32.5 |
| VLAct All | 16/20 | 12/20 | 70.0 |
| DM05 | 18/20 | 7/20 | 62.5 |
| Hy-VLA | 7/20 | 4/20 | 27.5 |

### Attribute v2 — `attribute_select`

| Policy | Color | Decal | Shape | Size | Avg. (%) |
|---|---:|---:|---:|---:|---:|
| X-VLA | 16/40 | 20/40 | 17/40 | 20/40 | 45.6 |
| LingBot-VA | 39/40 | 21/40 | 28/40 | 20/40 | 67.5 |
| LingBot-VLA | 20/40 | 21/40 | 16/40 | 20/40 | 48.1 |
| VLAct All | 34/40 | 25/40 | 29/40 | 20/40 | 67.5 |
| DM05 | 20/40 | 20/40 | 28/40 | 20/40 | 55.0 |
| Hy-VLA | 20/40 | 21/40 | 22/40 | 20/40 | 51.9 |

### Arm cube-v3 — `arm_select`

本表使用 5 cm cube；场景平移、旋转与配对验证见 [cube-v3 环境说明](docs/recon/arm-select-cube-v3.md)。旧长柱代码和 240 回合结果已[备份](bak/arm_select-long-v2-20260916/README.md)。

| Policy | Left | Right | Avg. (%) |
|---|---:|---:|---:|
| X-VLA | 2/20 | 3/20 | 12.5 |
| LingBot-VA | 18/20 | 19/20 | 92.5 |
| LingBot-VLA | 7/20 | 11/20 | 45.0 |
| VLAct All | 16/20 | 13/20 | 72.5 |
| DM05 | 9/20 | 16/20 | 62.5 |
| Hy-VLA | 6/20 | 11/20 | 42.5 |

### Sequence — `stack_sequence`

| Policy | RGB | RBG | GRB | GBR | BRG | BGR | Avg. (%) |
|---|---:|---:|---:|---:|---:|---:|---:|
| X-VLA | 0/20 | 0/20 | 0/20 | 0/20 | 0/20 | 0/20 | 0.0 |
| LingBot-VA | 17/20 | 0/20 | 0/20 | 0/20 | 0/20 | 0/20 | 14.2 |
| LingBot-VLA | 14/20 | 0/20 | 0/20 | 0/20 | 0/20 | 0/20 | 11.7 |
| VLAct All | 10/20 | 0/20 | 1/20 | 2/20 | 0/20 | 2/20 | 12.5 |
| DM05 | 9/20 | 0/20 | 0/20 | 0/20 | 0/20 | 0/20 | 7.5 |
| Hy-VLA | 15/20 | 0/20 | 0/20 | 0/20 | 0/20 | 0/20 | 12.5 |

### Spatial — `place_relative`

Spatial 从五模式收缩为 **left/right/on_top**；这是视频复核后的评测范围调整，分数变化不表示模型性能提升。front/back 原始自动结果与视频索引见 [决策与证据](docs/place-relative-spatial3.md)，旧五模式结果完整保留。


| Policy | Left | Right | Top | Avg. (%) |
|---|---:|---:|---:|---:|
| X-VLA | 4/20 | 2/20 | 0/20 | 10.0 |
| LingBot-VA | 12/20 | 7/20 | 7/20 | 43.3 |
| LingBot-VLA | 1/20 | 2/20 | 0/20 | 5.0 |
| VLAct All | 11/20 | 7/20 | 1/20 | 31.7 |
| DM05 | 12/20 | 8/20 | 0/20 | 33.3 |
| Hy-VLA | 2/20 | 5/20 | 0/20 | 11.7 |

</details>

数据来源：[HTML 报表](result/robotwin-if-arm-only-v2-20blocks/results.html) ·
[完整结果表](result/robotwin-if-arm-only-v2-20blocks/results.md) ·
[分模式 CSV](result/robotwin-if-arm-only-v2-20blocks/results.csv) ·
[逐回合 CSV](result/robotwin-if-arm-only-v2-20blocks/episodes.csv) ·
[结果 JSON](result/robotwin-if-arm-only-v2-20blocks/results.json) ·
[Checkpoint 版本](result/robotwin-if-arm-only-v2-20blocks/checkpoints.json) ·
[校验证据](result/robotwin-if-arm-only-v2-20blocks/validation.json)。

## 六个任务与视频

每项任务聚焦一种指令差异：做什么动作、抓哪个物体、按什么属性选择、用哪只手、按什么顺序、放在哪个方向。
下方动态预览可点击打开 MP4；素材随仓库提供。视频选自正式评测中的成功回合，用于展示任务行为，
整体表现见 [完整结果](result/robotwin-if-arm-only-v2-20blocks/README.md)。原始指令、seed、policy 和视频处理说明见 [素材来源](docs/assets/task-demos/README.md)。

<a id="bottle-verb"></a>

### 1. Bottle-Verb：根据动词选择动作

面对同一瓶子和初始场景，执行 **pick（拿起）** 或 **shake（摇动）**。
pick 跑满 700 个动作后判定：允许拿起后平移，末尾保持抬升至少 3 cm、连续 3 秒姿态稳定；回合中明显旋转摇晃不能算 pick。
详见 [成功判定与历史结果说明](docs/bottle-verb-pick-hold.md)。
下例左右分别为 pick / shake；一个 block 包含两个回合。

[![Bottle-Verb：同一场景中的拿起与摇动](docs/assets/task-demos/bottle_verb.gif)](docs/assets/task-demos/bottle_verb.mp4)

[观看 MP4](docs/assets/task-demos/bottle_verb.mp4) · 示例 policy：Hy-VLA（旧判定版本的演示，不作为 v6 成功证据）。

<a id="pick-diverse-object"></a>

### 2. Pick-Diverse-Object：根据名词找到目标

桌上放置四个不同类别的物体，机器人需要根据指令中的**物体名词**选中并抓起目标。
**Seen / Unseen** 分别使用熟悉与未见物体池；一个 block 包含两个独立场景，每个场景内的四个物体属于同一 familiarity group。
下例分别抓取 mug 与 wooden mallet。

[![Pick-Diverse-Object：Seen 场景抓取 mug，Unseen 场景抓取 wooden mallet](docs/assets/task-demos/pick_diverse_object.gif)](docs/assets/task-demos/pick_diverse_object.mp4)

[观看 MP4](docs/assets/task-demos/pick_diverse_object.mp4) · 左：DM05（Seen mug）；右：Hy-VLA（Unseen wooden mallet）。

<a id="attribute-select"></a>

### 3. Attribute-Select：根据视觉属性选择目标

在两个物体中按指定属性选择并抓起目标：**颜色**（red / blue）、**图案**（cat / dog）、
**形状**（block / bar）或**大小**（big / small）。同一属性的两个指令共享场景、切换目标；
一个 block 包含四组对比、共八个回合。下例依次展示 red、cat、long bar、small 四类属性指令。
当前[成功判据](docs/attribute-select-target-only.md)要求目标抬升超过 5 cm，且干扰物在本回合从未越过该阈值；
先抓错再抓对、或同时抓起两个物体，均判失败。下方演示来自旧判据归档。

[![Attribute-Select：颜色、图案、形状和大小四种属性的抓取示例](docs/assets/task-demos/attribute_select.gif)](docs/assets/task-demos/attribute_select.mp4)

[观看 MP4](docs/assets/task-demos/attribute_select.mp4) · 示例 policy：Hy-VLA。

<a id="arm-select"></a>

### 4. Arm-Select：使用指定的机械臂

对同一目标方块，分别要求用**左臂 / 右臂**抓起；用错机械臂即使抬起方块也不算成功。
2026-09-18 已加入[错误手臂历史判据](docs/arm-select-target-arm-only.md)：先用错误臂拿起、再换指定臂仍失败。
当前报表中的 Arm/Overall 已按该新规则重跑；历史结果包保留原始判据和计数。
当前 taskset 的 [cube-v3 配置](docs/recon/arm-select-cube-v3.md) 使用 5 cm cube，在双臂共用区域内随机平移和绕竖直轴旋转。
不同 blocks 改变物体的位置和朝向，同一 block 的两个回合共享布局。
下例左右分别为 left arm / right arm。

[![Arm-Select cube-v3：同一方块分别由指定的左臂和右臂抓起](docs/assets/task-demos/arm_select_cube_v3.gif)](docs/assets/task-demos/arm_select_cube_v3.mp4)

[观看 MP4](docs/assets/task-demos/arm_select_cube_v3.mp4) · 示例 policy：LingBot-VA · seeds 500000/500001 · [旧 v2 演示](docs/assets/task-demos/arm_select.mp4)。

<a id="stack-sequence"></a>

### 5. Stack-Sequence：按照指定顺序堆叠

将红、绿、蓝三个方块按指令指定的**自下而上顺序**堆成三层。
同一场景对应六种排列，一个 block 包含六个回合；仅堆成塔、颜色顺序错误不算成功。
下例分别为 red → green → blue 和 green → blue → red（箭头均表示从底层到顶层）。

[![Stack-Sequence：红绿蓝与绿蓝红两种自下而上的堆叠顺序](docs/assets/task-demos/stack_sequence.gif)](docs/assets/task-demos/stack_sequence.mp4)

[观看 MP4](docs/assets/task-demos/stack_sequence.mp4) · 示例 policy：VLAct All · 存档视频 3× 播放。

<a id="place-relative"></a>

### 6. Place-Relative：理解相对空间方向

将物体 A 放到参考物体 B 的 **left / right / on top**，场景中另有一个干扰物。
同一布局对应三种方向，一个 block 包含三个回合，检验目标放置关系是否符合指令。
下例将绿色 toycar 分别放到红色 tea-box 的左侧和顶部。

[![Place-Relative：将同一绿色 toycar 放到红色 tea-box 左侧或顶部](docs/assets/task-demos/place_relative.gif)](docs/assets/task-demos/place_relative.mp4)

[观看 MP4](docs/assets/task-demos/place_relative.mp4) · 示例 policy：VLAct All · 存档视频 1.5× 播放。

## 分支交付内容

| 交付项 | 入口 |
|---|---|
| 六个 policy 的 inference code / setup / eval adapter | [`policies/`](policies/README.md) |
| 统一 bash 评测入口（单个模型服务 + 串行 sim） | [`scripts/eval.sh`](scripts/eval.sh) |
| 视频人工复核、Success/Fail 标注与判定分歧导出 | [`tools/policy-video-review/`](tools/policy-video-review/README.md) |
| 六任务 × 20 blocks：flat seeds 与显式 seed/mode JSON、CSV | [`seed-manifests/robotwin-if-arm-only-v2-20-per-mode/`](seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md) |
| 已完成结果、逐回合 CSV、checkpoint 与校验证据 | [`result/robotwin-if-arm-only-v2-20blocks/`](result/robotwin-if-arm-only-v2-20blocks/README.md) |

接收方从 [分支交付说明](docs/branch-delivery.md) 开始；运行新评测不依赖本机 `/Data` 下的旧运行目录。

人工复核原始评测视频：

```bash
python tools/policy-video-review/server.py \
  --run-dir outputs/policy-eval/robotwin-if-arm-only-v2-20blocks-001
```

打开 `http://127.0.0.1:8893/`，按 policy/task 筛选、逐帧查看和标注，导出自动判定与人工判定的分歧。
人工标签独立保存，原始结果保持不变；远程机器需转发该端口，详见 [使用说明](tools/policy-video-review/README.md)。

## 设计原则：零改上游

任务源码维护在 `tasks/` 下；安全 installer 只把 canonical IF 六项及其四个 helper 软链到 RoboTwin：

- `envs/<task_name>.py`（六项）；
- `envs/_if_grounding.py`、`_if_relative.py`、`_pick_diverse_object_pool.py`、`_if_eval.py`；
- `description/task_instruction/<task_name>.json`（六项）。

历史/实验 env 即使仍在 `tasks/` 中也不会被安装；当前六项不依赖额外 object-description bridge。Installer 不修改 RoboTwin tracked 文件，尤其不会 merge 或替换 `task_config/_eval_step_limit.yml`。

Bridge 之后，RoboTwin 的 collect/eval harness 可像发现 raw task 一样通过 task name 加载新增任务。Bridge 只负责 runtime discovery；它不负责选择 balanced seeds 或计算 per-mode IF 指标。

## 用法

### 1. 环境搭建

```bash
bash setup_robotwin.sh [--assets_cache <本地资产缓存目录>]
```

安装 RoboTwin 2.0 仿真环境（SAPIEN/CUDA/curobo 等）。详见 [`docs/features/01-环境搭建.md`](docs/features/01-环境搭建.md)。

### 2. 桥接 / 解绑任务

#### 模式 A：锁定的 nested runtime（推荐）

```bash
# 默认 target = third_party/robotwin
bash scripts/bridge_tasks.sh --dry-run
bash scripts/bridge_tasks.sh
bash scripts/bridge_tasks.sh --check

# 卸载前先查看计划；真正卸载使用同一命令但去掉 --dry-run
bash scripts/unbridge_tasks.sh --dry-run
```

Nested checkout 固定在已验证的 RoboTwin commit `0aeea2d669c0f8516f4d5785f0aa33ba812c14b4`，适合 benchmark release、CI 和 CogACT/X-VLA 评测。Fresh clone、new worktree 或新的 CI job 都要重新 bridge；软链和 target-side `.robotwin-if-bridge.json` 是 workspace installation state，不属于 RoboTwin submodule commit。

#### 模式 B：接入外部 repo 已有的 RoboTwin

```bash
bash scripts/bridge_tasks.sh --robotwin-dir /path/to/external/RoboTwin --dry-run
bash scripts/bridge_tasks.sh --robotwin-dir /path/to/external/RoboTwin
bash scripts/bridge_tasks.sh --robotwin-dir /path/to/external/RoboTwin --check
```

Target 解析优先级为 `--robotwin-dir`、`ROBOTWIN_DIR`、默认 nested checkout。外部 checkout 的 commit 若不是上述 locked commit、没有可读且 target-root 精确匹配的 git metadata，或 compatibility contract files 有本地修改，默认拒绝；只有人工确认后才显式放行：

```bash
bash scripts/bridge_tasks.sh \
  --robotwin-dir /path/to/external/RoboTwin \
  --allow-compatible-commit

# mismatch checkout 的后续 check 也必须显式声明同一 opt-in
bash scripts/bridge_tasks.sh \
  --robotwin-dir /path/to/external/RoboTwin \
  --allow-compatible-commit --check
```

即使显式放行，Base_Task、instruction generator、`envs.utils` 的实际 package exports 与目录布局等静态 API contract 仍必须全部通过。Ownership manifest 记录实际 target/source commits、`source_dirty`、16 个 linked sources 的 deterministic `source_digest`、`target_contract_dirty` 和每个链接的精确 raw target；它不会把 dirty source 错写成可由 commit 单独复现，`--check` 也能发现 dirty source 内容再次变化。

Bridge 在写入前对所有 destination 做完整 preflight：正确旧链接会被 adopt，missing link 才新增，foreign/dangling symlink、真实文件或目录都会使整次安装在 mutation 前失败；不提供 `--force`。重跑 bridge 会安全清理 manifest-owned stale links 和仍指向本 source 的旧 inactive glob links。Unbridge 以 manifest 为准，因此 source 文件重命名/删除后仍可清理；被外部修改的 destination 一律 `skip-modified` 并保留 ownership 记录，绝不误删。Bridge/check/unbridge 通过 target-directory lock 串行化完整 transaction，dry-run 不新增 lock 文件。

### 3. 采集 oracle 专家演示

锁定版本的 RoboTwin collect 是单任务入口。先按[分支交付说明](docs/branch-delivery.md)
安装 `demo_clean_arm_select_v3.yml`，再遍历六项 IF manifest；Arm-Select 使用 cube-v3 配置：

```bash
bash scripts/bridge_tasks.sh
cd third_party/robotwin

for t in $(python3 -c "import yaml; print(' '.join(yaml.safe_load(open('../../eval_cfg/if_tasks.yml'))['tasks']))"); do
  task_config=demo_clean
  if [[ "$t" == arm_select ]]; then
    task_config=demo_clean_arm_select_v3
  fi
  bash collect_data.sh "$t" "$task_config" 0   # <task> <config> <gpu_id>
done
```

可执行清单：

- [`eval_cfg/if_tasks.yml`](eval_cfg/if_tasks.yml)：维护中的 IF 六项；
- [`eval_cfg/all_tasks_plus_if.yml`](eval_cfg/all_tasks_plus_if.yml)：锁定的 native 50 + 同一 IF 六项，共 56 项。

每个任务 collect 结束时会调用 RoboTwin 原生指令生成管线，无需单独执行 instruction generator。

### 4. Policy 评测

以下为初次接入时的 smoke 验证记录，Arm-Select 使用当时的长柱环境。
当前 Attribute-v2 的六个 policies、20-block 正式成绩见[评测结果](#policy-results)。

本仓库维护的策略入口见 [`policies/README.md`](policies/README.md)。X-VLA 环境安装命令为 `bash policies/xvla/setup_env.sh`，服务启动与最小评测命令见其 [README](policies/xvla/README.md)。初次闭环验证已完成：raw `click_bell` 1/1 成功，IF `arm_select` 的一个完整左右臂 block 为 1/2（左成功、右达到动作上限），结果属于 smoke 验证。每个策略先验证一个 raw RoboTwin task，再验证一个 IF task。

第二个策略 [LingBot-VA](policies/lingbot_va/README.md) 也已完成同一验证顺序：raw `click_bell` 1/1，IF `arm_select` 的完整左右臂 block 为 2/2。使用 `bash policies/lingbot_va/setup_env.sh` 安装独立环境；checkpoint 下载、服务和评测命令见该策略 README。两种策略均采用统一的 episode 输出格式；这些结果只用于初次接入验证。

[LingBot-VLA 4B](policies/lingbot_vla/README.md) 的 `robbyant/lingbot-vla-4b-posttrain-robotwin` 接入位于 `policies/lingbot_vla/`，使用独立环境和 WebSocket 端口 8012，输出 14D 绝对关节动作。真实 checkpoint 的 raw `click_bell` 1/1 成功；IF `arm_select` 完整左右臂 block 为 0/2，均达到动作上限，IF 成功验收尚未通过。安装、下载、启动及验证证据见该策略 README。

[VLAct Qwen3OFT](policies/vlact/README.md) 的 `StarVLA/VLAct_Qwen3OFT_Robotwin_Finetune` 接入位于 `policies/vlact/`，使用独立环境 `robotwin-if-vlact` 和 WebSocket 端口 8013。输入三路 RGB 与指令，按训练配置 `robotwin_wrap_32` 解码并重排 32 步、14D 绝对关节动作。真实 checkpoint 的 raw `click_bell` 1/1 成功；IF `arm_select` 完整左右臂 block 为 1/2（左达到动作上限、右成功）。安装、下载、启动和验证证据见该策略 README。

[DM05](policies/dm05/README.md) 的 `Dexmal/DM05-robotwin2` 接入位于 `policies/dm05/`，使用独立环境 `/Data/robotwin-if/envs/robotwin-if-dm05` 和 HTTP 端口 8014。输入三路 RGB、实测关节状态与指令，输出 50 步、14D 绝对关节动作。真实 checkpoint 的 raw `click_bell` 1/1 成功；IF `arm_select` 完整左右臂 block 为 2/2。安装、下载、启动、上游 CUDA Graph 回退说明和验证证据见该策略 README。

[Hy-VLA](policies/hy_vla/README.md) 的 `tencent/Hy-Embodied-0.5-VLA-RoboTwin` 接入位于 `policies/hy_vla/`，使用独立环境 `/Data/robotwin-if/envs/robotwin-if-hy-vla` 和 WebSocket 端口 8015。输入三路 RGB、六帧历史、实测末端状态与指令，按官方相对/绝对动作混合解码得到 20 步、16D 末端目标，每 7 步重规划。真实 checkpoint 的 raw `click_bell` 1/1 成功；IF `arm_select` 完整左右臂 block 为 0/2，均达到 400 步上限，IF 成功验收尚未通过。安装、下载、启动和验证证据见该策略 README。

RoboTwin 没有统一的顶层 eval 命令；每个 policy 使用自己的 `eval.sh`，参数签名也可能不同。常见入口为：

```bash
cd third_party/robotwin/policy/<PolicyName>
bash eval.sh <task_name> demo_randomized <ckpt_setting> <expert_data_num> <seed> <gpu_id>
```

- 把 `task_name` 换成 task inventory 中任一新增任务即可完成 runtime 加载；checkpoint 必须具备相应行为 repertoire，结果才有诊断意义。
- 各 policy 的 `deploy_policy.yml` 通常以 `instruction_type: unseen` 做正式 IF 评测；`seen` 只用于 sanity check。
- 原生 eval 会跳过 oracle-invalid candidate seeds，适合 smoke test，但不能保证每个 mode denominator 均衡。

六项 task 在 eval mode 使用集中维护的 policy-action budget（collect 不受影响）：

| Task | `step_lim` | Native structural analog |
|---|---:|---|
| `bottle_verb` | 700 | `shake_bottle`（取最长 shake branch） |
| `pick_diverse_object` | 400 | single grasp/lift |
| `attribute_select` | 400 | single grasp/lift |
| `arm_select` | 400 | single grasp/lift |
| `stack_sequence` | 1200 | `stack_blocks_three` |
| `place_relative` | 400 | `place_a2b_left` |

Mapping 位于 `tasks/envs/_if_eval.py`，task 在 `_init_task_env_` 返回后覆盖 eval limit，因此不修改 upstream config。Locked Base_Task 对未知 task 可能先打印 fallback-to-1000 提示，但 policy rollout 实际读取的是随后覆盖的固定值。现有 oracle trajectory 最大 recorded frames（按表中 task 顺序）为 255/103/89/89/479/163，只能支持相对复杂度判断；`step_lim` 统计 policy action calls，仍需在后续 CogACT rollout 中监测是否有 episode 撞到 limit。

正式 IF 结果不能任意跳过单个 seed。应先按 task 的完整 balance block 验证并固化 seed manifest，再让所有 policy 重放同一批 episodes。这里的 block 不一定是同一物理场景：`attribute_select` 的 8-seed block 包含四个 same-scene pair，`pick_diverse_object` 的 seen/unseen block 则是两个独立 familiarity scenes。具体 contract 见 [`eval_cfg/README.md`](eval_cfg/README.md)。

### 5. 生成与消费 balanced seed manifest

完整的生成、验证、resume 与外部 evaluator 消费流程见 [`docs/seed-manifest-usage.md`](docs/seed-manifest-usage.md)。

`eval_cfg/if_tasks.yml` 回答“运行哪些 task”；seed manifest 回答“每个 task 运行哪些 exact episode seeds”。面向外部 evaluator 的 JSON 故意保持扁平：

```json
{
  "schema_version": 1,
  "task": "arm_select",
  "task_config": "demo_clean",
  "seeds": [100000, 100001, 100002, 100003]
}
```

先完成 bridge，再在 RoboTwin/SAPIEN 环境中生成 oracle-qualified blocks：

```bash
python tools/generate_if_seed_manifest.py \
  --all \
  --task-config demo_clean \
  --accepted-blocks 2 \
  --max-candidate-blocks 20 \
  --output-dir /path/to/output
```

生成器逐个 exact seed 调用 `setup_demo`、`play_once` 与 `check_success`；任一成员失败就拒绝整个 block，不使用 `seed + 1` 替换失败成员。`--resume` 从逐 block 原子 checkpoint 续跑，并要求 task/config/count、contract、target/source commit、linked-source digest 与实际 task-config YAML SHA-256 全部一致；`--overwrite` 与 `--resume` 互斥。外部 RoboTwin 的 target 解析与 compatible-commit opt-in 和 bridge 相同。

每个 `<task>.json` 旁边的 `<task>.generation.json` 是可忽略的审计 sidecar，记录 accepted/rejected blocks、逐 seed oracle/mode 结果、source/target/config provenance、耗时和 manifest SHA-256。可在不安装 SAPIEN 的环境独立检查：

```bash
python tools/validate_if_seed_manifest.py --require-evidence /path/to/output
```

外部 policy evaluator 只需读取 `task`、`task_config`、`seeds`，并按列表逐 episode 运行。显式提供 manifest 后，某个 seed 无法运行必须判定整次评测无效；不得静默跳过、递增、补抽或回退到原生动态模式。未提供 manifest 时，RoboTwin 原生动态 seed/skip 行为保持不变，仍可用于 raw task 和 smoke test。本阶段只实现 seed pipeline；policy result JSONL、`eval_signals()`、per-mode success/gap reporter 与 CogACT replay wrapper 仍属后续工作。

### 6. 测试

测试采用可直接执行的 Python 脚本。常见入口：

```bash
python tests/test_task_bridge.py
python tests/test_eval_step_limits.py
python tests/test_task_manifests.py
python -m unittest discover -s tests -p 'test_if_seed_*.py' -v
python tests/<task>/test_instructions.py
python tests/<task>/test_check_success.py
```

不同任务的 instruction test 可能按职责命名为 `test_instruction_routing.py` 等；以各 task 测试目录为准。多数 Layer-A routing 与静态成功判定测试无需启动仿真。

## 仓库结构

```text
tasks/                  任务 env、instruction JSON 与对象描述；bridge 的 source of truth
policies/               每个开源策略的独立推理环境、说明与后续 adapter
if_benchmark/           simulator-free seed contracts、manifest 与 generation state
eval_cfg/               canonical IF 六项与 native 50 + IF 六项 task inventory
scripts/                thin shell entrypoints + stdlib ownership installer
tests/                  inventory、seed pipeline、routing 与 success invariants
tools/                  seed generator/validator、probe、report 与可视化工具
bak/                    暂时下线任务的源码、配置与专用材料
docs/                   设计及逐任务实现记录
notes/                  实验、评审与集成证据
third_party/robotwin/    锁定的 RoboTwin 2.0 submodule
third_party/xvla/        setup 获取的固定版本 X-VLA 源码（Git 忽略）
```

## 当前状态

当前维护六项任务；inventory、bridge 与 seed contracts 由静态检查保持一致。
Grasp-Approach 已归档，不参与默认安装、生成、评测或当前 Overall。
当前 Arm-only-v2 taskset 已完成 2760 回合、720 blocks；Arm 重跑 240 回合，其他五任务复用 Attribute-v2 的 2520 回合。
当前入口见 [正式评测说明](docs/formal-policy-evaluation.md) 和 [结果目录](result/README.md)。

任务执行使用固定 manifest，成功和 policy failure 都保留，基础设施错误不替换 seed。
正式 runner 保留场景/结果校验和 GPU 安全停止；当前 Arm 重评由 03 推理、04 最多三路仿真，见[运行说明](docs/arm-select-target-only-v2-evaluation.md)。
历史七任务 release、原始输出与源码快照继续保留，供追溯原评测范围。
