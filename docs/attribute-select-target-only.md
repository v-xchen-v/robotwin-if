# Attribute-Select：禁止先抓错物体再抓目标

成功判据标识为 `target-only-lift-v2`。场景、指令、seed 清单、
相对抬升阈值和 400-action 预算保持原设置。

## 判定规则

目标物体当前相对初始化后的静止高度抬升 **超过 5 cm**，且本回合的干扰物
**从未抬升超过 5 cm**，才满足单回合成功条件。原有的双目标 oracle 可执行性 gate 继续生效。

- 先抓干扰物、放下，再抓目标：失败。
- 同时抬起目标和干扰物：失败。
- 仅抓目标：成功；目标仍须满足当前抬升条件。
- 接触或轻推干扰物，未越过抬升阈值：不记为错误抓取。
- `setup_demo` 为新回合重新记录静止高度，并清空此前的错误记录。

[`AttributePickMonitor`](../tasks/envs/_if_grounding.py) 现在独立检查两个物体，
一旦观测到干扰物越过阈值，就锁定 `distractor_lifted_ever=true`。
[`attribute_select`](../tasks/envs/attribute_select.py) 在场景每次真实 physics step 后更新它，
覆盖 policy 的动作内部子步及 oracle 的移动过程。reset/close 会解除旧场景的观察回调。
`_raw_success`、`check_success` 和 `eval_signals` 使用同一份记录。

诊断字段包括 `checker_version`、`thresholds`、`target_lifted`、`distractor_lifted_ever`、
`first_lifted`、`first_distractor_lift_action`，以及两个物体的当前/最高相对抬升。
`grasped_target` 表示符合新规则的目标抓取；实际目标高度状态另由 `target_lifted` 表示。

## 验证

`python -m unittest discover -s tests -p test_attribute_select_success.py -v` 检查正确抓取、先错后对、阈值与 reset。
完整成绩见 [result](../result/README.md)；6 cm 场景与行为分析见 [尺寸实验](attribute-size-6cm-ablation.md)。
