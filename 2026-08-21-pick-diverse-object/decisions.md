# Pick-Diverse-Object — 工程决策记录

> 记的是"基于当时理解做了什么工程选择、为什么"，带批判视角。跟 `understanding.md`（理解怎么变）、`architecture.md`（代码位置）不同维度。

## 关键决策点（轻量 ADR）

### D1. 指令的"颜色+名词"怎么产生
- **决策**：目标物体在指令里怎么被命名成 "the blue cup"。
- **候选**：
  - (轻) 沿用 operate_tabletop 的 `{C}`=物体路径 → native `replace_placeholders` 从 `objects_description` **随机挑一条描述**。零新代码。
  - (中·选中) `info["info"]["{A}"]` 填**字面量** `"the {color} {noun}"`（不含 `/`）→ 走 native 的"非路径即字面替换"分支。
  - (重) 自建完整 description-gen 管线 / 给每个物体写新 `objects_description` 文件。
- **选中**：字面量。因为随机描述**不保证含颜色、也不保证能区分目标**（可能挑到 "plastic mouse"），而 IF 要颜色可控可测；字面量还免掉了 `objects_description` 依赖。
- **放弃代价**：字面量绕过了 native 的描述多样性——同一个 (色,名) 每次措辞一样，多样性全靠句式模板层。对本 task 可接受（要的是受控），但如果将来想让"物体描述本身"也 seen/unseen 隔离，得回头改。

### D2. 场景采样策略（本 feature 最大的分岔，且churn 最多）
- **决策**：4 物体怎么采、目标怎么选、要不要保证颜色必要。
- **演进**：option A（强制每 episode 含同名异色+同色异名干扰 → 颜色+名词联合必要）→ 用户指出分布被压偏 → option B（均匀采 4/12，只保证目标唯一）→ 用户指出目标仍限 3 类不等概率 → **12 品类等概率目标（seed%12）+ 均匀干扰**。
- **候选**（终态视角）：
  - (轻) option A 只让 bottle/cup/shoe 当目标：代码最少、颜色 grounding 最强，但物体分布严重偏斜。
  - (中·选中) 12 等概率目标 + 均匀干扰：分布最忠实"随机采 12"。
  - (重) 12 等概率 + 强制颜色必要 + 分层报告：忠实且颜色可测，但要给 9 个物体全配可抓 + 采样加约束。
- **选中**：12 等概率均匀。**批判**：这块 churn 了三版，根因是**一开始没把"分布均匀性"和"颜色 grounding 强度"这对张力想清楚**就先实现了 option A。如果实现前先跟用户对齐"目标要不要 12 等概率、颜色要不要每次必要"，能少走两轮返工。终态的代价：颜色 grounding 被均匀采样稀释（~10-15% episode 才必要）——已记为 IF-review TODO，是自觉留的债。

### D3. 目标选择用 `seed % N` 而非 rng 抽取
- **决策**：目标怎么从 seed 派生。
- **候选**：(轻·原始) `np.random.default_rng(seed).integers(N)`；(选中) `变体[seed % N]`。
- **选中**：`seed % N`。因为 rng 首抽对**低连续 seed 聚簇**（seed 0/2/3/4/8/10 全 → shoe/red），collect_data 从 0 顺序采、小规模数据集直接偏斜。`seed % N` 在任意连续区间严格均匀，且更简单、可复现。**这不是"更重"换"更对"，是又轻又对**——原方案是隐蔽的错。借了 operate_tabletop 的 `mode=seed%3` 同款手法。

### D4. 抽共用判定 `_if_grounding.py` vs 各自内联
- **决策**：pick_diverse_object 和 operate_tabletop 的 pick 判定逻辑一样，要不要抽。
- **候选**：(轻) 各写一份 3 行判定；(中·选中) 抽一个函数、operate_tabletop 也改调它；(重) 抽 grounding-strategy 抽象基类 / 判定策略注册表。
- **选中**：抽一个纯函数。feature-03 就提示过同源。**批判**：没上到"策略类"是对的——就 3 行、一个判据，抽基类是过度设计。代价是动了已验证的 operate_tabletop（但回归 7/7 兜住了）。

### D5. 逐物体的 qpos/旋转/抓取参数怎么组织
- **决策**：12 个物体各有不同静置朝向、旋转范围、抓取参数，怎么放。
- **现状**：`REST_QPOS`（类级 dict）+ `ROTATE`（类级 dict）+ 抓取参数（play_once 里的 if/elif 链，6 个分支）+ bottle 站/躺（load_actors 里的 if 特判）。
- **候选**：(轻·现状) 分散在 2 dict + 2 处 if；(重) 统一成一个 `OBJECT_CFG = {obj: {qpos, rotate, grasp_kwargs, ...}}` 单一配置源。
- **选中**：分散。**批判**：这是本 feature 最该被质疑的点——**同一个物体的配置散在 3-4 个地方**，加新物体要改多处、容易漏。当初分散是因为它们是**增量长出来的**（先 qpos、后加旋转、再加抓取、最后加 bottle 站躺），不是设计成这样。统一成单一 per-object config 会更好维护；没做是图快 + 每处都 work 了。**留作可选重构**（低优先，功能无碍）。

## 改动量级评估

**范围**（robotwin-if 侧，submodule 零改）：
- **新增**：`pick_diverse_object.py`(~230 行)、`_if_grounding.py`(共用 helper)、`pick_diverse_object.json`、`test_instructions.py`+`test_check_success.py`、`report_pick_diverse_object.py`、`render_pick_pool_{thumbs,snapshots}.py`（2 个渲染工具）。
- **修改**：`operate_tabletop.py`（1 处小重构改调 helper）、`docs/features/04`（大幅更新）。
- 占比：**绝大部分是新增**（本就是新 task），重构极少（1 处），无删除。

**量级是否匹配问题**：
- **基本匹配，但偏重**。任务本质"采样+摆放+抓取+判定"不复杂，但 **12 个物理形态各异的物体**逼出了大量 per-object 特判（qpos/旋转/抓取/bottle 站躺/phone 专属 qpos）——这部分复杂度是**问题固有的**（真实物体就是各不相同），不是过度设计。
- **过度设计嫌疑**：reporter 的 `--eval-log` 分支是照 operate_tabletop 抄的，**本轮没跑过任何 policy eval**，属于为将来建的、暂未验证的路径。轻度投机，但跟既有 task 保持一致、成本低，可接受。
- **两个渲染工具**（thumbs/snapshots）严格说不属于"task 实现"，是为**颜色核校**临时造的——但这个核校是这个 task 的命门（颜色标签有噪），造工具是值的，且留作可复现证据。不算跑题。
- **技术债（自觉）**：D5 的分散配置；`pdo_bench.yml`（我建的 episode_num 配置，在 submodule 里未跟踪）；`/tmp/pdo_*` 探针脚本（一次性、未整理）。都不影响功能。

## 设计模式 / 工程手法

- **Template Method**（`Base_Task` 定义 setup_demo/play_once/check_success 骨架、我们 override）：不是我们的选择，是 RoboTwin 的框架约定，顺着用。
- **确定性 seed 派生**（`seed % N`）：为可复现的惯用手法，借自 operate_tabletop。**必要性**：若写最直白的 `rng.integers`，就是 D3 那个隐蔽聚簇 bug——所以这个"手法"是真必要，不是装饰。
- **共用纯函数**（`_if_grounding`）而非策略类：**克制**的一次抽象。若不抽、直接复制 3 行，问题是两处逻辑会漂移（feature-03 已提示）；但抽成类就过了。一个函数正好。
- **没有生搬硬套的模式**：play_once 的抓取分派是**直白 if/elif**，没硬套 registry/strategy——对 6 个分支这是最可读的写法。**批判反问**"完全不用任何模式会怎样？"→ 答案是"就是现在这样，挺好"，说明这里本就不需要模式；真正的问题不是"少了个模式"，而是 D5 说的**配置分散**（那是组织问题，不是模式问题）。

## 一句话

核心决策（字面量指令、共用判定、seed%N、12 等概率）都站得住；**最大的过程教训是采样策略 churn 三版**（实现前没对齐分布 vs 颜色强度的张力）；**最该改的是 per-object 配置分散**（D5，留作可选重构）。
