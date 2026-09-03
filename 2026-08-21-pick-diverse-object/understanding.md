# Pick-Diverse-Object：当前理解

> 更新于 2026-09-03。当前 production task 已从历史 color+noun baseline 扩展为 object-familiarity evaluation。

## 一句话定义

每个 episode 放 4 个不同 noun 的物体，指令只点名目标 noun。偶数 raw seed 是 `Seen target / all-Seen scene`，奇数 raw seed 是 `Unseen target / all-Unseen scene`。

## 我们要回答的问题

在不使用 IF-Ext finetune data 的条件下，native-ft VLA 对 raw tasks 出现过的物体和从未出现过的物体，执行同一个“识别并抬起指定 noun”行为时表现有何差异？

这里的核心变量是 **object familiarity**：

- Seen = 被 first-commit `8187d5b` 的 50 个 native/raw task 文件引用的 numbered asset category；
- Unseen = 120 个 numbered categories 中未被这些 raw tasks 引用的类别；
- 清点为 51 Seen / 69 Unseen；
- IF-added tasks 是 eval-only，因此其中使用的资产不会转成 Seen。

instruction JSON 顶层也叫 `seen` / `unseen`，但那只是 **template split**。两者在代码、日志和报告中必须分开命名。

## 已选择的实验设计

- 两组独立场景，不构造 same-scene contrast pair；
- target 和全部 distractors 跟随同一 familiarity group；
- 每场 4 个不同 noun；
- 指令仅名词，不含颜色；
- Seen/Unseen 按 raw seed parity 严格交替；
- target noun 在各自组内确定性轮转；
- exact variant 在完整 noun cycle 后轮转。

这不是 target-only intervention。`S_seen-S_unseen` 同时包含 target familiarity、distractor familiarity、几何和 clutter composition 的变化。正确名称是 scene-level object-familiarity gap。

## 与论文和历史 baseline 的关系

论文 §6.2.1 可确认的任务是：从 12-item everyday pool 抽 4 个物体，以 color+noun 点名一个目标并抬起。论文未公开 12-item 清单、颜色词表、位置分布或 lift threshold。

本项目在 2026-08-21~24 实现过 12 noun / 16 variant color+noun baseline，并真实核验了贴图颜色和 oracle。该版本是历史证据，不再是当前 instruction/sampling contract。当前 familiarity extension 是为了新的研究问题而自建，不能写成论文规定。

## 当前生产池

### Seen

12 nouns / 12 exact variants，每个 noun 恰好一个：bottle/base13、cup/base0、shoe/base8、mug/base0、can/base2、toy car/base5、phone/base1、soap/base0、hamburger/base0、bread/base5、coffee box/base1、mouse/base2。它们全部属于 raw-task Seen，且 exact ID 在 first-commit raw-task Python 的显式集合或动态 metadata 扫描范围内。该轮通过真实贴图 atlas 做视觉选择，并复用 category-level oracle 配置；视觉选择本身不等于 exact-ID 物理验证。下述 20-success collection 发生在这次 Seen exact-ID 重选前，因此其中 Seen episodes 不作为这 12 个新 exact IDs 的 collection evidence。

### Unseen

| noun | exact asset | production evidence |
|---|---|---:|
| dumbbell | `052_dumbbell/base0` | historical confirmation 6/6，左右各 3/3 |
| apple | `035_apple/base1` | fixed top-grasp gate 10/12；左 5/6、右 5/6 |
| wooden mallet | `084_woodenmallet/base3` | historical confirmation 6/6，左右各 3/3 |
| paintbrush | `093_brush-pen/base1` | historical confirmation 5/6，左 2/3、右 3/3 |

Apple 按明确的 production decision 替换 speaker，不替换 dumbbell。当前 Apple 为 `z-pos-up`、完整 z-yaw，并只在 production actor 的 deep-copied config 中使用四个 body-centered top-down contacts；第三方 Apple JSON 和历史 y-pos/native-contact experiments 均不修改。

正常 20-success native collection 在 23 tries 中生成完整 20 组 trajectory/HDF5/MP4/instructions/scene-info：11 Seen、9 Unseen。Apple target 是 episode 2（seed 3）和 9（seed 11），两次均左臂顶抓成功；其余七个 Unseen episode 中 Apple 是竖放 distractor。

## 为什么不是 metadata 选满四类

原始静态 shortlist 为 14 nouns / 54 exact variants：stable rigid mesh + nonempty valid contact group/mask。所有 54 variants 都完成过至少一次真实 exact trial；quick successes 又做 opposite-arm 和 independent confirmation。

原 14 类里只有 dumbbell、speaker、wooden mallet 达到统一门槛。hand bell、drink bottle、trophy、glue、candlestick 等都出现过 quick-sweep false positive；contact pose 可规划也不等于真实执行后能 lift-and-hold。speaker 属于第一版 locked pool，后来是因 Apple 更日常、更易辨识而被 production replacement，并不是其原 confirmation 失效。

为了找到第 4 类，另检查有显式 contact pose、但空 group/mask 的 stable Unseen assets。notebook 与 `093_brush-pen` 被单列为 manual candidates；后者经真实 texture snapshot 命名为 paintbrush，并通过同一 confirmation 门槛。显式 `contact_point_id=0` 只绕开自动 group selection，不修改第三方 metadata。

## Production gate

每个 exact variant 必须同时满足：

1. independent confirmation 成功率至少 70%；
2. 左右臂各至少一次真实成功；
3. 能稳定加入全-Unseen 四物体 production scene。

不因 pool 数量不足降低门槛。metadata、isolated path planning、单次 quick success 都不够。

## Grounding 与 success

`{A}` 直接写成 `the <noun>`；四 noun 唯一，因此 instruction 不需要颜色。`{a}` 保留在句式 contract 中，但 arm 由 target 位置选择，不是本 feature 的主要自变量。

成功必须是被点名 target：

- 相对 settled origin 上升超过 0.02 m；
- 仍与夹爪接触。

抓起 distractor、仅移动 target、未持握的碰撞抬升、初始状态都必须为 False。Layer-B 真实 SAPIEN 测试覆盖 Seen 12 + Unseen 4 正例及两组全部通用负例，22/22 通过。

## 应报告什么

- `S_seen` 和 `S_unseen`；
- 两组 balanced average；
- absolute gap `S_seen-S_unseen`；
- retention `S_unseen/S_seen`；
- 每组 micro 与 per-noun macro；
- exact-variant rates；
- raw tried 与 kept composition；
- setup/planner/physical/check failure stages（有 probe records 时）。

Unseen 只有 4 nouns，且每个 Unseen scene 都包含四类，所以 per-noun macro 是必要主结果，micro 单独看会被 seed/keep bias 误导。

## 当前证据边界

已验证：taxonomy、pool invariants、instruction contract、seed wiring/determinism、Layer-B success discrimination、Apple 双臂 top-grasp gate、正常 20-success native collection，以及所有 Apple-containing scene 的首帧和 Apple-target rollout 目检。

关键数字：static 45/45、wiring 102/102、Layer-B 22/22、Apple physical gate 10/12（每臂 5/6）、20/20 HDF5/MP4/instruction/scene-info。collection accepted seeds 为 `1,2,3,4,5,6,8,9,10,11,12,13,14,15,16,17,18,20,21,22`，failed seeds 为 `0,7,19`。

仍不能声称：

- gap 是纯 target familiarity 因果效应；
- 四类 Unseen 覆盖全部 69 类的分布；
- scripted oracle collection 等于任意 VLA 的可执行能力或性能；
- 人工 placement/contact 参数来自论文；
- 20 个 successful episodes 的 11/9 composition 可替代 raw-seed parity 的 50/50 tried contract。
