# Attribute-Select：禁止先抓错物体再抓目标

2026-09-17 修正成功判据，版本为 `target-only-lift-v2`。场景、指令、seed 清单、
相对抬升阈值和 400-action 预算保持原设置。

## 判定规则

目标物体当前相对初始化后的静止高度抬升 **超过 5 cm**，且本回合的干扰物
**从未抬升超过 5 cm**，才满足单回合成功条件。原有的双目标 oracle 可执行性 gate 继续生效。

- 先抓干扰物、放下，再抓目标：失败。
- 同时抬起目标和干扰物：失败。
- 仅抓目标：成功；目标仍须满足当前抬升条件。
- 接触或轻推干扰物，未越过抬升阈值：不记为错误抓取。
- `setup_demo` 为新回合重新记录静止高度，并清空此前的错误记录。

旧 `_lifted()` 只检查查询时的高度，而且先检查 target。干扰物曾经被抓起后放回时，
其历史会丢失；两个物体同时在空中时，也会因为 target 优先而误判成功。

[`AttributePickMonitor`](../tasks/envs/_if_grounding.py) 现在独立检查两个物体，
一旦观测到干扰物越过阈值，就锁定 `distractor_lifted_ever=true`。
[`attribute_select`](../tasks/envs/attribute_select.py) 在场景每次真实 physics step 后更新它，
覆盖 policy 的动作内部子步及 oracle 的移动过程。reset/close 会解除旧场景的观察回调。
`_raw_success`、`check_success` 和 `eval_signals` 使用同一份记录。

诊断字段包括 `checker_version`、`thresholds`、`target_lifted`、`distractor_lifted_ever`、
`first_lifted`、`first_distractor_lift_action`，以及两个物体的当前/最高相对抬升。
`grasped_target` 表示符合新规则的目标抓取；实际目标高度状态另由 `target_lifted` 表示。

## 历史结果与后续评测

现有 [cube-v3 六任务结果包](../result-archive/robotwin-if-cube-v3-20blocks/README.md)中的
Attribute-Select 使用旧判据。原始视频、动作和计数保留，不能把它们标成新判据的结果。
修正后的[完整成绩](../result-archive/robotwin-if-attribute-v2-20blocks/README.md)已完成：六个 policies 重跑 Attribute 的 960 回合，其他五任务复用 cube-v3 的 1800 回合，共 2760 回合、720 blocks。历史汇总分数不改写。

[`run_formal_policy_suite.py`](../tools/run_formal_policy_suite.py) 为新计划固定
`target-only-lift-v2` 和 `lift_m=0.05`。旧版本或缺少版本标记的 Attribute-Select 成功/失败记录，
均不允许复用到新计划中；显式读取历史计划仍按其原记录的判据处理。

## 验证入口

两个用户指出的案例和一个正确抓取对照均完成原始动作回放，轻量证据保存在
[`result-archive/attribute-select-target-only-v2-review/`](../result-archive/attribute-select-target-only-v2-review/README.md)。

| Policy / seed | 错误物体首次越过 5 cm 的 action | 干扰物最高抬升 | 原始动作数 | 新判据 |
|---|---:|---:|---:|---|
| LingBot-VA / 100003 | 79 | 9.10 cm | 256 | failure |
| X-VLA / 100001 | 74 | 8.69 cm | 232 | failure |
| LingBot-VA / 100002（正确抓取对照） | — | 0.00 cm | 84 | success |

三次回放均匹配全部原始动作数、旧判据的成功停止点、三路初始 RGB 和初始机器人状态。
前两个案例的目标最终仍在空中，但历史错误被保留，正好覆盖此次误判。

CPU 回归覆盖八种 axis/value 下的正确抓取与先错后对、同时抓取、轻推、阈值、
reset/close、物理子步观察及双目标 gate：

```bash
python -m unittest discover -s tests -p test_attribute_select_success.py -v
python -m unittest discover -s tests -p 'test_formal*.py' -v
```

保存动作的回放工具为 [`replay_target_only.py`](../tests/attribute_select/replay_target_only.py)。
它先核对三路初始 RGB 和机器人状态，再执行原始 EE actions；沿用旧判据的停止时刻，
包括最后一个动作的部分子步，同时观察新判据。它不调用模型，也不补全原轨迹之后的动作，
输出明确标记 `diagnostic_only=true`，不作为重新完成的正式 policy 回合。

```bash
CUDA_VISIBLE_DEVICES=0 python tests/attribute_select/replay_target_only.py \
  --episode-prefix outputs/policy-eval/robotwin-if-cube-v3-20blocks-001/lingbot_va/attribute_select/attribute_select_ep100003 \
  --output outputs/policy-eval/attribute-target-only-v2-review-new/lingbot_va-100003
```

输出目录必须不存在。运行需要 RoboTwin 环境，完整回放证据保存在
`outputs/policy-eval/attribute-target-only-v2-review-001/`。

此次 CPU 检查中，9 项专用回归、24 项 formal 测试、9 项 setup/finalization 测试、
16 项预算测试、1 项现有 Attribute policy reset 测试均通过；另有 8/8 指令路由检查通过。
真实 SAPIEN 环境中的 `tests/attribute_select/test_check_success.py` 也通过 9/9 检查，
覆盖同场景换目标、正确/错误抓取、先错后对及原有 pair gate。
额外 bridge 测试为 23/24：唯一失败是当前已有 RoboTwin checkout 为 `b82ffb8`，
与 bridge 锁定的 `0aeea2d` 不同，且兼容性文件有本地修改。本次没有变更这些本地 runtime 配置或绕过该 gate。
