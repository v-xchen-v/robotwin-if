---
status: sop
area: robotics / benchmark-design
created: 2026-09-01
tags: [instruction-following, task-design, sop, workflow, if-ext]
parent: "[[09-IF-Ext-单轴扩展任务集设计]]"
---

# IF 任务实现流水线 SOP（设计 → 接线 → 验证 → 量产 → eval）

> 一句话：一个单轴 IF 任务从想法到可 eval，走 **6 个阶段**；其中第 ③ 步「**seed / mode / instruction / check_success** 四件事一起接」是把「能跑对的 oracle」变成「真正的 IF 诊断」的**分界线**，且这四件必须**同源**——mode 由 seed 生、指令由 mode 渲染、check 读同一个 seed 派生的 mode。缺任何一个，任务就悄悄不再测 instruction-following。

配套：设计原则见 [[被测行为须在能力库内-IF避免塌成OOD]]；每阶段的门（gate）用 `/task-design-review`、spike harness、`/task-diag`、`/check-video` 这几个工具卡。

## 全流程（阶段 + 每阶段的门 + 产物）

### ① 设计校验（写实现代码前）
- **做什么**：跑 `/task-design-review` 的各维度，尤其 **action-OOD（被测行为在 repertoire 内吗）**、先验强度、度量选型（二元 vs 方向性）。定下：测哪个轴、哪几个 mode 值、用什么判据。
- **为什么在最前**：前提错了（如选了 native 从没演示的 `close`）建完 oracle 才发现最亏——「可以在错的靶子上执行得无可挑剔」是最贵的失败模式。
- **产物**：`notes/<date>-<task>/` 下 understanding / spec / decisions。

### ② Oracle spike（单模式可行性，退风险）
- **做什么**：最小 env，证明**每个 mode 值**的 oracle 都能从共享初始态 ~90%（风险值是重点，如侧抓、合盖）。
- **此阶段允许**：mode 用**全局开关（env var）**、位姿可先固定——只是证「动作做得出来」，还不是 IF。
- **产物**：`tests/<task>/spike_success_rate.py`（+ 需要时 `sweep_*.py`）+ 一个成功率数字。
- **门**：两个（或多个）mode 值都过 ~90%，否则回 ① 换靶子（参照 [[mic-drawer-oracle-infeasible]] 的教训：够不到的值让任务不可测）。

### ③ ▶▶ IF 接线（本 SOP 的核心步）——把 spike 变真 IF 任务
四件事**一起、同源**地接上：

| 件 | 接法 | 参照 |
|---|---|---|
| seed → 场景/模式 | `scene_seed = seed // 2`；`mode = values[seed % 2]` —— 让**同一场景成对**出现在每个 mode 下，policy 唯一能区分的只有指令 | `tasks/envs/laptop_verb.py:56-58` |
| instruction 模板 | 建 `tasks/task_instruction/<task>.json` 指令池（mode-word 槽，如 {V}/{approach}），`get_instruction()` 按 `seed//2` 取 | `laptop_verb.py:80-81` + `laptop_verb.json` |
| check_success | 读**seed 派生的 mode**（不是 env var），配 **pair-gate**（同场景两向都可演才算）+ **方向性/拆分判据** | `laptop_verb.py:164+` |

- **为什么在 spike 之后**：oracle 都达不到目标值，接指令/配对是白接。
- **为什么在采集之前**：这才让采出的数据真正「受指令条件约束」、eval 可成对读。
- **判断是否接好**：`check_success` 不再引用任何环境变量；seed 的奇偶能翻 mode；`<task>.json` 存在且措辞只在 mode 上变。

### ④ 验证（Layer A 结构 + Layer B oracle 正确性）
- **Layer A（结构/集成）**：跑得通；`/task-diag` 看 **seed→scene 映射符合设计**（成对？模式平衡？）、成功率。
- **Layer B（oracle 判定正确性）**：正例过 **且【反例必挂】**——给错 mode（该顶却侧）即使举起也 False。反例是验收必过项，不能省。
- **视频**：`/check-video` 抽帧视觉复核轨迹——度量看不见的扭腕、蹭桌、假抓。数值全绿 ≠ 轨迹自然。
- **产物**：impl-verify / negative-test-plan（notes/）。

### ⑤ 量产 + 接入
- **实采**：现在靠 **seed 出多个 mode**（不再跑两次 env）；`collect_data.sh <task> <config> <gpu>`。
- **接入**：`bridge_tasks.sh` 注入 submodule；接进 `all_tasks_plus_if.yml`；指令池洁净（措辞不泄 mode 之外的信息）。

### ⑥ Eval
- **只在 `zeroshot` / `native-ft` 下**——IF-Ext 是纯测试集、无 finetune data，**ifext-ft 永不在场**（[[ifext-eval-test-only]]）。
- **按 mode 分开报 + gap**，用方向性判据（不是二元平均）。没有 ifext-ft 兜底，所以任何被测行为的 OOD 都直接污染诊断——方向性判据是任务成立的前提，不是锦上添花。

## 一图记住顺序

```
① 设计校验(/task-design-review)  →  ② oracle spike(证两值都 ~90%)
        ↓  [退风险后才接线]
③ IF 接线【seed→mode→instruction→check，四者同源】 ← 分界线
        ↓
④ Layer A/B 验证(/task-diag + 反例 + /check-video)  →  ⑤ 量产+接 yml  →  ⑥ eval(zeroshot/native-ft, 报 gap)
```

## 常见「没接好」的征兆（=停在 ② 而非 ③）
- `check_success` 读的是环境变量 / 全局常量，而不是 seed 派生的 mode。
- 没有 `tasks/task_instruction/<task>.json`，指令文本根本没被生成。
- 一次运行只有单一 mode；`/task-diag` 显示「无 mode 轴 / 1 个 scene」。
- 顶/侧（或开/关）靠跑两次 env 切换，而不是 seed 的奇偶。

> 现况例：`grasp_cube_approach` 的 ①②③已完成（seed→mode→instruction→check 已同源接线，`tests/grasp_cube_approach/check_if_wiring.py` 验证 seed 偶→top/奇→side、指令 {D} 随 mode、两向 check 均真），下一步是 ④/⑤。`APPROACH` 降级为 harness 专用 override。见 [[grasp-approach-spike]]。（命名：这是 grasp-cube 家族里按**接近方向**分轴的那个；未来 texture/size 变体用 `grasp_cube_texture` / `grasp_cube_size`。）

## 参考
- 设计原则前提：[[被测行为须在能力库内-IF避免塌成OOD]]
- 主设计：[[09-IF-Ext-单轴扩展任务集设计]]
- 接线模板任务：`tasks/envs/laptop_verb.py` + `tasks/task_instruction/laptop_verb.json`
