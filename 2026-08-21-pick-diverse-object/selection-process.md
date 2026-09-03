# Pick-Diverse-Object：Seen / Unseen object 挑选过程

> 日期：2026-09-03  
> 状态：production pools 已锁定并通过真实 SAPIEN 验证。  
> 目的：保留从 taxonomy 到 exact-variant admission 的可审计路径；closeout 后不再保留一次性失败实验的 raw/debug artifacts。

## 1. Taxonomy 与 production pool 是两层概念

1. **Object-familiarity taxonomy**：120 个 numbered asset categories 中，哪些属于 raw-task Seen / Unseen。
2. **Production pool**：从 taxonomy 中选择实际进入 Pick-Diverse-Object 的 noun 与 exact model ID。

进入 taxonomy 不等于进入 production。production 还要求真实 scene placement、双臂 grasp 和 target-specific lift-and-held evidence。instruction JSON 顶层 `seen/unseen` 仅表示 template split。

## 2. Object-familiarity taxonomy

定义：

- Raw-task Seen：first-commit `8187d5b` 的 50 个 native/raw task 文件引用过该 numbered category；
- Raw-task Unseen：没有被这些 raw tasks 引用；
- IF-Ext 是 eval-only，IF-added task usage 不会让资产变成 raw-task Seen。

复核步骤：重建 50 个 native task 文件集合，提取 numbered categories，与 assets 目录下全部 120 categories 做全集差分，并验证两组不相交且 union 为全集。

结果：**51 Seen + 69 Unseen = 120**。

## 3. Seen production pool

Seen 侧沿用历史 color+noun baseline 的 12 个语义清晰 nouns，再通过真实贴图 atlas 为每类锁一个 raw-task exact-ID-reachable variant。

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

保留条件：category 为 raw-task Seen，exact ID 可被 raw-task 代码选择，真实 texture/geometry 的 noun 明确，并通过更新后的 production regressions。`phone/base1` 使用 native standing quaternion `(0.5, 0.5, 0.5, 0.5)`。

边界：这是人工挑选的 12-category 子集，不代表全部 51 类 Seen 的无偏样本；最终 20-success collection 先于 Seen exact-ID 重选，所以其中 Seen episodes 不证明当前 12 个 exact IDs。

## 4. 从 69 类 Unseen 建立 metadata shortlist

一个 exact variant 进入原始 shortlist 必须同时具备 rigid visual/collision GLB、`stable=True`、nonempty valid contact group/mask。

| Candidate noun | Asset | Qualified IDs |
|---|---|---|
| drill | `030_drill` | 6 |
| shampoo bottle | `049_shampoo` | 1,2,3,4,5,7 |
| candlestick | `051_candlestick` | 0,1,2,3 |
| dumbbell | `052_dumbbell` | 0,2,4,6 |
| speaker | `055_small-speaker` | 1,2 |
| pencil cup | `059_pencup` | 0,1,2,3,4,5,6 |
| drink bottle | `068_boxdrink` | 2,3 |
| wooden mallet | `084_woodenmallet` | 3 |
| globe | `089_globe` | 2,3 |
| trophy | `090_trophy` | 0,1,2,3,4 |
| glue bottle | `095_glue` | 0,1,2,4,5,6 |
| milk tea | `101_milk-tea` | 0,1,2,4,6 |
| hydrating oil | `109_hydrating-oil` | 0,1,2,5 |
| hand bell | `111_callbell` | 1,2,3,4,5 |

总计 **14 nouns / 54 exact variants**。完整真实贴图 contact sheet 保留在 `evidence/pool/snapshots_unseen-candidates.png`。

Metadata 只决定“值得 probe”，不证明 settle、reachability、physical hold 或四物体 coexistence。

## 5. 真实贴图与 noun 审核

所有 variants 使用真实 baseColor texture + geometry 渲染。人工审核修正：

- `068_boxdrink`：drink carton → **drink bottle**；
- `111_callbell`：call bell → **hand bell**；
- `093_brush-pen/base1`：→ **paintbrush**。

缩略图只证明视觉可审阅性，不是 grasp admission evidence。

## 6. Exact-variant probe pipeline

1. **Quick sweep**：54 variants 各至少一次真实 target trial。
2. **Cross-arm screen**：quick success 的 variant 测 opposite arm。
3. **Independent confirmation**：fresh seeds，避免单次幸运成功。
4. **Production coexistence**：进入最终 all-Unseen scene。

每次记录 noun/asset/model ID、raw seed、requested/actual arm、setup/settle、scene poses、workspace/motion、oracle、target z-rise、noun-only instruction 和 failure stage，并逐 trial 增量写 JSON/CSV。

Admission gate 固定为：confirmation ≥70%，左右臂各至少一次真实成功，并能稳定参与 production scene。不因缺第四类而降门槛。

## 7. 原 14 类的结果

通过 independent confirmation：

| Noun | Exact variant | Result |
|---|---|---:|
| dumbbell | `052_dumbbell/base0` | 6/6；L 3/3，R 3/3 |
| speaker | `055_small-speaker/base1` | 6/6；L 3/3，R 3/3 |
| wooden mallet | `084_woodenmallet/base3` | 6/6；L 3/3，R 3/3 |

主要 false positives：trophy/base3 由 quick 3/4 回归为 confirmation 0/4；trophy/base4 2/6；glue/base2 2/6；glue/base6 1/6；candlestick/base2 2/6；hand-bell variants ≤4/6；drink-bottle/base2 的 fresh contact-ID confirmation 2/6。

结论：contact pose 可规划、isolated reachability 和 quick success 均不能替代真实执行后的 grasp-and-hold confirmation。

## 8. Manual follow-up 找到第四类

原 shortlist 只有三类通过，因此单独检查 stable 且有 contact poses、但 group/mask 为空的 notebook 与 paintbrush：

| Noun | Asset / IDs | Result |
|---|---|---|
| notebook | `092_notebook/base0,1,2` | rejected |
| paintbrush | `093_brush-pen/base0,1,2,4,5` | base1 5/6；L 2/3，R 3/3 |

两类均显式使用 `contact_point_id=0`，没有修改 third-party metadata。该 inventory 与原 14/54 shortlist 分层保留。证据包括 `evidence/unseen_confirm_paintbrush_b1.json` 和 `evidence/pool/snapshots_manual-candidates.png`。

## 9. 第一版四物体 coexistence（历史）

第一版 Unseen pool 为 dumbbell、small speaker、wooden mallet、paintbrush。真实 odd seeds `1,3,5,7,9,11,13,15` 的结果是 8/8 setup、8/8 settle、7/8 oracle；唯一失败为 paintbrush seed 7，seed 15 成功，因此四个 nouns 都至少有一次 target success。

`evidence/unseen_production_seeds_1_15.json` 作为首次 locked-pool coexistence 证据保留。Closeout 后旧 pool 不再作为 runtime manifest 存在，不能把这项结果描述为当前 Apple pool 的 production sweep。

## 10. 被淘汰的 replacement/candidate experiments

以下结论保留，但 one-off manifests、raw JSON/CSV、pose atlases、debug frames 和 experiment MP4 已在 closeout 删除：

| Candidate | Aggregate result | Decision |
|---|---|---|
| `098_speaker/base3` | confirmation 4/6；L 1/3，R 3/3 | 低于 ≥70%；未进 coexistence |
| Apple natural-pose screen | 0 个 pose family 达到严格 6/6；多数 conditional-on-setup stable，x-pos-up 有重复 tilt/drift | 不按失败后结果挑 pose |
| Apple y-pos radius-first | Gate A 5/6；fixed seed packing failure | 不补 seed；停止 admission gates |
| Apple post-gate exploratory grasp | 5/6 overall；5/5 attempted | 仅描述性，不能改写 failed packing gate |
| perfume/base1 | native grasp 1/2 | 用户决定放弃；base2 未继续 grasp |
| toothpaste/base0 | baseline native grasp 0/2；pose-only 未形成双臂可靠候选 | rejected |
| whiteboard eraser/base0 | baseline native grasp 0/2；随后明确放弃 | 不做 contact-frame tuning |
| tissue-box/base4 | 一路 planner target pose failure；一路 z-rise 0，视频显示 miss/push distractor | rejected |

这些实验说明最终 pool 不是“所有日常 Unseen objects”中的随机样本，而是通过当前 embodiment/oracle feasibility screen 的 survivors。

## 11. Apple 最终 promotion 是独立 production 决策

用户明确要求 Apple 替换 speaker，而不是 dumbbell。最终顺序直接声明为：

1. dumbbell — `052_dumbbell/base0`
2. apple — `035_apple/base1`
3. wooden mallet — `084_woodenmallet/base3`
4. paintbrush — `093_brush-pen/base1`

早期 Apple y-pos/native-side-grasp 视频显示侧放、侧抓，不符合任务视觉可读性。最终 Apple 配置改为：z-up、full world-z yaw、四个 body-centered top-down contacts、`pre_grasp_dis=0.08`、radius 0.055。actor config 从 native metadata deep-copy，source JSON 不改。

固定 12-scene gate：left 5/6、right 5/6、overall 10/12；十次成功均 lift-and-held且 approach-axis world-z 接近 `-1.0`，两次失败均为桌面后缘 planner failure。

## 12. 正常 20-success collection

使用正常 `collect_data.sh pick_diverse_object pdo_apple20 0`，无 familiarity-only scheduler。

- accepted raw seeds：`1,2,3,4,5,6,8,9,10,11,12,13,14,15,16,17,18,20,21,22`；
- failed：`0,7,19`；
- successful composition：11 Seen / 9 Unseen；
- 20 trajectory、HDF5、H.264 MP4、instruction JSON、scene-info records 均生成并可读。

Apple 在 9 个 Unseen scenes 全部 z-up；episode 2/raw seed 3 与 episode 9/raw seed 11 是 target，均 top-down grasp、lift-and-held。final MP4、16-frame sheets 和 9-scene initial sheet 保留在 `evidence/videos/apple-zup-topgrasp/`。

这证明 scripted oracle 与 native collection pipeline，不是 VLA score。Apple 右臂能力来自 fixed gate，不从两个左臂 target videos 推断。

## 13. 最终证据与 source of truth

Production source：

- `tasks/envs/_pick_diverse_object_pool.py`
- `tasks/envs/pick_diverse_object.py`

保留的选择/物理 evidence：

- `evidence/unseen_confirm_round3.json`
- `evidence/unseen_confirm_paintbrush_b1.json`
- `evidence/unseen_production_seeds_1_15.json`
- `evidence/pool/snapshots_unseen-candidates.png`
- `evidence/pool/snapshots_manual-candidates.png`
- `evidence/videos/apple-zup-topgrasp/`

Reusable tools/tests：

- `tools/probe_pick_diverse_unseen.py`
- `tools/render_pick_pool_snapshots.py`
- `tests/pick_diverse_object/`

## 14. 解释边界

1. Seen pool 是 51 类中的人工 12-category 子集。
2. Unseen pool 是 69 类中通过 feasibility screen 的四个 survivors。
3. 两边类别多样性不对称。
4. 每个 Unseen episode 都出现相同四类。
5. Seen/Unseen 为独立、组内同质场景；gap 同时包含 target、distractor、geometry 和 clutter 差异。
6. 因而只能称 **scene-level object-familiarity gap**。
7. 应同时报告 group micro、per-noun macro、exact variants 和 tried/kept composition。

## 15. 复现当前长期接口

```bash
python tests/pick_diverse_object/test_pool.py
python tests/pick_diverse_object/test_probe_logic.py
python tests/pick_diverse_object/test_instructions.py
python tests/pick_diverse_object/test_reporter.py

conda run --no-capture-output -n RoboTwin \
  python tests/pick_diverse_object/test_wiring.py
conda run --no-capture-output -n RoboTwin \
  python tests/pick_diverse_object/test_apple_top_grasp.py
conda run --no-capture-output -n RoboTwin \
  python tests/pick_diverse_object/test_check_success.py

# Retained exact-candidate interface
conda run --no-capture-output -n RoboTwin \
  python tools/probe_pick_diverse_unseen.py \
  --phase grasp --variants "paintbrush:1" \
  --arms left right --repeats 3 --output /tmp/paintbrush-confirm.json

# Current production-seed interface
conda run --no-capture-output -n RoboTwin \
  python tools/probe_pick_diverse_unseen.py \
  --phase grasp --production-seeds 1 3 5 7 9 11 13 15 \
  --output /tmp/unseen-production.json
```

任何后续 pool 改动都必须重新通过相同 admission gate；不能只改 manifest 或凭缩略图加入 production。
