# Bottle-Verb：相对抬升与稳定保持判定

2026-09-15，根据视频复核反馈修复 pick 的两类错误：低幅抬起被判失败，以及摇晃过程中被判 pick 成功。
旧代码位于 git `bf25bc3` 的 `tasks/envs/bottle_verb.py`；它只要求历史最高 z 超过
`0.95 + table_z_bias`。因此不需要在终态继续拿着，也不需要稳定；摇晃跨过高度线就会通过。
RoboTwin 每个物理步检查 success，并在首次 True 时锁定成功、提前结束，单纯降低高度线会加重第二个问题。

## 当前判定：v6，完整动作预算后裁决

当前版本为 `relative-lift-hold-v6-terminal`。用户在复核 X-VLA seed 100002 后确认：
**pick 跑满本回合预算后判定；拿起后允许 translation，主要排除旋转摇晃（rot）。**
阈值在 [`PickHoldRules`](../tasks/envs/_if_bottle_verb.py)，接线在
[`bottle_verb.py`](../tasks/envs/bottle_verb.py) 与 [`policies/evaluation.py`](../policies/evaluation.py)。

| 条件 | 默认值 / 行为 |
|---|---|
| 判定时点 | pick 的第 700 个动作完整执行结束后；中途稳定不提前终止 |
| 相对抬升 | 最近保持窗口内始终 ≥ 3 cm，相对于 setup 后瓶子的静置高度 |
| 平移 | 允许；不设位置半径、累计位移或平移往返否决 |
| 末尾姿态保持 | 连续 ≥ 3 秒仿真时间；期间 policy 正常执行 |
| 姿态容差 | 最近 3 秒内各采样姿态距窗口起点 ≤ 10°，允许轻微物理抖动 |
| 小幅高频旋转 | 保持段最近 3 秒累计转角 > 135° 时，否决本回合 pick |
| 明显旋转往返 | 首次抬升后，同一世界轴旋转分量累计 ≥ 2 次有效反向，单次须达到 10°，否决本回合 pick |
| 轨迹采样 | 50 Hz 仿真时间；推理等待、查询频率、视频时长不计入 |

超过姿态容差或掉回抬升线以下会重新计满 3 秒。旋转摇晃一旦触发否决，之后即使重新稳定也不能成功。
单次转向后稳定可以成功；平移或纯线性往返本身不再作为 pick 摇晃证据。最终还须通过原有配对 oracle gate。
这些是明确的任务判定容差，并不声称能够识别任何小于阈值的旋转或根据轨迹判断模型意图。

三秒是**末尾稳定窗口**，不是整个观察窗口。模型在整个 700-action 预算内持续执行，
“先稳定三秒，再摇晃”的后半段不再因早停而丢失。预算外的未来行为不属于这次评测。
shake mode 保持原 `累计 |Δz| ≥ 0.30 m` 及提前成功行为；此次未改变 shake 的定义。
因此纯平移的往返可能满足旧 shake 规则，也可能符合用户新确认的 pick 规则，这是两套条件的明确边界。

旋转检测使用相邻四元数的有符号世界轴旋转增量，累计后分别跟踪三个轴的反向；
不再只检查“距首次姿态的无符号夹角”，避免换一个轴摇晃时夹角几乎不变的盲区。
初始化反向检测时跟踪峰谷范围，避免从波形中点开始采样、正负两侧各自未过阈值就永远检测不到。
四元数 q / -q 等价，不使用有 ±180° 跳变的 Euler 角作判定。

## 时钟、终态、oracle 与诊断

只在 Bottle-Verb 场景实例上观察 `scene.step()`，物理步后累加 `get_timestep()` 并读取 pose；
关闭或重建环境恢复该实例的原始 step。监测器在物体静置之后初始化。
保持窗口采用滚动三秒的运动量，避免长回合里的正常微抖因为“累计一辈子”而周期性失败。
位置路程只作诊断，不参与成功条件。

公共 `setup_episode` 在 oracle 资格检查后的 policy reset 调用 `start_policy_rollout()`。
pick 的 `check_success()` 在 rollout 内始终 False，所以第 700 个动作内部也不会半途锁定成功。
六个 evaluator 均在正常循环结束后调用 `finalize_episode_success()`，再生成结果、summary 和视频文件名。
最终成功回合的 `termination=action_limit`，因为它是在预算用完后通过。执行异常仍是 error，不能拿已有的
候选 hold 充当 success；其他任务继续使用原来的提前成功方式。

oracle / collection 不受 policy 的末尾裁决限制；pick oracle 提起轨迹保持不变，最后保持 3.25 秒真实物理时间。
配对 scene qualification 保留，新规则下 oracle 失败仍然保留原 seed、报告 setup error，不能换 seed。
`eval_signals()` 输出版本、阈值、轴名/反向次数、旋转检测时间，以及 `pick_verdict_protocol`、
`pick_verdict_finalized`、`pick_final_success` 和动作计数。`pick_success` 是物理保持候选，
只有完成 budget 后的 `pick_final_success` 才是 policy 的最终裁决。

## 历史结果与复用

当前 README 与 [v6 结果包](../result/if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/README.md)
已使用完整重测的 Bottle-Verb 分数和重算的 Overall，六个 policy 均完成 20/20 blocks。
旧判定结果包、五模式/三模式历史证据独立保留，原标签不改写。
原始视频不是精确的仿真时钟，既有动作 NPZ 也不包含完整瓶子 pose 序列；旧成功回合还会在旧高度线处
提前结束，缺失之后的保持过程，因此不能简单对旧 CSV 改几个阈值就可靠得到新结果。

新的正式 `prepare` 将版本及阈值写进 task spec。复用、导入和断点恢复时检查这两个字段；
旧 Bottle-Verb 记录或阈值不一致的记录不能当作新结果复用，排除列表写入
`support/excluded-checker-reuse.json`。原 20 个 paired blocks 和 seed 不变，默认重新评测 Bottle-Verb
的 40 回合/policy（六个 policy 共 240 回合）；其他任务可以按各自原契约复用。
新 oracle 仍须逐 seed 通过资格检查，失败不会偷偷换 seed。旧计划仍可按历史口径校验。

## 验证

`python tests/bottle_verb/test_check_success.py` 为 CPU 回归入口，覆盖低幅抬起、桌高偏移、
放回桌面、短暂停顿、位置/姿态小抖动、三种明显摇动、容差内高频运动、单次姿态调整、
高幅单调提起、四元数符号、重复查询、时步变化、时钟/pose 无效输入，以及 task reset/close/pair gate。

以下 SAPIEN / 机器人实测记录来自首版 `relative-lift-hold-v3`（1 秒），保留为历史证据，
不能当作 v4 的三秒资格检查或新 policy 分数。

真实 SAPIEN CPU scene 另验证了实例 step 观察函数、时间推进和四种输入轨迹：
低幅抬起通过；高位纵向摇动、横向摇动、旋转摇动均未触发首次成功。
该检查使用运动学物体，验证时钟及判定接线，不替代机器人抓取的 oracle 验证。
输出在 `outputs/policy-eval/bottle-pick-hold-validation/cpu-scene-validation.json`。

真实机器人 oracle 的串行诊断入口为 `tests/bottle_verb/probe_pick_hold.py`，会保存原始 pose 轨迹与判定信号；
它只验证单个 seed 的 raw 谓词，配对 seed 需要另测，不隐式创建第二个 renderer。

2026-09-15 在 GPU 0 串行运行三个真实机器人 oracle 检查（`demo_clean`），结果如下。
轨迹按 50 Hz 保存，并检查整个过程是否曾触发 pick 成功，避免只看终态漏掉提前锁定的错误。

| 检查 | Seed | 实际终态抬升 | 终态稳定时长 | pick 曾成功 | 对应模式 raw success |
|---|---:|---:|---:|---|---|
| 原 pick oracle（指令抬升 20 cm） | 100002 | 17.93 cm | 1.32 s | 是 | 是 |
| 低幅 pick（诊断覆盖指令抬升为 6 cm） | 100002 | 4.14 cm | 1.40 s | 是 | 是 |
| 原 shake oracle | 100003 | 7.71 cm | 0 s | 否 | 是 |

三次 `plan_success` 均为 True。低幅 pick 全程未达到旧 `z > 0.95` 高度线，新规则能够接纳；
shake 最长稳定段为 0.68 s，7.76 s 时检测到明显往返，纵向累计移动 36.71 cm，原 shake 规则仍通过。
这是同一场景的一组配对 seed，分别验证 raw 谓词；没有执行包含第二环境的完整 pair-gate 流程，
也没有运行六个模型或全部 20 blocks，不能据此声称所有 seed 均已重新资格验证。

输出目录为 `outputs/policy-eval/bottle-pick-hold-validation/`，其中三个 `oracle-*/` 子目录保存
`result.json` 和 `trajectory.json`；`validation-summary.json` 汇总结果与文件哈希。
检查结束后两张 GPU 显存均回落到 16 MiB，未留下模拟器或模型服务。

自动检查结果：Bottle 判定、正式结果复用、公共评测 setup 和步数限制共 **55 项通过**；
task manifest inventory **52 项通过**；bridge、交付和结果范围测试 **34/35 项通过**。
剩余一项是本地既有 RoboTwin checkout 与锁定提交不一致：期望 `0aeea2d`，实际 `b82ffb8`，
导致严格版本检查拒绝；此次未更改其 revision 或本地配置。兼容 API 的 bridge 已检查并添加新 helper 链接。

## 六个 policy 的 1 秒版试跑（2026-09-15 启动后暂停）

用户确认后，新建运行 `if-six-tasks-spatial3-bottle-hold-20blocks-001`。
完整目录为 `/Data/robotwin-if/evaluations/if-six-tasks-spatial3-bottle-hold-20blocks-001`，
repo 内可从 `outputs/policy-eval/if-six-tasks-spatial3-bottle-hold-20blocks-001/` 访问。

- Bottle-Verb 原 20 paired blocks、40 seeds 全部保留；六个 policy 共重跑 240 回合。
- 其余五项的 2520 回合已按原文件哈希复制；旧 Bottle 240 回合已列入排除清单。
- 模拟器 GPU 0，模型服务 GPU 1；单 simulator、单 server 串行执行。
- 顺序：X-VLA、LingBot-VA、LingBot-VLA、VLAct All、DM05、Hy-VLA。
- 实时进度读运行目录的 `status.json` / `report.md`，运行日志为 `runner.log`；不要把复用回合计作新完成。

这次运行冻结的是 v3 / 1 秒的源码与阈值；期间改动任务/evaluator/runner 会触发来源校验并停止，
不允许一个运行中混入不同判定。普通 policy failure 保留；基础设施错误停止队列，原 seed 不替换。

`support/launch-and-export.py` 在完整评测及校验通过后调用 `support/finalize-results.py`，
生成 `result/if-ext-v2-six-tasks-spatial3-bottle-hold-20blocks/` 并更新 README 的 Verb、Overall 表格。
导出前核对新 Bottle 240 回合的判定版本，以及其他任务与旧结果完全一致；旧结果包保留。
若 README 的待替换结果片段被并行修改，导出脚本会保留新结果包并停止覆盖 README，记录到 `publication.json`。

用户随后要求暂停，并指出 pick 需要多等待几秒以发现稍后发生的摇晃。所有评测及模型进程均已退出，
没有继续执行自动导出。停止后回收已写完但尚未入库的回合，共保留 X-VLA 的 **3 个 v3 回合**，
其余 **237 回合未完成**。冻结的运行记录和视频保留，不能将其中的 1 秒判定结果并入 v4。
恢复新判定评测时需要新运行目录；当前队列保持 `paused`，不会自动续跑。

## 延长至三秒（v4）

只延长连续稳定窗口（1 → 3 秒），高度、位姿容差、累计运动预算和明显往返检测保持原值。
等待期间继续执行 policy 动作并监测物理运动，不是让机器人冻结或暂停推理三秒。
未满三秒发生超容差移动时，从新姿态重新计满三秒；明显摇动触发后，随后暂停也不恢复成功。
因此“先稳定拿起 1.6 秒、再开始摇晃”不会被早早判为 pick 成功。

判定版本及参数均参与正式结果复用检查，v3 的 1 秒成功/失败记录会被排除。
pick oracle 的保持阶段读取同一个参数，自动延长到 3.25 秒。
新增回归覆盖完整三秒边界、第三秒内移动重置、先停顿后摇动，以及 1 秒结果不可复用。
判定、正式复用/恢复、公共评测 setup 与步数限制共 **60 项 CPU 测试通过**。
本次保持 GPU 评测暂停；v4 的完整机器人 oracle / 六 policy 重跑尚未执行。

## v4 启动前检查：累计运动预算（2026-09-15）

用户要求按三秒版重新跑、丢弃之前结果后，旧 1 秒试跑标记为 `discarded`，新建
`/Data/robotwin-if/evaluations/if-six-tasks-spatial3-bottle-hold3s-20blocks-001`。
新计划锁定 v4 / 3 秒，Bottle 无复用 seed、待跑 240 回合；其余任务 2520 回合已复制并校验。

启动模型前串行执行了真实机器人低位 / 标准 pick 检查，二者 `plan_success=True`，
但现有 4 cm 累计路程预算不断重置保持时间。没有明显往返摇动；例如低位轨迹在距离保持起点
仅 1.7 mm 时，因这段累计移动刚超过 4 cm 被重置。这说明延长时间但不调整总预算，会更严地
限制物理抖动。CPU 合成测试通过不代表真实物理轨迹满足三秒规则。

| 保存的真实轨迹 | 实际终态抬升 | v4 最长稳定段 / 结果 | 候选同比预算最长稳定段 / 结果 |
|---|---:|---|---|
| 低位 pick，seed 100002 | 3.90 cm | 1.60 s / fail | 3.44 s / success |
| 标准 pick，seed 100002 | 17.72 cm | 1.26 s / fail | 3.06 s / success |

候选仅把三秒内累计预算从 4 cm / 45° 调整到 12 cm / 135°，维持原来每秒允许的累计运动量。
相对于本段保持起点的 1.5 cm / 15° 容差、三秒连续要求和明显往返否决不变。
上述候选结果为同一份保存 pose 轨迹的 CPU 重放，未重跑机器人、未修改正式判定参数。
保存的真实 shake 轨迹和七个合成用例也检查了该候选：稳定低位拿起 / 小幅抖动可通过，
先停顿再摇动、纵向 / 横向 / 旋转摇动、容差内高频往返均未触发 pick 首次成功。

原始结果、pose 轨迹及对比在 `outputs/policy-eval/bottle-pick-hold3s-validation/`。
由于候选会改变用户刚确认的评分参数，已提出选择；新队列状态为 `awaiting_checker_decision`，
模型评测尚未启动（0/240），两张 GPU 均已释放。旧试跑的 3 个回合不进入这轮评分。

## 用户确认后的正式版本（v5）

用户确认“开跑”后，采用上述同比累计预算：3 秒内 12 cm / 135°；3 秒连续保持、
1.5 cm / 15° 位姿容差、相对抬升 3 cm 及明显往返否决保持不变。
`relative-lift-hold-v5` 将全部阈值写入结果，新旧版本及不同预算的结果不可混用。
CPU 回归共 **61 项通过**，包括恢复原小幅抖动幅度的三秒用例，以及姿态容差内的高频旋转仍不能通过。

正式运行目录为 `/Data/robotwin-if/evaluations/if-six-tasks-spatial3-bottle-hold3s-20blocks-002`，
repo 内入口为 `outputs/policy-eval/if-six-tasks-spatial3-bottle-hold3s-20blocks-002/`。
原 1 秒试跑与 v4 预检计划均已标记作废，Bottle-Verb 从 **0/240** 开始；其他五项复用 2520 回合。
每个 policy 的 40 个 Bottle seed 保持原值，不挑选或替换失败 seed。

采用单模拟器 GPU 0、单模型服务 GPU 1，依次运行 X-VLA、LingBot-VA、LingBot-VLA、VLAct All、DM05、Hy-VLA。
完成且通过正式校验后，自动导出 `result/if-ext-v2-six-tasks-spatial3-bottle-hold3s-20blocks/`，
更新 README 的 Verb / Overall。进度以新目录的 `status.json` / `report.md` 为准；此前三个 v3 回合不计入。

已用 v5 重跑真实低位 pick oracle（seed 100002，指令抬升 6 cm）：实际抬升 3.86 cm，
稳定 3.38 秒，首次通过时稳定时长为 3.00 秒，plan/raw success 均为 True。
保持段累计路程 6.97 cm、姿态变化 27.23°，未检测到明显摇晃。
结果与轨迹见 `outputs/policy-eval/bottle-pick-hold3s-v5-validation/oracle-low-pick-100002/`；
此单 seed 检查不替代完整 paired qualification，正式 worker 在每个新回合开始前照常检查。

## v5 误判证据与 v6 修正（2026-09-15）

用户指出：
`outputs/policy-eval/if-six-tasks-spatial3-bottle-hold3s-20blocks-002/xvla/bottle_verb/bottle_verb_ep100002_1.mp4`
已有旋转摇晃，却被判 pick 成功。原始 summary 记录 106 个动作、3.00 秒保持、往返计数全为 0。
已保存原视频、动作、result / summary 的 SHA-256 到该运行的 `support/pick-false-positive-review.json`。

该回合最后一次预测完整保存到第 120 个动作，但只执行到第 106 个动作就停止。
解析已保存预测，左手腕目标 roll 在第 102 个动作约 +22.1°，第 111 个动作约 +0.3°，
第 120 个动作约 −23.4°。**107–120 是未执行的预测，不是原视频里已经发生的瓶子运动**；
它说明稳定窗口可能恰好落在摇晃转折点，不能据此可靠地给整回合提前判成功。

诊断脚本 [`replay_pick_hold.py`](../tests/bottle_verb/replay_pick_hold.py) 不启动模型服务，
只用单个 simulator 重放已保存动作；可选择补完未执行的预测后缀，并关闭诊断的成功早停。
它绕过配对 oracle gate，仅用于 raw 谓词分析，不能导入正式分数。
两次重放的初始三路图片及 proprio 与原记录完全一致，但运动规划时序出现差异：
106 个动作重放为 29.52 秒仿真时间，原记录为 40.46 秒。不能把重放当作原始物理轨迹的精确恢复。

证据目录：`outputs/policy-eval/bottle-pick-hold3s-v6-validation/`，包括原动作重放、
补完 120 个预测动作的重放及 `cpu-replay-comparison.json`。在当前 v6 阈值下，补完后缀的保存轨迹
末尾不满足三秒姿态保持；它没有跑满 700 个动作，不能标为新版正式 policy success/failure。

v5 队列当时暂停，保留 **15 个 X-VLA 回合**作历史诊断；新版分数在该阶段尚未生成。
运行与模型服务停止，不自动恢复。v6 的版本及参数与 v5 不兼容；正式导入还要求 pick 的 700-action
终态标记与计数完整，旧 15 回合和 raw probe 均不能计入 v6。下次评测需要新计划、新输出目录，
原 seed / mode 清单不变，其余五任务仍可按原规则复用。

### v6 验证范围

判定、正式结果版本/终态隔离、公共 setup、步数限制与六 runner 终态落盘共 **77 项 CPU 测试通过**，
其中六 runner 的参数化检查覆盖最终 success / failure 共 12 种情况；原六 policy client 回归 **43 项通过**。
覆盖末尾裁决、稳定八秒后再摇晃、摇晃后又停住、最后放下、持续平移、平移并旋转、轻微抖动长时间保持、
四元数符号/180° 边界，以及角度参考方向变化导致的旧漏检。

四份真实 pose 轨迹已裁剪到首次抬升附近，连同来源哈希保存到
`tests/bottle_verb/fixtures/rotation-hold-traces.json`，作为可重复的 CPU 回归证据。
低位 / 标准 pick 末尾保持通过，原 shake oracle 检出旋转往返，X-VLA 补完后缀的诊断轨迹末尾保持不通过。
姿态容差选择 10°：试验的 8° 会让保存的标准 pick oracle 在接触微抖中重置，而 10° 下该轨迹保持通过；
仍比 v5 的 15° 严格，旋转反向幅度也从 20° 收紧到 10°。

另外串行运行了一次真实 v6 低位 pick oracle，seed 100002：实际终态抬升 **4.02 cm**，
稳定 **3.88 s**，最近三秒累计转角 **10.41°**，plan / raw success 均 True，未检测到摇晃。
它是 raw 谓词验证，不是完整 paired qualification 或 700-action policy 分数。
输出为 `outputs/policy-eval/bottle-pick-hold3s-v6-validation/oracle-low-pick-100002/`。
该次诊断未恢复正式评测；验证结束后两张 GPU 均回落到 16 MiB。

## v6 X-VLA 前两个回合实测（2026-09-15）

用户要求只跑前两个 episodes 后，完成首个配对 block（100002 / 100003）：

| Seed | Mode | 结果 | Action calls |
|---|---|---|---:|
| 100002 | pick | Fail | 700 |
| 100003 | shake | Success | 149 |

两个 seed 的 paired oracle qualification 均通过。pick 在第 127 步检测到旋转往返，
仍完整运行到 700 步后裁决；终态抬升 8.90 cm，失败由旋转摇晃导致。
用冻结 v5 checker 重放这次实际记录的相同瓶子轨迹，旧逻辑仍会在第 106 步提前成功，
明确展示了提前终止怎样漏掉稍后的摇晃。shake 保持原规则，在垂直累计路程 0.300014 m 时成功。

运行、视频及位姿轨迹位于 `outputs/policy-eval/xvla-bottle-verb-v6-first2-001/`，
`support/v5-v6-same-trajectory.json` 保留对比，`support/validation.json` 保留视频帧数 / 动作数及哈希。
本次完成 2/2 episodes（1/2 success，0/1 全模式成功 block），未扩大到其他 seed 或 policy。
该两回合试跑结束时模型服务和模拟器退出，GPU 释放；随后启动的六 policy 正式重测结果见下一节。

## v6 六 policy 正式重测（2026-09-15）

用户确认扩大至六个 policy、每个 20 个 Bottle-Verb blocks。新计划位于
`outputs/policy-eval/if-six-tasks-spatial3-bottle-v6-terminal-20blocks-001/`，
实际目录为 `/Data/robotwin-if/evaluations/if-six-tasks-spatial3-bottle-v6-terminal-20blocks-001/`。
每个 policy 仍使用原有 40 个 seed（pick / shake 各 20），不替换失败 seed。

- 其他五任务的 **2520 回合**复制并逐文件校验，逐回合结果哈希与已发布三模式结果包一致，所有任务计数不变。
- X-VLA 首个 block 的 **2 个 v6 回合**已经按完整 policy 流程完成，核对源码、配置、manifest、checkpoint、推理参数及终态标记后导入；其余 **238 回合**进入串行队列。
- 旧 v3 / v4 / v5 Bottle 试跑不导入。新目录中 `origin=new` 表示相对历史发布包重新按 v6 评测的 Bottle 回合，包括这 2 个已完成回合；不表示它们是在本次队列启动后执行。

导入审计见 `support/warm-start-audit.json`、`support/compatible-v6-pilot/`，
其他任务复用审计见 `support/reuse-audit.json`；`status.json` / `report.md` 为当前进度。
初始状态为 **2522/2760 回合、601/720 blocks**；其中新版 Bottle 为 **2/240 回合、1/120 blocks**。

GPU 0 运行一个模拟器，GPU 1 运行一个模型服务；顺序为 X-VLA、LingBot-VA、LingBot-VLA、
VLAct All、DM05、Hy-VLA。保留温度、显存、日志停滞检测和源码冻结检查。
只有纯推理前 oracle 资格失败允许原 seed 在新模拟器中最多尝试三次；完成的 policy failure 不重试。

正式队列已于 **2026-09-15 22:44 UTC** 全部完成，视频帧数、动作轨迹、跨 policy 初始场景、
判定版本及参数校验均通过。`support/launch-and-export.py` 已自动导出
[v6 结果包](../result/if-ext-v2-six-tasks-spatial3-bottle-v6-terminal-20blocks/README.md)，更新 README 的 Verb / Overall。
其余五项的统计与记录哈希均与旧结果一致；`status.json` / `publication.json` 均为 `complete`。

| Policy | Pick 成功 | Shake 成功 | Bottle 成功 | 完成 blocks | 六任务 Overall (%) |
|---|---:|---:|---:|---:|---:|
| X-VLA | 0/20 | 20/20 | 20/40 | 20/20 | 37.1 |
| LingBot-VA | 0/20 | 20/20 | 20/40 | 20/20 | 60.9 |
| LingBot-VLA | 0/20 | 20/20 | 20/40 | 20/20 | 32.5 |
| VLAct All | 16/20 | 20/20 | 36/40 | 20/20 | 47.9 |
| DM05 | 20/20 | 20/20 | 40/40 | 20/20 | 61.8 |
| Hy-VLA | 0/20 | 20/20 | 20/40 | 20/20 | 35.2 |

新版 Bottle 共 **156/240 成功**；全套为 **2760/2760 回合、720/720 blocks**。
这些是自动判定结果；改动了成功规则，不能将与旧分数的变化归因于模型能力变化。
完整分模式计数及逐回合 CSV 见结果包；其他五项仍沿用历史自动标签，包括已注明的 Hy-VLA coffee-box 待人工复核记录。
