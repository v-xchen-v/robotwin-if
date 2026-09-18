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

## 发布与回归验证

[当前结果包](../result/robotwin-if-arm-only-v2-20blocks/README.md)包含按 v6 重新完成的
240 个 Bottle 回合；既有 seeds、成功和 policy failure 均保留。
正式计划固定 checker 版本与参数，旧判据、不同阈值及未完成 700-action 终态裁决的
pick 记录都不能复用为当前成绩。来源与原始产物校验见[发布溯源](release-provenance.md)。

CPU 回归入口：

```bash
python tests/bottle_verb/test_check_success.py
python -m unittest discover -s tests -p test_policy_terminal_verdict.py
python -m unittest discover -s tests -p 'test_formal*.py'
```

覆盖相对高度、三秒稳定窗口、旋转反向与累计角度、允许平移、四元数符号、reset/close、
末尾裁决、六个 evaluator 的最终状态落盘，以及禁止导入旧判据结果。
`tests/bottle_verb/fixtures/rotation-hold-traces.json` 保留四份带来源哈希的真实 pose 轨迹，
用于反复执行 CPU 回归；它们是判据诊断材料，不是正式 policy 分数。

早期 v3–v5 的单回合探测、补完预测 chunk 的回放脚本及部署流水账只保留在 Git 历史 `833d496` 中。
这些诊断曾绕过配对资格检查或使用提前成功规则，不能替代当前完整评测。
新评测按[统一入口](branch-delivery.md)执行，逐 seed 验证 oracle；无需运行历史诊断脚本。
