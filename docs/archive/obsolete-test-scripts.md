# 过时测试与实验脚本清理

当前测试入口见 [tests/README.md](../../tests/README.md)。本次从 `tests/` 移除 19 个过时脚本，
全部原文件仍保存在[备份提交](https://github.com/v-xchen-v/robotwin-if/tree/ac582a75267126c7a8fe17c220475d517b73882b/tests)（分支 `master-261027-staper-v1`）。未恢复旧测试目录到 master。

| 移除范围 | 数量 | 原因与原文件 |
|---|---:|---|
| Laptop / Operate-Mic-Drawer / Operate-Stapler / Operate-Tabletop | 7 | 停用实验任务的测试与 oracle probe，见[旧 tests 树](https://github.com/v-xchen-v/robotwin-if/tree/ac582a75267126c7a8fe17c220475d517b73882b/tests)。 |
| Attribute `render_*`、`spike_*` | 6 | 早期贴图、渲染和接线探索；当前属性判据与指令回归独立保留，见[原目录](https://github.com/v-xchen-v/robotwin-if/tree/ac582a75267126c7a8fe17c220475d517b73882b/tests/attribute_select)。 |
| Attribute `replay_target_only.py` | 1 | 针对旧归档动作和旧停止条件的诊断回放，原[脚本](https://github.com/v-xchen-v/robotwin-if/blob/ac582a75267126c7a8fe17c220475d517b73882b/tests/attribute_select/replay_target_only.py)仅作为历史验证方法。 |
| Arm `check_if_wiring.py`、`spike_success_rate.py` | 2 | 针对早期固定方块和旧配置；当前 cube-v3、左右臂和错误臂历史测试保留，见[原目录](https://github.com/v-xchen-v/robotwin-if/tree/ac582a75267126c7a8fe17c220475d517b73882b/tests/arm_select)。 |
| Bottle `sweep_per_variant.py` | 1 | 旧 Bottle 变体筛选，见[原脚本](https://github.com/v-xchen-v/robotwin-if/blob/ac582a75267126c7a8fe17c220475d517b73882b/tests/bottle_verb/sweep_per_variant.py)。 |
| Bottle `test_check_success.py` | 1 | 仅转调根目录 CPU 测试的重复入口；`test_bottle_verb_success.py` 与真实轨迹 fixture 保留。 |
| Sequence `sweep_per_perm.py` | 1 | 早期 90% oracle gate / 动态换 seed sweep；当前顺序反例和固定 manifest 资格校验保留，见[原脚本](https://github.com/v-xchen-v/robotwin-if/blob/ac582a75267126c7a8fe17c220475d517b73882b/tests/stack_sequence/sweep_per_perm.py)。 |

Bell 命名下仍被 Stapler 使用的覆盖已整理为 `test_press_lift_shared.py`、`test_press_lift_seed_audit.py`；
正式发布检查改为 `test_stapler_result_delivery.py`，使用当前 Stapler 指令与 seeds。
这些模块的共享接触、配对观测、动作分类和拒绝不完整结果等断言继续保留。

历史设计文档中的原脚本路径和过往验证次数描述当时的实现。重放这些实验应使用备份版本；当前固定 seed 的模型评测入口保持不变。

清理后根目录 CPU 回归 **260 项全部通过**；本次没有运行 GPU 仿真或模型评测。当前任务、seed 清单及结果包保持原样。
