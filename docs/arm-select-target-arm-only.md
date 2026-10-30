# Arm-Select：禁止先用错误手臂再换指定手臂

成功判据标识为 `target-arm-only-lift-v2`。场景使用 5 cm 方块，在双臂共用区域随机平移和旋转；配对场景相同，动作预算为 400。

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

[`ArmPickMonitor`](../tasks/envs/_if_grounding.py) 在每个真实 physics step 后观察高度和两臂距离。
一旦错误手臂满足拿起条件，就锁定 `wrong_arm_lifted_ever=true`，直到下一次 `setup_demo`。
动作内部的短暂错误抬升也会记录；放下、换手、再次执行 oracle、查询信号均不会清除此标记。
`setup_demo` 和 `close_env` 会解除旧场景的观察回调。

`eval_signals` 保留原 `arm_match`、`lifted` 和距离字段，新增 `checker_version`、`thresholds`、
`lifted_by`、`first_lifted_arm`、`wrong_arm_lifted_ever`、`first_wrong_arm_lift_action`、
`target_arm_only_success`。因此最后 `arm_match=true` 且 `lifted=true` 的回合仍可能因历史错误失败。
该判据应用于共享 `arm_select` 任务，旧几何配置也使用同样的历史检查。

## 验证

`python -m unittest discover -s tests/arm_select -p 'test_*.py' -v` 检查左右臂、先错后对、严格阈值与 reset。
当前成绩见 [result](../result/README.md)。
