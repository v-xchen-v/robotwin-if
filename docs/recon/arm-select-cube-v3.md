# Arm-Select cube-v3：场景与资格验证

当前正式场景采用 5 cm cube，成功规则为 [target-arm-only-v2](../arm-select-target-arm-only.md)。
六个 policies 的 240 个 Arm 回合已完成重跑，见[当前结果](../../result/robotwin-if-arm-only-v2-20blocks/README.md)。

## 目的与实现

通过独立配置把原 6 × 6 × 20 cm 长柱换成原生 `stack_blocks_three` 使用的
5 × 5 × 5 cm 红色 cube，提供原生上方抓取姿态，降低执行难度，让 arm instruction
成为主要考察点。上方抓取是 oracle 的执行方式，policy 成功判据不额外要求抓取方向。

![旧长柱、cube 初始场景，以及同场景下分别使用左右臂的 oracle 结果](../assets/task-demos/arm_select_cube_v3.png)

位置和旋转由 `scene_seed = seed // 2` 的局部 RNG 采样，指令手臂只由 seed 奇偶决定。
不同 scene seeds 改变初始位置和 yaw；相同 seed 的 reset 可复现，同一 left/right pair
保持相同场景和同一句式，只替换手臂词。cube 平放，roll/pitch 固定为零，避免倾倒引入额外难度。

源码：[`arm_select.py`](../../tasks/envs/arm_select.py) 的 `setup_demo`、`scene_pose`、
`load_actors`、`play_once`；原生 `envs/utils/create_actor.py:create_box` 的
`boxtype="default"` 提供四个上方抓取姿态。

## 输入契约

| 输入 | 来源、默认与约束 | 依据 |
|---|---|---|
| task | `arm_select`；现有六个 policy evaluator 共用任务和 seed 契约 | `if_benchmark/seed_contracts.py` |
| task_config | 新配置 `demo_clean_arm_select_v3`，指定 `arm_select_scene_version: cube-v3` | `tasks/task_config/demo_clean_arm_select_v3.yml` |
| seed | 成对偶/奇数；偶数 left、奇数 right，scene seed 为整除 2 | `setup_demo` / `load_actors` |
| 初始 translation | 世界坐标 x ∈ [−0.04, 0.04] m，分三段循环采样；y ∈ [−0.08, −0.06] m；生成中心 z=0.766 m | `CUBE_X_BINS` / `CUBE_Y_RANGE` / `CUBE_Z` |
| 初始 rotation | yaw ∈ [−15°, 15°]，roll/pitch=0；四元数顺序 wxyz | `CUBE_YAW_LIMIT` / `load_actors` |
| 物理高度 | cube 下表面初始在 0.741 m，随后物理沉降；相对抬升基线在 setup 后记录，支持原生 table bias | `setup_demo` / `create_actor.preprocess` |
| oracle | default cube 的 contact ids 0–3；预抓取 9 cm、上抬 10 cm | `play_once` |
| policy 预算 | 400 actions，相对抬升 >5 cm，距指定 TCP <20 cm 且比另一 TCP 更近；错误臂此前从未抬起 | `_if_eval.py` / `_compute_signals` |
| 语言 | 所有版本沿用 `the block` 及原模板；cube-v3 与 jitter-v2 按 scene seed 选模板 | `policies/xvla/eval.py:instruction_for` |

`fixed-v1` 仍是未传版本时的默认值；旧 `demo_clean_arm_select_v2` 仍生成长柱。
v3 必须显式选择新配置，旧 manifest 与新配置不匹配时 evaluator 会拒绝。
Cube-v3 已纳入[新的六任务 taskset](../../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md)，
六个 policies 的独立重跑与五任务复用见[合并评测说明](../arm-select-target-only-v2-evaluation.md)。

## 资格验证与边界

当前 20 个场景使用固定 seeds `500000–500039`。发布前完成左右臂可执行性、配对
RGB/位姿/指令、复测和错误手臂反例检查；先错后对的当前判据另有[真实仿真验证](../arm-select-target-arm-only.md)。
`env.info['arm_select_scene']` 记录采样元数据；`eval_signals()` 记录当前抬升、手臂归属和整回合错误历史。
这些诊断字段不进入语言指令。

![最终双臂可用范围与探索中的失败角落](../assets/task-demos/arm_select_cube_v3_workspace.png)

资格证据通过[发布溯源](../release-provenance.md)读取固定 Git 提交；
有限样本不保证整个连续空间均可达，正式 evaluator 仍在每个 seed 上执行 oracle qualification。
场景开发过程、旧长柱源码和逐次探测日志仅保留在 Git 历史 `833d496` 中。

## 最小调用

工作目录为仓库根目录，Python 使用已经安装 SAPIEN/CuRobo 的 RoboTwin 环境。
本地已创建下述配置链接；新 checkout 需先安装 task bridge，再链接配置：

```bash
ln -s "$(pwd)/tasks/task_config/demo_clean_arm_select_v3.yml" third_party/robotwin/task_config/demo_clean_arm_select_v3.yml
```

需要为场景修改重新做串行 oracle 预检时，使用保留的工具（输出目录必须不存在）：

```bash
python tools/probe_arm_select_variation.py \
  --scene-version cube-v3 --blocks 12 --seed-start 300000 --check-boundaries \
  --sim-gpu 0 --output outputs/policy-eval/arm-select-cube-v3-probe-new
```

这项开发检查需要 GPU 和 fixed-v1 参考观测；参考目录通过 `--reference PATH` 指定，
默认是 `outputs/policy-eval/if-seven-tasks-2blocks-001`。普通新评测直接使用下面的正式清单，
不需要历史探测产物，也不应重选 seeds。

六个 policy evaluator 均可使用已生成的清单，模型连接参数沿各 policy README：

```text
--task arm_select
--task-config demo_clean_arm_select_v3
--seed-manifest seed-manifests/robotwin-if-arm-only-v2-20-per-mode/arm_select.json
--blocks 20
--output-dir <新的独立结果目录>
```

六任务正式运行已使用 20-block 清单调度六个 policies，状态与结果入口见[合并评测说明](../arm-select-target-only-v2-evaluation.md)。
