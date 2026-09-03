# Pick-Diverse-Object：决策记录

> 当前状态：2026-09-03 object-familiarity extension 已锁定。Production Unseen pool 为 dumbbell、Apple、wooden mallet、paintbrush；一次性候选实验已在 closeout 中移除，只保留 aggregate outcome 与决策理由。

## D1 — Seen 的定义来自 raw-task 资产引用

**决定**：编号资产只要被 first-commit `8187d5b` 的 50 个 native/raw tasks 引用，就属于 raw-task Seen；否则属于 raw-task Unseen。

**结果**：51 Seen / 69 Unseen，覆盖全部 120 categories。

**理由**：研究问题是 native-ft 是否接触过该物体。IF-Ext 不生成或消费 finetuning data，所以 IF-added task 中出现的 asset 不改变 familiarity。instruction JSON 顶层 `seen/unseen` 只切 sentence templates。

## D2 — 采用两组独立同质场景

**决定**：Seen target 配 all-Seen scene；Unseen target 配 all-Unseen scene。

**取舍**：same-scene target-only contrast 的因果解释更强，但当前 Seen/Unseen assets 无法做到替换后 pixel-identical。最终 gap 因而是 scene-level familiarity difference，不是 target-only causal effect；reporter 和文档必须明确这一点。

## D3 — 指令改为 noun-only

**决定**：四物体 noun 强制唯一，`{A}` 为 `the <noun>`，移除颜色条件。

**理由**：本扩展隔离 object-category familiarity；颜色会额外引入 attribute grounding。历史 color+noun baseline 作为论文复刻证据保留，但不再是 production contract。

## D4 — Distractors 跟随 target group

**决定**：target 和三个 distractors 全部来自 active familiarity pool，且 noun 不重复。

**后果**：Unseen pool 恰好四类，所以每个 Unseen scene 都出现四类，只轮换 target role、pose 和 ordering。必须同时报告 per-noun macro。

## D5 — Raw seed parity 控制 tried composition

**决定**：偶数 Seen、奇数 Unseen；`group_index=seed//2` 驱动每组 target cycle。

**理由**：相邻 raw seeds 严格 50/50。不得用 successful-episode count 替代 tried denominator，也不得为 setup/planning failure 偷换 seed。

## D6 — Metadata 只做 shortlist，不做 admission

**决定**：原 Unseen shortlist 条件是 rigid visual/collision mesh、`stable=True`、有效 nonempty contact group/mask。14 nouns / 54 exact variants 全部进入真实 probe，但不会自动进入 production。

**门槛**：independent confirmation ≥70%，左右臂各至少一次真实成功，并能参与 all-Unseen production scene。

## D7 — 不为凑够四类降低门槛

主要 false positives：

- hand bell base4：多个 yaw/contact follow-up 仍约 4/6 或更低；
- drink bottle base2：fresh contact-ID confirmation 2/6；
- trophy base3/base4：0/4、2/6；
- glue base2/base6：2/6、1/6；
- candlestick base2：2/6，另有 setup failure。

**决定**：保持固定门槛。isolated planner reachability 和 quick success 不能替代执行后的 lift-and-held confirmation。

## D8 — Manual candidates 与原 14/54 分层

**决定**：notebook 和 `093_brush-pen` 单列 manual inventory。它们 stable 且有 contact poses，但 group/mask 为空，不满足原 shortlist 条件。

**结果**：显式 `contact_point_id=0`、不修改 third-party metadata。paintbrush/base1 达到 5/6（L 2/3、R 3/3）并成为第四类；notebook 未通过。

## D9 — Noun 以真实 geometry/texture 为准

- `068_boxdrink` → drink bottle；
- `111_callbell` → hand bell；
- `093_brush-pen/base1` → paintbrush。

Asset category name 和历史 description 可能不准确；真实 baseColor texture + geometry snapshot 才是 instruction noun 的视觉依据。

## D10 — Production placement 使用 footprint radius

**决定**：按 radius 从大到小放置，pair separation 为 `radius_a + radius_b + 0.025`，tie 由 seed 决定。forced exact-candidate probe 使用 target-first；production 始终 radius-first。

**理由**：固定中心距会让 dumbbell、mallet 等长物体碰撞；probe placement 不能泄漏到 production。

## D11 — Success 为 target-specific lift-and-held

**决定**：named target 相对 settled origin 上升 >0.02 m 且仍在 gripper contact 才成功。

**拒绝**：任意 actor 被抬起、只看 z-rise、仅检查末态位置。抬起 distractor、移动但未保持 target 均为 False。

## D12 — 第一版四类 pool 作为历史 evidence，而非现役 manifest

第一版为 dumbbell/base0、small-speaker/base1、wooden-mallet/base3、paintbrush/base1。odd seeds 1–15 达到 8/8 setup、8/8 settle、7/8 oracle，四个 target nouns 都至少成功一次。

**Closeout 决定**：保留 `evidence/unseen_production_seeds_1_15.{json,csv}` 作为首次四物体 coexistence 的历史证据，但删除 runtime 中的备份 pool。当前代码不提供 `PRE_APPLE_UNSEEN_POOL`，也不把这次 sweep 当作当前 Apple pool 的 production result。

## D13 — 不借用 procedural `108_block` 结果

IF-Grasp-Approach 创建 procedural box，并未加载 `108_block` asset。相同名词或视觉概念不能替代 exact-asset evidence。

## D14 — Report 同时报 micro、macro 与 retention

主报告包含 `S_seen`、`S_unseen`、balanced average、absolute gap、retention、per-group micro、per-noun macro、exact variants 和 tried/kept composition。禁止 target-only causal language。

## D15 — 098 speaker 未过固定门槛

`098_speaker/base3` 外观更容易辨认，但缺少生产所需 scale/contact metadata。历史 probe-only config 注入 task-local scale/contact frames且不修改 source JSON。

**结果**：independent confirmation 4/6（L 1/3、R 3/3），低于 ≥70%；停止于 coexistence 前，不追加 trial、不降低门槛。

**Closeout 决定**：删除 098 的 one-off runtime manifest 和 raw/debug evidence，只保留上述 aggregate conclusion。当前 generic probe 不再复现这套 handcrafted config。

## D16 — 旧 Apple natural-pose/radius-first 实验不决定最终 production

早期实验把 Apple 临时替换 dumbbell，使用 native side contacts，并针对 principal-axis pose family 做严格 drift/tilt/packing gate。没有 pose family 达到冻结的 6/6 family gate；多数失败来自共享场景 packing，`x-pos-up` 另有重复 tilt/drift failure。

Outcome-informed radius-first follow-up 的 Gate A 为 5/6：五个 executed scenes 稳定，固定 seed 25001 无合法 placement。随后独立 exploratory grasp 为 5/6 overall、5/5 conditional on attempt，但不能重写已失败的 packing gate。

**Closeout 决定**：这些结果只保留为历史 aggregate reasoning；one-off pose families、stability schema、policy mapping、JSON/CSV、debug frames 和 exploratory MP4 已删除。最终 Apple production decision 是独立决策。

## D17 — Apple 替换 speaker，而不是 dumbbell

**决定**：最终 `UNSEEN_POOL` 固定顺序为：

1. dumbbell — `052_dumbbell/base0`
2. apple — `035_apple/base1`
3. wooden mallet — `084_woodenmallet/base3`
4. paintbrush — `093_brush-pen/base1`

**理由**：Apple 更日常、noun grounding 更直观；用户明确要求替换 speaker。最终 pool 直接声明，不通过历史 replacement manifest 派生。

## D18 — Production Apple 为 z-up、body-centered top grasp

第一轮 promotion 沿用 y-pos-up/native contacts，视频中 Apple 侧放、侧抓；仅改 z-up 后 native contacts 对位置/yaw/arm 仍不稳定。

**最终配置**：

- exact asset `035_apple/base1`；
- z-up visual pose + full world-z yaw；
- 四个经过验证的 top-down wrist-roll rotations；
- contact translation 使用 native metadata `center`；
- actor 创建后 deep-copy config，只改当前 production actor；
- source `model_data1.json` 不修改。

**固定门槛**：left 5/6、right 5/6、总计 10/12；两次失败都是后缘 planner failure，十次成功均 lift-and-held，approach-axis world-z 约 `-1.0`。

## D19 — 正常 collect-data 路径验收 production

使用正常 `collect_data.sh pick_diverse_object pdo_apple20 0`，不增加 collection-only scheduler。

**结果**：23 tries 收满 20 successes；accepted seeds `1,2,3,4,5,6,8,9,10,11,12,13,14,15,16,17,18,20,21,22`，failed `0,7,19`。生成 20 trajectory、HDF5、H.264 MP4、instruction JSON 和 scene-info records。

Apple 在 9 个 Unseen scenes 全部 z-up；target episodes 2/9 均由左臂 top-grasp、lift-and-held。右臂能力来自 D18 的 fixed gate，不从这两段自然调度视频推断。

**边界**：这是 scripted oracle 和 pipeline closeout，不是 VLA evaluation；successful 11 Seen / 9 Unseen composition 不能替代 raw-seed parity。

## D20 — 更日常候选均未替换 final four

Closeout 前还测试了更日常的 Raw-task-Unseen objects：

- perfume/base1：native grasp 1/2；base2 只完成 settle 后按用户决定放弃；
- toothpaste/base0：baseline native grasp 0/2；upright pose-only rescue仍未形成可靠双臂候选；
- whiteboard eraser/base0：baseline native grasp 0/2；用户随后明确放弃 eraser，不做 contact-frame tuning；
- tissue-box/base4：一个 contact 路径出现 `target_pose cannot be None`，另一路径 target z-rise 0；视频显示 missed contact/推到 distractor。

**决定**：不继续 candidate exploration，不修改 source contacts，不把 settle success 当 grasp admission。perfume、toothpaste、eraser、tissue-box 的 one-off manifests、pose atlases、raw/debug evidence 在 closeout 删除。

## D21 — Closeout 只保留长期接口和最终证据

保留：

- final Seen/Unseen production manifests；
- 原 14/54 shortlist 与 manual inventory；
- generic exact-variant/production-seed probe；
- final selected-object evidence；
- final Apple z-up/top-grasp videos/screenshots；
- first locked-pool coexistence JSON；
- historical color+noun baseline evidence。

删除：一次性 candidate-set registries、stability/policy interfaces、淘汰候选 raw/debug evidence、old Apple y-pos/radius-first evidence、098 evidence 和 duplicate report。

该边界使 production source of truth 只剩当前四类，同时保留足够的选择依据与最终审计证据。
