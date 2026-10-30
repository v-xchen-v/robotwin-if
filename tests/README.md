# 当前测试入口

测试覆盖当前六任务、六模型适配、固定 seeds、成绩与视频查看入口。

## CPU 回归

在装有项目客户端依赖的 RoboTwin 环境中，从仓库根目录执行：

```bash
conda activate RoboTwin
export PYTHONPATH="$PWD:$PWD/tests${PYTHONPATH:+:$PYTHONPATH}"
python -m unittest discover -s tests -p 'test_*.py' -v
```

这个命令发现根目录的 unittest 模块；子目录中的独立脚本另行执行。
Bridge 集成检查会读取本机 RoboTwin checkout，并在临时目录验证安装/解绑；它仍检查 runtime 的 commit 和本地兼容性文件状态。
同时覆盖旧版 Arm 配置软链的接管、冲突文件保留，以及配置随 bridge 统一校验和解绑。

| 范围 | 主要入口 |
|---|---|
| Runtime 版本一致性、首次源码获取、已有 CuRobo 安全复用 | [test_runtime_setup.py](test_runtime_setup.py) |
| Expert 完整 block 采集、失败跳过、可选 manifest | [test_expert_collection.py](test_expert_collection.py) |
| Stapler 判据、随机朝向 | [test_press_lift_stapler.py](test_press_lift_stapler.py) |
| 共享接触分类、干扰物采样、指令 reset | [test_press_lift_shared.py](test_press_lift_shared.py) |
| Stapler 初始 RGB / proprio / 位姿配对审计 | [test_press_lift_seed_audit.py](test_press_lift_seed_audit.py) |
| 当前清单与结果发布 | [test_current_release.py](test_current_release.py) |
| 固定 seed、完整 block、无 seed 替换 | `test_if_seed_*.py`、[test_evaluation_setup.py](test_evaluation_setup.py) |
| 当前预算与 bridge inventory | [test_eval_step_limits.py](test_eval_step_limits.py)、[test_task_manifests.py](test_task_manifests.py)、[test_task_bridge.py](test_task_bridge.py) |
| Attribute / Arm 当前历史错误判据 | [test_attribute_select_success.py](test_attribute_select_success.py)、[arm_select/test_policy_success.py](arm_select/test_policy_success.py)、[arm_select/test_scene_variation.py](arm_select/test_scene_variation.py) |
| 完整 block 评分和视频复核 | `test_formal*.py`、[test_spatial3.py](test_spatial3.py)、[test_policy_video_review.py](test_policy_video_review.py) |

`test_press_lift_shared.py` 仍测试 Stapler 所继承的 `BellMonitor` 基类；基类的兼容撤离条件与 Stapler 的接触即完成条件分别验证。

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
