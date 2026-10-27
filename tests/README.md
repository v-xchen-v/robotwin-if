# 当前测试入口

当前 benchmark 为 Stapler v1 六任务。测试保留当前任务、六模型适配、seed/release、结果复用和调度器的回归覆盖；
早期任务试验、一次性渲染及 sweep 脚本的去向见[历史测试清理说明](../docs/archive/obsolete-test-scripts.md)。

## CPU 回归

在装有项目客户端依赖的 RoboTwin 环境中，从仓库根目录执行：

```bash
conda activate RoboTwin
export PYTHONPATH="$PWD:$PWD/tests${PYTHONPATH:+:$PYTHONPATH}"
python -m unittest discover -s tests -p 'test_*.py' -v
```

这个命令发现根目录的 unittest 模块；子目录中的独立脚本另行执行。
Bridge 集成检查会读取本机 RoboTwin checkout，并在临时目录验证安装/解绑；它仍检查 runtime 的 commit 和本地兼容性文件状态。

| 范围 | 主要入口 |
|---|---|
| Stapler 判据、随机朝向 | [test_press_lift_stapler.py](test_press_lift_stapler.py) |
| 共享接触分类、干扰物采样、指令 reset | [test_press_lift_shared.py](test_press_lift_shared.py) |
| Stapler 初始 RGB / proprio / 位姿配对审计 | [test_press_lift_seed_audit.py](test_press_lift_seed_audit.py) |
| 当前清单与结果发布 | [test_stapler_manifest_release.py](test_stapler_manifest_release.py)、[test_stapler_result_delivery.py](test_stapler_result_delivery.py)、[test_current_release.py](test_current_release.py) |
| 固定 seed、完整 block、无 seed 替换 | `test_if_seed_*.py`、[test_evaluation_setup.py](test_evaluation_setup.py) |
| 当前预算与 bridge inventory | [test_eval_step_limits.py](test_eval_step_limits.py)、[test_task_manifests.py](test_task_manifests.py)、[test_task_bridge.py](test_task_bridge.py) |
| Attribute / Arm 当前历史错误判据 | [test_attribute_select_success.py](test_attribute_select_success.py)、[arm_select/test_policy_success.py](arm_select/test_policy_success.py)、[arm_select/test_scene_variation.py](arm_select/test_scene_variation.py) |
| 结果复用、评分和视频复核 | `test_formal*.py`、[test_spatial3.py](test_spatial3.py)、[test_policy_video_review.py](test_policy_video_review.py) |
| 双路并行与共享远端调度 | [test_parallel_stapler_suite.py](test_parallel_stapler_suite.py)、`test_remote*.py`、[test_sharded_remote_suite.py](test_sharded_remote_suite.py) |

`test_press_lift_shared.py` 仍测试 Stapler 所继承的 `BellMonitor` 基类；基类的兼容撤离条件与 Stapler 的接触即完成条件分别验证。
`test_bottle_verb_success.py`、其轨迹 fixture、历史 schema/判据与退休任务测试仍用于兼容读取、末尾裁决和防止旧结果混入当前评分。
这些测试使用旧任务名，不表示旧任务重新进入默认 suite。`test_remote_attribute_suite.py` 覆盖的 helper 仍被 Stapler 双路调度器使用。

## 子目录测试

当前五个非 Verb 任务的指令、场景和判据脚本位于 `pick_diverse_object/`、`attribute_select/`、`arm_select/`、`stack_sequence/`、`place_relative/`。
各脚本的 docstring 说明环境要求。以下指令路由脚本无需启动仿真：

```bash
python tests/pick_diverse_object/test_instructions.py
python tests/attribute_select/test_instruction_routing.py
python tests/stack_sequence/test_instruction_routing.py
python tests/place_relative/test_instructions.py
python -m unittest discover -s tests/arm_select -p 'test_*.py' -v
```

`test_check_success.py`、Noun 的 `test_wiring.py` / `test_apple_top_grasp.py`，以及 Arm 的
[verify_target_arm_only.py](arm_select/verify_target_arm_only.py)属于真实 SAPIEN 检查，需要先 bridge 并准备资产。
Arm 验证保留“错误臂拿起→放回→指定臂拿起”的物理反例；Noun 的 Apple 检查保留当前 grasp 的固定场景 gate。

六个模型各自的 client/runtime 检查位于对应 policy 子目录。`dm05/test_service.py`、`hy_vla/test_runtime.py` 等官方 runtime 一致性检查使用对应模型的独立环境，详见 [policies](../policies/README.md)。
