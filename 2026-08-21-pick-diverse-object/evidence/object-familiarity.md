# Pick-Diverse-Object object-familiarity evidence

Date: 2026-09-03  
Closeout status: final production evidence and reusable shortlist records retained; abandoned one-off experiment artifacts removed.

## Definition

- **Raw-task Seen**: numbered asset category referenced by one of the 50 native task files at first-commit `8187d5b`.
- **Raw-task Unseen**: numbered asset category absent from those files.
- IF-Ext is eval-only and creates no finetuning data; IF-added usage does not change raw-task familiarity.
- Instruction JSON keys `seen/unseen` split sentence templates and are independent of object familiarity.

The complete taxonomy is **51 Seen + 69 Unseen = 120 numbered categories**.

## Production pools

### Seen: 12 nouns / 12 exact variants

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

Exact thumbnails are under `pool/current-seen/`.

### Unseen: final four

| Noun | Exact variant | Physical evidence | Configuration |
|---|---|---:|---|
| dumbbell | `052_dumbbell/base0` | 6/6; L 3/3, R 3/3 | radius 0.105 |
| apple | `035_apple/base1` | 10/12; L 5/6, R 5/6 | z-up, full z-yaw, four body-centered top contacts, radius 0.055 |
| wooden mallet | `084_woodenmallet/base3` | 6/6; L 3/3, R 3/3 | radius 0.100 |
| paintbrush | `093_brush-pen/base1` | 5/6; L 2/3, R 3/3 | explicit contact ID 0, radius 0.080 |

Apple replaces speaker, not dumbbell. The current `UNSEEN_POOL` is declared directly; there is no runtime historical replacement pool.

## Retained metadata shortlist

A raw-task-Unseen exact variant entered the original shortlist only if it had rigid visual/collision GLBs, `stable=true`, and a nonempty valid contact group/mask.

| Asset | Qualified IDs |
|---|---|
| `030_drill` | 6 |
| `049_shampoo` | 1,2,3,4,5,7 |
| `051_candlestick` | 0,1,2,3 |
| `052_dumbbell` | 0,2,4,6 |
| `055_small-speaker` | 1,2 |
| `059_pencup` | 0,1,2,3,4,5,6 |
| `068_boxdrink` | 2,3 |
| `084_woodenmallet` | 3 |
| `089_globe` | 2,3 |
| `090_trophy` | 0,1,2,3,4 |
| `095_glue` | 0,1,2,4,5,6 |
| `101_milk-tea` | 0,1,2,4,6 |
| `109_hydrating-oil` | 0,1,2,5 |
| `111_callbell` | 1,2,3,4,5 |

Total: **14 nouns / 54 exact variants**. The retained contact sheet is `pool/snapshots_unseen-candidates.png`; individual images remain under `pool/unseen-candidates/`.

Visual review renamed `068_boxdrink` to **drink bottle** and `111_callbell` to **hand bell**. Historical JSON may contain the older names; raw evidence is not rewritten.

## Retained probe protocol

`tools/probe_pick_diverse_unseen.py` supports the reusable 14/54 shortlist plus notebook/paintbrush manual inventory. Candidate mode records:

- noun, asset, exact model ID, seed, requested/actual arm;
- setup and generic settle status;
- scene poses, placement order, pair separation and motion diagnostics;
- oracle exception/result, target z-rise and noun-only instruction target;
- optional H.264 video path/error.

Generic settle failure stops before oracle and remains in the fixed denominator. Production admission requires independent confirmation ≥70%, at least one success per arm, and all-Unseen scene coexistence.

## Canonical retained records

The following records remain useful for the shortlist audit and final lock:

- `unseen_quick_first_ids.{json,csv}` — first exact ID across all 14 categories and both arms;
- `unseen_quick_promising_variants.{json,csv}` — persisted partial exact-variant sweep;
- `unseen_quick_remaining_containers_{left,right}.{json,csv}` and `unseen_quick_remaining_shapes_{left,right}.{json,csv}` — remaining variants;
- `unseen_confirm_round2.{json,csv}` and `unseen_confirm_round3.{json,csv}` — strong-candidate confirmation;
- candidate-specific confirmation records for drink bottle, hand bell, trophy, glue and candlestick — rejected false positives;
- `unseen_quick_manual_candidates_{left,right}.{json,csv}` and `unseen_confirm_paintbrush_b1.{json,csv}` — manual follow-up;
- `unseen_production_seeds_1_15.{json,csv}` — first locked speaker-pool coexistence run.

The complete manual-candidate contact sheet is `pool/snapshots_manual-candidates.png`.

## Shortlist outcomes

| Exact variant | Result | Status |
|---|---:|---|
| `052_dumbbell/base0` | 6/6; L 3/3, R 3/3 | final production |
| `055_small-speaker/base1` | 6/6; L 3/3, R 3/3 | historical first lock; later replaced by Apple |
| `084_woodenmallet/base3` | 6/6; L 3/3, R 3/3 | final production |
| `093_brush-pen/base1` | 5/6; L 2/3, R 3/3 | final production via manual inventory |
| `068_boxdrink/base2` | fresh contact-ID confirmation 2/6 | rejected |
| `090_trophy/base3` | quick 3/4, confirmation 0/4 | rejected |
| `090_trophy/base4` | confirmation 2/6 | rejected |
| `095_glue/base2` / `base6` | 2/6 / 1/6 | rejected |
| `051_candlestick/base2` | 2/6 plus setup failure | rejected |
| `111_callbell/base4` | best repeated configurations 4/6 | rejected |

These failures establish that metadata-qualified contact poses and isolated planning do not guarantee executed grasp reliability.

## First locked-pool coexistence evidence

The historical speaker-containing pool ran odd seeds 1,3,5,7,9,11,13,15 with every override cleared:

- setup 8/8;
- settle 8/8;
- oracle 7/8;
- every target noun succeeded at least once.

The retained record is `unseen_production_seeds_1_15.json`. It proves the first four exact variants coexisted under production scheduling, but it is **not** a current Apple-pool sweep and no historical runtime manifest remains.

## Final Apple evidence

Production Apple uses `035_apple/base1`, z-up pose, full world-z yaw and four task-local body-centered top contacts. `_apple_top_down_actor_config()` deep-copies native metadata; `third_party/robotwin/assets/objects/035_apple/model_data1.json` is unchanged.

The fixed physical gate contains 12 frozen scenes with no replacement trials:

| Arm | Result | Failure characterization |
|---|---:|---|
| left | 5/6 | one rear-workspace planner failure |
| right | 5/6 | one rear-workspace planner failure |
| total | 10/12 | all ten successes lift-and-held |

All successful approaches had `abs(approach_axis_z) >= 0.90`, observed near 1.0.

### Normal 20-success collection

The normal `collect_data.sh pick_diverse_object pdo_apple20 0` run kept 20 of 23 tried raw seeds:

- accepted: `1,2,3,4,5,6,8,9,10,11,12,13,14,15,16,17,18,20,21,22`;
- failed: `0,7,19`;
- successful composition: 11 Seen / 9 Unseen;
- outputs: 20 trajectory PKLs, HDF5s, H.264 MP4s, instruction JSONs and scene-info records.

Apple appears z-up in all nine Unseen episodes. It is target in episode 2/raw seed 3 and episode 9/raw seed 11; ordered review confirms top-down closure around the body, lift and final hold.

Retained final files:

- `pool/snap_035_apple_b1_zup.png`;
- `videos/apple-zup-topgrasp/all-unseen-apple-initials.png`;
- `videos/apple-zup-topgrasp/seed3-episode2-left.mp4` and matching `*-frames16.png`;
- `videos/apple-zup-topgrasp/seed11-episode9-left.mp4` and matching `*-frames16.png`.

## Closeout-only historical conclusions

The following one-off artifacts were removed, but their aggregate conclusions remain part of the decision history:

- `098_speaker/base3`: confirmation 4/6 (L 1/3, R 3/3), below the fixed ≥70% gate;
- old Apple natural-pose families: no family reached strict 6/6; many executed scenes were stable, while x-pos-up repeatedly tilted/drifted;
- old Apple radius-first gate: 5/6 due one fixed-seed packing failure; exploratory grasp was 5/6 overall, 5/5 attempted;
- perfume/base1: native grasp 1/2, then abandoned;
- toothpaste/base0 and whiteboard-eraser/base0: baseline native grasp 0/2; pose-only follow-up did not yield a reliable candidate, and eraser was explicitly abandoned;
- tissue-box/base4: planner/contact failures and no lift-and-held success.

Current runtime intentionally does not reproduce these handcrafted candidate sets. No third-party metadata was changed.

## Interpretation boundary

This evidence validates scripted-oracle task wiring and native collection behavior. It does not report VLA performance. Seen and Unseen are independent homogeneous scenes, so `S_seen-S_unseen` includes target familiarity, distractor familiarity, geometry and clutter differences. The 11/9 successful collection composition must not replace the 50/50 raw-seed tried contract.
