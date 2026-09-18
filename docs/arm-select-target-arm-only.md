# Arm-Select：禁止先用错误手臂再换指定手臂

2026-09-18 修正成功判据为 `target-arm-only-lift-v2`。Cube-v3 的方块尺寸、
位置/旋转采样、配对指令、seed 清单和 400-action 预算保持原设置。

## 判定规则

物体当前相对 setup 后的静止高度抬升 **严格超过 5 cm**，且当前归属于指定手臂，
并且此前从未被非指定手臂抬升超过 5 cm，才算成功。

手臂归属沿用原判据：物体中心距该手臂 TCP **小于 20 cm**，且严格比另一臂 TCP 更近。
这仍是基于物理状态的归属估计，不依赖 oracle 的执行手臂标签，也不新增接触或夹爪闭合条件。
两个 TCP 等距时不归属于任一手臂。

| 行为 | 新判定 |
|---|---|
| 指定手臂直接拿起，满足高度和距离条件 | 成功 |
| 错误手臂拿起、放回桌面，再用指定手臂拿起 | 失败 |
| 错误手臂拿起后，在空中交给指定手臂 | 失败 |
| 错误手臂轻碰或轻抬，没有超过 5 cm，随后指定手臂拿起 | 成功 |
| 目标尚未抬起，或当前已放下 | 失败 |

旧实现仅检查查询时的 `lifted && arm_match`，丢失了此前使用错误手臂的历史。
此次修复前，在 left/right 两种指令下均复现“先错后对仍返回 True”。

[`ArmPickMonitor`](../tasks/envs/_if_grounding.py) 在每个真实 physics step 后观察高度和两臂距离。
一旦错误手臂满足拿起条件，就锁定 `wrong_arm_lifted_ever=true`，直到下一次 `setup_demo`。
动作内部的短暂错误抬升也会记录；放下、换手、再次执行 oracle、查询信号均不会清除此标记。
`setup_demo` 和 `close_env` 会解除旧场景的观察回调。

`eval_signals` 保留原 `arm_match`、`lifted` 和距离字段，新增 `checker_version`、`thresholds`、
`lifted_by`、`first_lifted_arm`、`wrong_arm_lifted_ever`、`first_wrong_arm_lift_action`、
`target_arm_only_success`。因此最后 `arm_match=true` 且 `lifted=true` 的回合仍可能因历史错误失败。
该判据应用于共享 `arm_select` 任务，旧几何配置也使用同样的历史检查。

## 历史结果

已经发布的 cube-v3 和 Attribute-v2 包中的 Arm/Overall 仍使用旧终态判据，保留原始字节与计数。
当前 [Arm-only-v2 结果](../result/robotwin-if-arm-only-v2-20blocks/README.md)已完成六个模型的 240 个 Arm 回合重跑；旧包仅保留在 Git 历史中。
[`run_formal_policy_suite.py`](../tools/run_formal_policy_suite.py) 为新计划固定新判据版本、
5 cm 抬升阈值与 20 cm TCP 阈值，拒绝将旧判据的 Arm 成功或失败记录混入新计划。
显式读取历史计划仍按原合同验证。

## 验证入口

2026-09-18 已完成 **4/4 组真实仿真与 76 项 CPU 回归**，见[验证包](../result/robotwin-if-arm-only-v2-20blocks/evidence/arm-target-only/README.md)。
两个方向均真实执行“错误臂拿起→放回→指定臂拿起”，最终仍失败；直接正确抓取的两个对照仍成功。
4 组初始观测逐数组匹配旧 cube-v3 同 seed 的观测。

CPU 回归覆盖左右臂、放下后再抓、空中换手、动作内子步、轻碰、严格阈值、
reset/close、oracle 不清空历史，以及旧成绩禁止复用。

```bash
python -m unittest discover -s tests/arm_select -p 'test_*.py' -v
python -m unittest discover -s tests -p 'test_formal*.py' -v
```

真实仿真验证脚本在同一配对场景的两个指令下分别执行“指定臂直接抓”和
“错误臂抓起→放回→退回→指定臂抓起”，全程用机器人动作驱动物体，不传送物体或手臂。
逐 physics step 记录信号，保存视频、阶段截图，并逐数组核对初始观测与已归档 cube-v3 的一致性。

```bash
CUDA_VISIBLE_DEVICES=0 PYTHONNOUSERSITE=1 \
  /home/xichen6/miniconda3/envs/RoboTwin/bin/python \
  tests/arm_select/verify_target_arm_only.py \
  --output /Data/robotwin-if/evaluations/arm-select-target-arm-only-v2-review-new
```

输出目录必须不存在。结果标记为 `diagnostic_only=true`，不能混入正式 policy 成绩。
