# Operate-Stapler 工程决策记录（decisions）

> 记的是"基于当时理解做了什么工程选择、为什么"，带批判视角。理解本身怎么变的见 `understanding.md`；隐患见 `gotchas.md`。

## 一、关键决策点（轻量 ADR）

### D1. mode 怎么定：`seed % 2` 纯派生
- **为什么要决策**：eval 对一个 seed 会两次 `setup_demo`（专家产指令 / policy 判定），两次必须是同一个 mode。
- **候选**：
  - （更轻）`np.random.choice(["press","move"])`——最直觉，一行。
  - （选中）`self.mode = ["press","move"][seed % 2]`——纯 seed 函数。
  - （更重）把 mode 写进 sidecar 文件、第二次 setup 读回；或独立的 mode 配置/registry。
- **选择理由**：`np.random.choice` 看似最轻，但它依赖 RNG 状态，两次 setup 之间任何采样顺序变化都会让 mode 漂移 → 指令与判定错位、**静默污染分数**。`seed%2` 是**能保证正确的最轻方案**。sidecar/registry 是过度设计——徒增一份需要同步的状态。
- **放弃的代价 / 残留成本**：mode 与 seed 奇偶强绑定，连续 seed 严格交替 press/move。对分析无害（seed 就是 episode 序号），但任何"连续 seed 段"的统计都带这个结构。可接受。

### D2. 合并成一个任务、用 `if self.mode` 分支，而不是 mode-strategy 类
- **候选**：
  - （更轻）根本不合并，保留两个原生任务——但那就不是 IF 的"同场景动词判别"，需求不成立。
  - （选中）一个 task 类，`load_actors/play_once/check_success` 里各一个 `if self.mode` 分支。
  - （更重）Strategy 模式：`PressMode`/`MoveMode` 两个策略类，task 委托给它们。
- **选择理由**：IF 基准硬要求同场景，"不合并"出局。两个 mode 各自专家/判定就 ~10 行且**逐字复用**原生任务，为 2 个分支引入策略类是典型的为想象中的扩展性买单。
- **代价**：`if self.mode` 在三个方法各出现一次，是分支条件的轻度重复。可接受——比策略对象的样板代码轻得多。

### D3. `is_static` 随 mode 切（方案 A），而非两 mode 都非静止（方案 B）
- **为什么要决策**：press 要焊死订书机防倒、move 要能抓起来，共享场景无法两全。（这条是和用户显式讨论后拍的。）
- **候选**：A 随 mode 切 `is_static`（视觉一致、物理属性不同）；B 两 mode 都非静止（物理逐位一致，但 press 专家要自己调稳非静止订书机）。
- **选择**：A。诊断只需相机画面一致，`is_static` 静止画面不可见。
- **诚实的代价**：**"共享场景"其实是"视觉共享"，物理属性两 mode 不同**。这点必须写清楚，别把 press mode 的成功率当成能直接对齐原生 press_stapler（后者场景更空）。已在 impl-verify 标注。

### D4. 指令模板：复用合并现有两份 JSON，而非 MLLM 重新生成
- **候选**：
  - （选中）直接合并 `press_stapler.json` + `move_stapler_pad.json` 的 seen/unseen，做数据卫生。
  - （更重）跑 RoboTwin 的 MLLM description-gen，为 IF 语境重新润色一套模板。
- **选择理由**：现成模板已被原生任务验证过；`{B}` 有无天然对应两个动词。MLLM 重生成是大炮打蚊子，且引入不确定性。
- **代价**：措辞是"两个独立任务"的口吻，没为"同场景判别"专门润色。保真度上可接受，属复刻范围内的合理取舍。
- **合并里必须做的修正**（否则出 bug）：过滤掉 move 池里 1 条漏 `{B}` 的模板（会泄漏进 press mode）、去重、强制 seen/unseen 不相交。

### D5. 干扰物 model_id 采样：枚举 `stable`+mesh 的 id，而非按数量随机
- **候选**：
  - （更轻，且是最初写的——**错的**）`np.random.randint(0, count)`，count = model_data 文件数。
  - （选中）`_stable_model_ids()`：只取 `"stable":true` 且 mesh 存在的 id。
  - （更重）直接调 RoboTwin 的 `rand_create_cluttered_actor` + 整套 objaverse registry。
- **选择理由**：最初的 count-based 是**欠设计的 hack**——假设 id 连续、且物体都能平躺，结果撞上 `071_can` 缺 id 4、`108_block` 缺 scale、markpen 站着，实机接连报错。`_stable_model_ids` 是正确的中间量。全套 cluttered 机制更重、接口不同、还拉进另一批物体。
- **诚实**：这里先踩了"图快用 hack"的坑，debug 掉几个循环才收敛到 stable-filter。教训值钱：**RoboTwin 资产库数据不规整，随机 model_id 不能想当然**（详见 gotchas 坑 A/B/C）。

### D6. 干扰物池：自选 stable 办公物体（"省事路线"），而非硬还原论文原物 / 保留 markpen
- **候选**：（更轻/选中）换成一批 stable 办公物体，全部用统一 glb qpos 自然平躺；（更重）保留 markpen 等非 stable 物体，逐个手调 qpos + 重跑校 z。
- **选择理由**：调研发现 RoboTwin 50 任务无一摆 markpen（stable=false），没有现成 qpos 可抄；静态干扰物本不会滚，用等价的 stable 物体（`093_brush-pen` 顶替笔）零手调、零重跑。
- **代价**：**当前池非论文原物**，是按"办公语境 + 可平躺"自选的等价物。已列入 report 待办（含定位论文图里那个黄色圆角物体）。

### D7. 反例测试：构造末态 + 直接断言，而非改 submodule 记录 / 只跑正例
- **候选**：（选中）`set_pose` 构造错误末态、立即 `check_success` 断言；（更重）改 submodule eval 记录 per-episode 结果、或写作弊 oracle 变体跑完整轨迹。
- **选择理由**：move 判定是 pose-based，`set_pose` 能精准、快速构造 T1/T2/T3，零侵入。
- **边界代价**：press 判定是 contact-based，`set_pose` 伪造不了接触 → press 正例只能真跑专家（T6）、且"抓侧面假阳"这类细案覆盖不到（已在 report 待办 #3）。

### D8. 成功率报告：解析 eval stdout + 采集目录分析，而非改 submodule 落 per-episode
- **候选**：（选中）报告脚本解析 `Success!/Fail! + current seed:N`，按 seed 奇偶拆 mode；（更重）改 submodule eval 把 per-episode (seed,mode,success) 落 json。
- **选择理由**：坚持"零改 submodule"；`mode=seed%2` 让分 mode 拆分不需要额外落盘。
- **诚实的代价**：**stdout 解析对打印格式脆弱**——上游改了 print 就会失效。这是为守住零侵入边界付的税。且 eval-log 这条路目前**还没 policy 验证过**（见改动量级里的 YAGNI 讨论）。

## 二、改动量级评估

**范围**：
- 新增：`tasks/envs/operate_stapler.py`（~245 行，其中专家序列/判定**逐字复用**两个原生任务，真正新写的是 mode 枢纽 ~5 行 + 干扰物加载 ~50 行）、`tasks/task_instruction/operate_stapler.json`（一次性合并脚本产出）、2 个测试、1 个报告工具。
- 修改：`.gitignore` 2 行。
- 重构：**零**。
- **submodule 源码改动：零**（只加 symlink）。

**量级是否匹配问题**：基本匹配，偏"克制"。核心复刻靠复用而非重写，改动集中在自己目录。几处值得警惕：

- **可能的过度设计 / YAGNI**：报告工具的 `--eval-log` 分支是**在还没有 policy 的情况下先写的**——投机。理由是机制（seed 奇偶）已被证明、代码 ~20 行，但严格说它现在无法端到端验证，属于"先建好等用"。可接受但要诚实标记为未验证路径。
- **缓存是否过早**：`_stable_model_ids` 的类级 cache——每 episode 每个干扰物都会调，缓存文件系统扫描是合理的，不算过早优化。
- **回归基线的脆性**：指令测试里硬编码了过滤计数（press 48/10、move 48/8）。脆，但**故意**——池子一改就触发、强制人工复核。是有意的 tripwire，不是坏味道。
- **被迫的 workaround（技术债）**：`add_prohibit_area(actor if config else pose)` 是给 `config=None` 物体（缺 scale）的兜底，本质是在给 RoboTwin 资产数据不规整打补丁；stdout 解析同理。都是被上游/边界约束逼出来的，不是我们想引入的复杂度——记在 gotchas，别让它扩散。

**结论**：没有为了"显得做得多"而堆砌；主要复杂度来自**必须适配 RoboTwin 既有约束**（两次 setup、资产数据坑、零侵入），不是自造的抽象。

## 三、设计模式 / 工程手法

- **Template Method（填框架钩子）**：task 继承 `Base_Task`、覆写 `setup_demo/load_actors/play_once/check_success`。这不是我们的选择，是 RoboTwin 的框架契约——我们只是填模板。恰当，非装饰。
- **单一枢纽变量、多处只读（single source of truth）**：`self.mode` 一处派生、三处读。**这是刻意的手法**，不是随手。反问"不用它、最直白地写会怎样"——答案是：在 check_success 里独立重采 mode，正是我们要避免的 bug。所以这个手法是**必要的，不是装饰**。
- **Seam / 拦截复用（测试里换掉 `collect_data.run`）**：测试不 copy-paste ~40 行 embodiment/config 解析，而是拦截 `cd.run` 拿到它构造好的 args。反问"不用它会怎样"——答案是：复制那段 arg 构造、随上游漂移。所以这个 seam 换来了真实收益（零漂移），justified。
- **刻意不用的模式**：没有为 2 个 mode 引入 Strategy/Factory/抽象基类（见 D2）。若强套，多出的样板复杂度换不来任何收益——2 个分支、各 ~10 行、且是复用。不用任何"模式"、写最直白的 `if self.mode` 才是对的。

**总评**：用到的手法都能通过"不用它会出什么问题"的反问；没有为想象中的扩展性提前抽象。唯一的投机是报告工具的 eval-log 分支（D8），已诚实标注未验证。
