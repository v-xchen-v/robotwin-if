---
status: implemented
parent: "[[RoboTwin-IF 复刻]]"
tags: [robotwin, vla, benchmark, object-familiarity]
---

# Pick-Diverse-Object

> feature-04。2026-09-03 完成 object-familiarity extension：Seen target / all-Seen scene 与 Unseen target / all-Unseen scene。

## 结论

每个 episode 放置四个**不同名词**的物体，指令只用 noun 点名 target。raw seed 偶数生成全-Seen scene，奇数生成全-Unseen scene；target 和三个 distractors 全部来自同一 familiarity group。

这是**整场 object-familiarity split**，不是 pixel-identical same-scene contrast。`S_seen-S_unseen` 同时包含 target、distractor、geometry 与 clutter 差异，不能解释为 target-only causal effect。

## 论文事实与本项目扩展

论文 §6.2.1 可确认：从 12 个日常物品中采样四个，指令用 color+noun 指定 target，机器人识别并抬起目标。论文没有公开 12-item 清单、成功阈值、位置分布或颜色词表。

本项目历史上实现并验证过 12 noun / 16 variant color+noun baseline；其视频仍作为历史 grounding evidence，但不再是当前 production contract。

当前 familiarity extension 是自建设计：

- Seen/Unseen 使用两组独立、组内同质 scene；
- 四个 nouns 必须不同；
- instruction 为 noun-only；
- metadata 只用于 shortlist；
- exact production variant 必须通过真实 SAPIEN settle/grasp evidence。

## Object familiarity 定义

- **Raw-task Seen**：numbered asset category 被 first-commit `8187d5b` 的 50 个 native/raw task 文件引用。
- **Raw-task Unseen**：不被上述 raw tasks 引用。
- IF-Ext 是 eval-only，不产出 finetuning data；资产被其他 IF task 使用仍是 raw-task Unseen。
- 清点结果：**51 Seen + 69 Unseen = 120 categories**。

不要与 instruction JSON 顶层 `seen/unseen` 混淆；后者只表示 sentence-template split。

## Production pools

共享 source of truth：`tasks/envs/_pick_diverse_object_pool.py`。

### Seen：12 nouns / 12 exact variants

| Noun | Exact variant |
|---|---|
| bottle | `001_bottle/base13` |
| cup | `021_cup/base0` |
| shoe | `041_shoe/base8` |
| mug | `039_mug/base0` |
| can | `071_can/base2` |
| toy car | `057_toycar/base5` |
| phone | `077_phone/base1` |
| soap | `107_soap/base0` |
| hamburger | `006_hamburg/base0` |
| bread | `075_bread/base5` |
| coffee box | `113_coffee-box/base1` |
| mouse | `047_mouse/base2` |

全部 exact IDs 可由 first-commit raw-task 显式 ID 集或动态 metadata 扫描选到。`phone/base1` 使用 native standing quaternion `(0.5, 0.5, 0.5, 0.5)`。

### Unseen：final four

| Noun | Exact variant | Evidence | Production config |
|---|---|---:|---|
| dumbbell | `052_dumbbell/base0` | 6/6；L 3/3，R 3/3 | radius 0.105 |
| apple | `035_apple/base1` | 10/12；L 5/6，R 5/6 | z-up；full z-yaw；4 body-centered top contacts；radius 0.055 |
| wooden mallet | `084_woodenmallet/base3` | 6/6；L 3/3，R 3/3 | radius 0.100 |
| paintbrush | `093_brush-pen/base1` | 5/6；L 2/3，R 3/3 | explicit contact ID 0；radius 0.080 |

Apple 按用户要求替换 speaker，而不是 dumbbell。当前 `UNSEEN_POOL` 直接声明上述四类，不保留历史 replacement pool。

## Candidate gate

原 metadata shortlist 有 14 nouns / 54 exact variants，静态条件为：rigid visual/collision mesh、`stable=True`、nonempty valid contact group/mask。所有 variants 均完成真实 exact trial；quick success 者再做 opposite-arm screen，强候选使用 fresh seeds confirmation。

Production admission：

1. independent confirmation ≥70%；
2. 左右臂各至少一次真实成功；
3. 能稳定参与 all-Unseen production scene。

hand bell、drink bottle、trophy、candlestick、glue 等 quick high points 均在 confirmation 回归，未因 pool 数量而降门槛。

Paintbrush 不在原 14/54 shortlist：它 stable 且有 contact poses，但 contact group/mask 为空。显式 `contact_point_id=0` 后通过同一门槛；third-party metadata 未修改。

## Apple production specialization

Production Apple 使用 `apple_top_down` strategy：

1. `035_apple/base1` 以 z-up 放置，保留完整 world-z yaw；
2. task layer deep-copy actor native config；
3. 四个 contact rotations 为已验证的 top-down wrist-roll frames；
4. translations 使用 native metadata `center`，使 fingers 围住果体中部；
5. source `model_data1.json` 不修改。

固定、无 replacement retry 的 gate 为 left 5/6、right 5/6、overall 10/12。十次成功均 lift-and-held，approach-axis world-z 接近 `-1.0`；两次失败为桌面后缘 planner reachability failure。

正常 20-success native collection 在 23 tries 中收满 20 个 outputs；Apple target episodes 2/raw seed 3 与 9/raw seed 11 均 top-down grasp、lift-and-held，Apple 在所有 9 个 Unseen scenes 中都为 z-up。

## Seed wiring 与 placement

```python
familiarity = ("seen", "unseen")[seed % 2]
group_index = seed // 2
```

- 连续 raw seeds 的 tried denominator 为严格 50/50；
- 每组 target noun 按 `group_index % len(pool)` 轮转；
- exact variant 在完整 noun cycle 后轮转；
- scene RNG 使用 raw seed；不做 same-scene pair；
- target + 3 distractors 均从 active pool 采样且 noun 不重复；
- production placement 按 footprint radius 从大到小；forced exact-candidate probe 固定 target-first；
- pair separation 为 `radius_a + radius_b + 0.025`。

Retained probe hooks 均默认 `None`：

`FAMILIARITY_OVERRIDE`, `TARGET_NOUN_OVERRIDE`, `TARGET_MODEL_ID_OVERRIDE`, `TARGET_SIDE_OVERRIDE`, `POOL_OVERRIDE`, `DISTRACTOR_NOUNS_OVERRIDE`。

## Instruction、oracle 与 success

```python
self.info["info"] = {
    "{A}": f"the {self.target_noun}",
    "{a}": str(arm_tag),
}
```

`{A}` 是字面 noun phrase，不走 color description。四个 nouns 唯一，所以 noun 足以定位 target。

`play_once()` 从 manifest 读取 pose、rotation、strategy、kwargs 与 placement radius。Apple 在 actor 创建后注入独立 top-contact config；所有目标统一 world-frame `z=0.12` lift。

`check_success()` 使用：

```python
named_object_lifted_and_held(task, target, modelname, origin_z)
```

只有 named target 比 settled origin 高超过 0.02 m 且仍与 gripper 接触才为 True。抓 distractor、仅撞起 target 或移动后未保持均为 False。

## Probe 与 closeout 边界

`tools/probe_pick_diverse_unseen.py` 保留长期接口：14/54 shortlist + manual inventory exact probes、双臂/repeats、fixed JSON/CSV、可选 H.264 video，以及 odd production-seed mode。generic settle failure 在 oracle 前 fail closed，不替换 raw seed。

Closeout 删除了 098 speaker、旧 Apple natural-pose/radius-first、perfume、toothpaste、whiteboard eraser、tissue-box 的 one-off manifests、stability/policy interfaces 和 raw/debug artifacts。aggregate outcome 保留在 notes 的 decisions/selection 文档，但当前 runtime 不再承诺复现这些 handcrafted experiments。

关键淘汰结论：

- `098_speaker/base3`：4/6（L 1/3，R 3/3），低于 ≥70%；
- old Apple radius-first gate：5/6，固定 seed packing failure；
- perfume/base1：native grasp 1/2；
- toothpaste/eraser baseline：均 0/2；eraser 后续明确放弃；
- tissue-box/base4：planner/contact failure，无 lift-and-held success。

## Reporting

`tools/report_pick_diverse_object.py` 输出：

- `S_seen`：Seen target / all-Seen scene；
- `S_unseen`：Unseen target / all-Unseen scene；
- balanced average、absolute gap、retention；
- group micro、per-noun macro、exact-variant rates；
- tried/kept composition。

必须保留警告：独立场景 gap 不是 target-only causal gap。successful episode composition 不能替代 raw-seed tried denominator。

## Verification

当前长期验证层：

- static pool/taxonomy/schedule/top-contact contracts；
- simulator-free probe qualification/video helpers；
- noun-only instruction templates；
- real-SAPIEN seeds 0–7 production wiring、determinism、Apple config isolation与 source JSON immutability；
- Apple fixed cross-arm gate 10/12（L 5/6、R 5/6）；
- target-specific success semantics；
- reporter synthetic aggregation；
- normal collection output integrity与 final Apple video review。

精确 test counts 以 `notes/2026-08-21-pick-diverse-object/report.html` 的最终 verification matrix 为准。

## 解释边界

1. Seen 与 Unseen 为不同 scene，gap 是 scene-level familiarity difference。
2. Unseen pool 只有 4 nouns，每个 Unseen episode 都出现四类；必须报告 per-noun macro。
3. Seen 12 类和 Unseen 4 类均是人工/物理筛选子集，不代表完整 51/69 taxonomy。
4. lift threshold、pool composition、paintbrush contact ID、Apple task-local contacts 和 placement radii均是项目自建设计。
5. 20-success collection 是 scripted oracle/pipeline validation，不是 VLA 的 `S_seen/S_unseen`。
