# 基于原生动作设计 IF 任务：Readiness、可复现交付与模型基线

核对日期：2026-10-23。项目：robotwin-if，分支 `press_lift_bell`，主仓库 HEAD `d850cb1`。
本文总结 Bottle Hold/Place 与 Press/Lift Bell 的设计经验，以及用户补充的正式交付要求。
这是方法与现状记录；本次写作没有恢复模型 eval、生成正式 manifest 或修改任务链接。

## 三个层次及其完成标准

| 层次 | 要回答的问题 | 主要交付物 |
|---|---|---|
| **Task Feasibility / Readiness** | 任务是否在测预定能力？动作可行、判定合理、指令和场景控制是否成立？ | 原生动作依据、任务定义、成对场景、instruction、expert、判据反例、少量模型可行性检查 |
| **Reproducible Task Delivery** | 别人在指定版本的 RoboTwin 中，能否加载同一任务并复现同一批有效场景？ | task bridge/安装检查、seed contract、固定且均衡的 manifest、生成证据、版本与运行说明 |
| **Extra: Open-source Checkpoint Baselines** | 已交付的任务上，各公开 checkpoint 表现如何？ | 相同 manifest 下的分模式/成组成绩、checkpoint 与推理配置、视频和错误分析 |

Readiness 不是“已经有完整 benchmark 发布包”；生成 manifest、提供可靠的加载入口，是后续独立的完成条件。
Readiness 中可以做少量模型 sanity check；Extra 指冻结任务后更完整的多 checkpoint 基线，二者用途不同。

## 一、Task Feasibility / Readiness

### 1. 先确定评测目的，再选择原生任务中的动作

先写清楚测试轴：动词、对象、属性、手臂、空间关系或动作顺序。若研究动词选择，就尽量固定对象、场景和非目标语言因素，
避免同时要求新抓法、长距离搬运、长时间稳定保持和复杂视觉识别。

接着建立“目标行为 → 原生任务 → 可复用子动作 → 训练/能力证据”的映射。优先从原生演示中提取已存在的动作，
再在共享场景中重新组合，使 instruction 决定执行哪一种行为。例如：

| 需要的行为 | 本项目参考 | 能支持什么判断 |
|---|---|---|
| 按铃 | `click_bell` | 原生任务包含顶部按压/接触动作及其判定代理 |
| 拿起铃铛 | `place_object_stand`、`place_object_scale` 的铃铛抓取阶段 | 原生物体池包含 `050_bell`，完整搬运任务中存在抓起子动作 |
| 二选一 | 同一只可移动铃铛上的 press / lift | 可以提出依赖指令的动作选择实验；新组合仍需独立验证 |

需要纠正“原生 task 存在，所以模型见过这些数据”的简写：应核对目标 checkpoint 的训练说明、任务范围、资产及 clean/random 配置。
**原生任务存在、训练中出现过、模型已经掌握、新组合也能做，是四个不同层次。**
见过完整 place 任务不能证明见过独立的 `Pick up the bell.`；没有找到训练证据也不等于模型绝无泛化能力。
把训练覆盖当作选型依据，再用能力检查补充，不能只凭任务目录名称断言。

### 2. 从最小动作差异开始，控制组合难度

原生子动作可以组合，但组合长度和状态分布也会引入新难度。先验证最短、最容易区分的一对，再逐步扩展。

Bottle Hold/Place 需要抓起、搬运到垫子附近、定位，再保持或释放；该 pilot 的 24 个模型回合均未成功。
其中 hold 终态首先违反位置要求，不能只通过缩短保持时间来修复。后来改用铃铛 press/lift，去掉搬运目标和长时间保持，
才更容易拆开“会不会做这个动作”和“有没有根据 instruction 选动作”。

复杂组合并非不能测，但应将结论标为组合执行能力，避免把所有失败归结为不读指令。

### 3. 用共享、适度陌生的场景减少视觉任务捷径

目标是减少整场景与某个原生任务的一一对应，同时保留熟悉的机器人、物体资产、可达区域和基本操控方式。

| 场景方案 | 适用用途 | 收益与代价 |
|---|---|---|
| 原生场景及原生指令 | 能力基线、接口检查 | 最接近训练任务，但容易靠场景猜目标 |
| 同一初始态配多条指令 | IF 主对照，必要基础 | 视觉不能唯一决定正确目标；仍可能存在物体的默认动作先验 |
| 共享场景中加入中性 distractor，并受约束地随机位置 | 可与上一项组合 | 减少固定场景模板和物体位置线索，但增加少量识别/泛化难度 |
| 大幅改变背景、相机、资产、物理或放置范围 | 单独的鲁棒性实验 | 分布变化更强，失败归因也更复杂，不宜一次性全部加入 |

本次去掉 stand、scale、目标垫等明显的搬运目的地，使用铃铛、鼠标、玩具车组成共享场景。
后续让两个 distractor 在安全区域随机摆放，允许左右次序交换，且与铃铛和彼此保持间距。
场景随机数只由 scene seed 决定，不能随指令 mode 改变；否则会制造新的视觉答案线索。

当前参数是本项目的实例：X ∈ [-0.30, 0.30] m、Y ∈ [0.04, 0.22] m；中心距铃铛至少 22 cm，彼此至少 18 cm。
这些数值用于当前资产和桌面，不是其他任务的通用阈值。

“看起来与原生场景不同”不等于已经消除捷径。应在固定布局/随机布局或 bare/context 的匹配条件下比较模型，
再结合相同画面下的指令替换、必要时的 instruction 消融。无指令输入本身可能偏离训练分布，只能作为辅助证据。

### 4. 配对需要控制全部初始条件

本任务用 `episode_seed = 2k / 2k+1` 表示两个 mode，用 `scene_seed = k` 初始化完整场景。
同一对的三路 RGB、机器人 proprio、对象状态和物理参数都应一致；只有 instruction 的目标动作不同。

不要只核对铃铛坐标：相机、背景、机器人初态、distractor、质量、静态/动态属性、动作预算和可见辅助信息也可能泄露 mode。
本次原生 click 使用静态铃铛，而 lift 必须可移动；新任务两边共用动态铃铛，避免隐含物理差异。
静态改动态仍属于相对原生任务的分布变化，需要重新验证 expert 和模型。

随机策略还应固定或记录推理采样 seed、历史缓存重置和采样参数，并通过重复配对降低偶然性。
场景初态逐数组相同，不代表 GPU 规划器的每个中间物理步也必然完全相同。

### 5. Instruction 借鉴原生表达，但保持对照变量清楚

优先参考原生**实际会进入生成链路**的模板和子动作措辞。不能只搜索 JSON 文本：模板过滤、占位符替换及最终适配器可能改变模型收到的文字。

当前选择动作短语对照：

| mode | instruction | 共同对象 |
|---|---|---|
| press | `Press down on the bell.` | `the bell` |
| lift | `Pick up the bell.` | `the bell` |

这是从原生表达改写/截取的句子；不能声称训练集中有这两条完全相同的独立指令。
“只换动作短语”与“增加针对动作的部位/步骤解释”是两种实验：后者可能更容易执行，但语言差异不再局限于动词。
应先确定目的，再选择，不把两种版本的成绩混算。

当前运行时链路为 `INSTRUCTIONS → env.policy_instruction → setup_episode → policy adapter`。
任务 JSON 与运行时常量都已同步；只改 JSON 并不会改变这个实验实际下发的文本。

### 6. Expert、成功判据和模型能力分别验收

| 检查 | 必须确认的内容 | 单独通过仍不能证明什么 |
|---|---|---|
| Expert / oracle | 每个 mode 均可完成；覆盖对象变体、左右侧、随机位置；不是仅规划无报错 | 不能证明模型会做或判据合理 |
| 成功判据 | 正确行为通过，错误行为拒绝；合法的不同路径也可接受 | 不能证明模型能产生正确行为 |
| Policy reset / 接线 | expert 后完整重建同 seed；判据基准在 setup 初始化；实际指令、预算、初态正确 | 不能证明语言被使用 |
| 少量模型能力检查 | 原生基线、简单单动作、新共享场景中是否有可执行证据 | 小样本不能证明稳定能力或跨模型排名 |
| 配对行为检查 | 相同场景不同指令产生相应动作，报告双成功与错误类型 | 不能仅凭一组成功断言彻底消除视觉捷径 |

Expert 不应只在自己的 `play_once()` 路径中初始化判据。模型在 reset 后直接调用 `take_action()`，也必须有正确的初始高度、
接触状态、计时器和 mode。Expert 能调用物体真值位置和规划器，而模型只能使用规定的观测，两者能力条件不同。

成功条件首先与原生逐项对照：接触语义、位置容差、检查频率、仿真计时、早停/终态、允许的动作策略。
不要因为 expert 恰好撤离某个距离、用某个速度或姿态，就自动把它们变成模型必须满足的条件。
必要的额外约束要有任务语义依据，同时保留原生条件的诊断结果。

本次具体教训：原生 click 接受包括零冲量在内的接触报告，按 4 ms 物理步检查；新任务曾过滤冲量并降采样到 20 ms。
LingBot-VA 的动作回放中原生条件可以满足，新增冲量门槛却阻止 Press 建立候选。之后对齐为逐物理步检查、不过滤冲量。
仅把采样目标写为 2 ms，并不能从 4 ms 的仿真中得到额外状态。

完整 Press 目前仍要求撤离 2 cm。X-VLA 有一例原生 click 已成功，但最大撤离约 1.36 cm，仍被完整 Press 拒绝。
因此“接触条件对齐”并不是“整个任务 success 已等价”。这是需要保留解释、继续审视的额外条件。

判据反例至少覆盖：未碰到、碰错部位、只抓未抬、弹起但未抓持、闭合抓取被误判成按压，以及先后把两个候选动作都做一遍。
要先决定研究首个完成动作还是最终状态，再设计互斥性；不能让模型通过“两个都试一下”在每条指令下都成功。

模型 pilot 若全面失败，应按接口/场景无效、判据差异、目标识别、动作执行和动词选择等层次诊断。
不要只看最终红绿标签，也不要直接认定模型“不看 instruction”。

### Readiness 的交接门

进入正式交付前，应能给出：明确的测试轴与原生动作依据；共享且无 mode 泄漏的场景；固定指令及实际下发证据；
各 mode 的 expert 可行性；成功判据正反例与原生差异；小规模模型检查及失败归因边界。
开发阶段可迭代，但应预留未用于调设计的场景用于后续正式评测。

## 二、可复现交付：加载入口与 Seed Manifest

### 1. 确保正式 RoboTwin 入口能加载新任务

独立 runner 能跑，只证明该 runner 的路径注入有效。正式交付需要检查或更新链接/注册脚本，使新任务可从约定入口安装并加载。
实践中应先验证正式加载路径，再从该路径生成 manifest，以免 manifest 依赖未发布的本地注入逻辑。

本项目已有：

- [`scripts/bridge_tasks.sh`](../../scripts/bridge_tasks.sh) 调用 [`scripts/_task_bridge.py`](../../scripts/_task_bridge.py)。
- `MAINTAINED_TASKS` 决定 env 和 instruction JSON 的链接；`ENV_HELPERS` 决定 helper 链接。
- `--dry-run` 预览，`--check` 核对，`unbridge_tasks.sh` 管理本工具拥有的链接。

接入应检查 env、helper、instruction JSON、任务清单、mode 读取、配置/预算和实际 import 来源，而非只确认 task.py 存在。
检查脚本可重复运行，链接指向当前声明源码，旧链接不会悬空，也不覆盖不属于本项目的原生文件。
目标 RoboTwin commit、接口及本地兼容性改动需要核对；不应默认加兼容性跳过参数。

### 2. 生成固定、均衡、经过 expert 资格检查的 manifest

Manifest 固定的是**有效测试场景集合及其顺序**，不是“模型能成功的集合”。
候选按预先声明的区间和顺序扫描，以完整 balance block 接受或拒绝：对 press/lift 而言，一组同时包含两条指令。

每个成员应检查：setup、实际 mode、expert planning、success、reset/清理；共享初态的对照还应验证配对观测一致。
任一 mode 无效，应拒绝整组并记录原因，再检查下一个候选 block，不能只保留容易的一边。

**可以过滤 expert 无法完成或场景无效的 seed；不能根据模型成功与否筛 seed。**
过滤会使评测范围成为“通过该资格协议的场景子集”，应公开候选数、拒绝率和拒绝原因。
若 expert 有随机不稳定性，应预先定义复查/重试规则；固定 seed 本身不能保证未来每次规划都成功。

本项目已有生成器 [`tools/generate_if_seed_manifest.py`](../../tools/generate_if_seed_manifest.py)、
验证器 [`tools/validate_if_seed_manifest.py`](../../tools/validate_if_seed_manifest.py) 和
[使用指南](../../docs/seed-manifest-usage.md)。正式接入新任务时，不仅要加入 seed contract，还要补齐生成器及 evaluator 的 observed-mode 读取。

| 产物 | 内容 |
|---|---|
| `<task>.json` | 现有 flat schema：`schema_version`、`task`、`task_config`、exact episode `seeds` |
| `<task>.generation.json` | 接受/拒绝的 blocks、各阶段结果、期望/实际 mode、异常、源码/配置/目标版本与 manifest 哈希 |
| 运行/发布说明 | 依赖与安装入口、实际 instruction 版本、检查器版本、动作预算、资格协议、复现及错误处理方式 |

所有 checkpoint 使用同一 manifest，不在评测时自行跳到下一个成功 seed。
若固定 seed 重新资格检查失败，记录为基础设施/资格问题，按预定规则处理；不要临时更换测试场景或计作模型行为失败。
模型完成执行后的失败必须保留。中途暂停未完成的回合也要单独标记。

场景、instruction、物理或 checker 改变时，应评估资格证据和结果是否仍兼容，重新发布受影响版本，不能混用旧分数。
只修复统计展示时可以重算；改变判定且旧轨迹有早停或缺失状态时，通常不能靠重标结果替代新评测。

## 三、Extra：公开 checkpoint 的标准化成绩

正式任务与 manifest 冻结后，再提供更完整的开源模型基线。Readiness 中的少量 pilot 只证明实验方向有可执行证据，
不等于已形成公开 leaderboard，也不是挑选“模型做得好”的 seeds 的依据。

成绩应绑定 checkpoint repo/revision、训练设置、适配器、相机/状态/动作接口、历史缓存、推理配置、预算、manifest 哈希及任务版本。
本项目的公开 checkpoints 存在 clean 与 clean+random 训练设置差异，不能默认训练条件相同。
接口与训练范围见 [policies/README.md](../../policies/README.md)。

至少报告各 mode 成功率、同场景全部 mode 成功率、原生条件与附加条件的差异，以及错误类型。
仅报平均成功率会掩盖“总是执行一个默认动作”；原生接触成功也不能自动代替完整任务成功。
更大样本、跨场景重复和文字替换对照用于支持泛化及 instruction 使用的结论，小样本不用于可靠排名。

保留逐回合视频、初始观测、动作、仿真时间和判定信号。模型失败后诊断证据链，避免看完分数再无记录地改标准。

## 本项目目前到哪一步

| 版本/产物 | 已观察到的事实 | 不能据此声称 |
|---|---|---|
| Bottle Hold/Place，`e7a7f7c` | 六模型 pilot 完成 24/24，均失败；任务包含定位、搬运和稳定要求 | 不能只归因于动词理解失败 |
| Bell 接触对齐，`1651f35`，固定 distractor、旧 instruction | LingBot-VA Press 2/2、Lift 1/2、双成功 1/2；整轮在 6/24 时按用户要求暂停 | 不是最终随机场景和新 instruction 的成绩 |
| 随机 distractor，`b37a6de` | 15 项测试；8/8 oracle；四对初始 RGB/proprio 相同，铃铛初态和 proprio 与固定布局一致 | 尚无模型证据证明随机化减少视觉捷径 |
| 新动作短语，`d850cb1` | 实际下发链路已更新，15 项测试通过 | 尚未对新句做模型推理 |
| 正式 manifest / bridge | **待接入**：当前 `press_lift_bell` 不在正式 seed contract、bridge task/helper 清单中 | 独立 runner 成功不能称为正式交付完成 |

当前 `tools/press_lift_bell.py` 在本进程扩展 `envs.__path__`，支持显式 scene seeds，但没有正式 `--seed-manifest` 接口。
源码核对发现：正式 bridge 当前声明 17 个链接；这不是本次执行 `--check` 得到的通过结果。
bridge 锁定的 RoboTwin commit 为 `0aeea2d…`，本地实验 checkout 为 `b82ffb8…`，正式接入前需要核对兼容性。
新任务还需补齐 seed contract、mode adapter、加载/manifest 使用路径及相应测试；本笔记没有执行这些工程改动。

因此当前具备一批 Readiness 证据，但最终随机布局加新 instruction 的模型 sanity check、正式 manifest 和安装交付仍有待完成。
模型 eval 保持用户要求的暂停状态。

## 复查方式与边界

以下在主仓库根目录执行，只读取源码或已保存结果，不启动模型/仿真：

```bash
git show --stat d850cb1
rg -n 'INSTRUCTIONS|sample_context_positions|VERSION' tasks/envs/_press_lift_bell.py
rg -n 'MAINTAINED_TASKS|ENV_HELPERS|LOCKED_ROBOTWIN_COMMIT' scripts/_task_bridge.py
rg -n 'press_lift_bell' if_benchmark/seed_contracts.py tools/generate_if_seed_manifest.py
cat outputs/policy-eval/press-lift-bell-six-models-2blocks-005/paused.json
cat outputs/policy-eval/press-lift-bell-random-context-oracle-001/layout-validation.json
```

最后的 `rg` 当前找不到新任务，这是尚未正式注册的证据；不要把无输出当作已支持。
`paused.json` 记录 6 个完成的 policy 回合和中断的 X-VLA seed 6；`layout-validation.json` 记录随机布局的 oracle 与配对检查。
`outputs/` 仅在当前机器存在，不随 Git 分发。

未来接入完成后，按 [manifest 指南](../../docs/seed-manifest-usage.md) 从正式入口生成种子，
再用 `tools/validate_if_seed_manifest.py --require-evidence` 验证生成物。
`bash scripts/bridge_tasks.sh --dry-run`、`bash scripts/bridge_tasks.sh --check` 是预览/核对入口；实际安装命令会修改 RoboTwin 链接。
本次没有执行这些 bridge 命令，也没有生成新 manifest。此前验证结果来自已保存记录，未为写笔记重新运行测试或评测。

## 参考与笔记状态

- [Bell 实验、原生判定对照与各版本记录](../../docs/press-lift-bell-experiment.md)
- [原生 click success](../../third_party/robotwin/envs/click_bell.py)
- [原生 instruction 生成器](../../third_party/robotwin/description/utils/generate_episode_instructions.py)
- [共享 policy setup](../../policies/evaluation.py)
- [被测行为与已有能力的关系](../../docs/task-design/被测行为须在能力库内-IF避免塌成OOD.md)
- [历史 IF 任务实现 SOP](../../docs/task-design/IF任务实现流水线-SOP.md)
- [历史判定/初始化修复后的结果复用原则](../2026-09-16-task-fixes-rerun-audit/concepts.md)
- [旧 Bottle Hold/Place 记录，固定 commit](https://github.com/v-xchen-v/robotwin-if/blob/e7a7f7c/docs/bottle-hold-place-experiment.md)

本篇由独立 `notes/` 仓库的 `notes/vibe-coding` 分支管理，并同步到远端同名分支；以 Git 提交记录追溯版本。
统一同步入口是主仓库根目录的 `just vibe-notes-push`，它会提交 notes 全部改动。
本次仅定向新增本篇笔记的提交，再推送分支；其他历史结果的未提交内容保持原样。
