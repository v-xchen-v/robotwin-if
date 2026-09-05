---
status: reference
area: robotics / benchmark-design
created: 2026-08-31
tags: [instruction-following, task-design, verb, native-inventory, if-ext]
parent: "[[被测行为须在能力库内-IF避免塌成OOD]]"
---

# Native in-domain 动词清单（verb 任务选型参考）

> 用途：设计 IF 的 **verb / action** 任务时，被测动作必须在模型 repertoire 内（见 [被测行为须在能力库内-IF避免塌成OOD](被测行为须在能力库内-IF避免塌成OOD.md)）。这份是**只统计 native raw RoboTwin(50 个任务)实际演示过的动作**——从这里挑动词，才对"零样本 / 只在 raw 上微调"的模型是 in-distribution。
>
> 统计口径：`third_party/robotwin/envs/` 下的 **50 个 native raw** 任务（排除 robotwin-if 注入的软链：operate_stapler / operate_tabletop / pick_diverse_object / place_relative / grasp_cube / operate_mic_drawer / smoke_click_bell / laptop_verb）。

## 一、金矿：同一 asset 出现过多个动词（seen-vs-seen verb-select 直接候选）

做纯净的 verb-select，最好用**同一个物体**在**两个都见过**的动词下——这样 0 分只能归因于"没读动词"。native 里满足的 asset：

| asset | native 演示过的动词 | 出处任务 | 备注 |
|---|---|---|---|
| **001_bottle** | **pick / shake / adjust**（3 个） | `pick_diverse_bottles`、`pick_dual_bottles`、`shake_bottle`、`shake_bottle_horizontally`、`adjust_bottle` | ★ **首选**：3 个都在域内，pick(抓离桌) vs shake(握住晃) motor 差异大、视觉可分 |
| **048_stapler** | **press / move** | `press_stapler`、`move_stapler_pad` | ★ 次选（= 设计文档候选 C），press vs move 两向都 native |

其余 asset 基本只在**单一动词**下出现（如 041_shoe 只 place、002_bowl 只 stack、015_laptop 只 open），做不成同-asset 的动词对。

**建议**：纯净 seen-vs-seen verb-select → **`001_bottle` 的 pick vs shake** 首选，`048_stapler` 的 press vs move 次选。

## 二、Native in-domain 动词全表（19 类原语）

| 类 | 动词 | 代表任务 |
|---|---|---|
| 取 | pick / grab | `pick_diverse_bottles`、`pick_dual_bottles`、`grab_roller` |
| 举 | lift（双臂抬） | `lift_pot` |
| 放 | place / put / insert | `place_*`（15+）、`put_bottles_dustbin`、`put_object_cabinet` |
| 叠 | stack | `stack_blocks_two/three`、`stack_bowls_two/three` |
| 挂 | hang | `hanging_mug` |
| 移 | move / slide / push-away | `move_can_pot`、`move_pillbottle_pad`、`move_stapler_pad`、`move_playingcard_away` |
| 压 | press（原地下压） | `press_stapler` |
| 按 | click（按钮/顶部） | `click_bell`、`click_alarmclock` |
| 击 | beat / strike（带工具） | `beat_block_hammer` |
| 盖章 | stamp | `stamp_seal` |
| 转 | turn / rotate | `turn_switch`、`rotate_qrcode` |
| 开 | open（铰链/门，**仅开向**） | `open_laptop`、`open_microwave` |
| 拉 | pull（抽屉拉出） | `put_object_cabinet` |
| 晃 | shake | `shake_bottle`、`shake_bottle_horizontally` |
| 倒 | dump / pour（倾倒） | `dump_bin_bigbin` |
| 扫 | scan（过传感器） | `scan_object` |
| 交接 | handover（臂间传递） | `handover_block`、`handover_mic` |
| 调整 | adjust（重新摆位/朝向） | `adjust_bottle` |
| 排序 | rank / arrange（多物体排列） | `blocks_ranking_rgb`、`blocks_ranking_size` |

> 注：`place/put/stack/hang/insert` 本质都是"抓取 + 沉放"的变体，做动词**对比**时别用两个 place 变体互对（不构成真动词差异）；要挑 motor 上真正不同的两类（如 pick vs shake、press vs move）。

## 三、明确 OOD（native 零演示，做 native-model 的纯 IF verb 测试要避开）

- **close / fold / shut**——任何铰链/盖子的**闭合**方向：全 50 个任务里 open×2、close×0，没有任何 articulated 物体被驱动到闭合端。（这正是 `laptop_verb` 的 close 踩的坑。）
- 其他 native 没有的：twist/拧盖、unscrew、pour-into-窄口、wipe/擦、fold cloth/叠布、plug/插接、push（区别于 move 的推挤）等。

用这些当被测动词，对零样本 / native-ft 模型 = action-OOD → IF 会塌成 OOD 泛化。

## 四、怎么用（选型指引）

1. **verb-select（纯 IF）**：从"金矿"里选同-asset 两个 in-domain 动词（bottle pick/shake、stapler press/move）。两向都在 repertoire → 0 分可归因于动词。代价：无 laptop 那种数据支撑的强先验。
2. **要强先验**：只能回到"OOD 值（如 close）+ 在 ifext-ft 协议下评 / 改方向性判据 + 诚实标注为复合轴"，见 [被测行为须在能力库内-IF避免塌成OOD](被测行为须在能力库内-IF避免塌成OOD.md)。
3. **选型阶段就查**：候选动词逐一对照本表，不在表内的即 OOD；用 `/task-design-review <task>` 的第 5(action-OOD)、8(协议依赖)维度复核。

---
### 附录：50 个 native raw 任务 → (动词, 主物体)

| 任务 | 动词 | 主物体 |
|---|---|---|
| adjust_bottle | adjust | 001_bottle |
| beat_block_hammer | beat/strike | 020_hammer（击 block） |
| blocks_ranking_rgb / _size | rank/arrange | blocks |
| click_alarmclock | click | 046_alarm-clock |
| click_bell | click | 050_bell |
| dump_bin_bigbin | dump/pour | 011_dustbin → 063_tabletrashbin |
| grab_roller | grab/pick | 102_roller |
| handover_block | handover | block |
| handover_mic | handover | 018_microphone |
| hanging_mug | hang | 039_mug → 040_rack |
| lift_pot | lift | 060_kitchenpot |
| move_can_pot | move | 105_sauce-can → 060_kitchenpot |
| move_pillbottle_pad | move | 080_pillbottle |
| move_playingcard_away | move/push-away | 081_playingcards |
| move_stapler_pad | move | 048_stapler |
| open_laptop | open | 015_laptop |
| open_microwave | open | 044_microwave |
| pick_diverse_bottles / pick_dual_bottles | pick | 001_bottle |
| place_a2b_left / _right | place（左/右空间） | generic |
| place_bread_basket | place | 075_bread → 076_breadbasket |
| place_bread_skillet | place | 075_bread → 106_skillet |
| place_burger_fries | place | 006_hamburg,005_french-fries → 008_tray |
| place_can_basket | place | can → basket |
| place_cans_plasticbox | place | 071_can → 062_plasticbox |
| place_container_plate | place | container → 003_plate |
| place_dual_shoes | place | 041_shoe → 007_shoe-box |
| place_empty_cup | place | 021_cup → 019_coaster |
| place_fan | place | 099_fan |
| place_mouse_pad | place | 047_mouse |
| place_object_basket | place | object → basket |
| place_object_scale | place | object → 072_electronicscale |
| place_object_stand | place | object → 074_displaystand |
| place_phone_stand | place | 077_phone → 078_phonestand |
| place_shoe | place | 041_shoe |
| press_stapler | press | 048_stapler |
| put_bottles_dustbin | put | 114_bottle → 011_dustbin |
| put_object_cabinet | pull + put | 036_cabinet |
| rotate_qrcode | rotate | 070_paymentsign |
| scan_object | scan | 112_tea-box（过 024_scanner） |
| shake_bottle / shake_bottle_horizontally | shake | 001_bottle |
| stack_blocks_two / three | stack | blocks |
| stack_bowls_two / three | stack | 002_bowl |
| stamp_seal | stamp | 100_seal |
| turn_switch | turn | 056_switch |
