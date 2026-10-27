# 当前任务实现

`tasks/` 只保留 Stapler v1 六任务的场景、指令和必要共享模块。
当前清单为[六任务 × 20 blocks](../seed-manifests/robotwin-if-press-lift-stapler-v1-20-per-mode/README.md)，模型入口见[运行评测](../README.md#run-evaluation)。

| Task | 场景 | 指令 | task config |
|---|---|---|---|
| Press / Lift Stapler | [press_lift_stapler.py](envs/press_lift_stapler.py) | [JSON](task_instruction/press_lift_stapler.json) | `demo_clean` |
| Noun | [pick_diverse_object.py](envs/pick_diverse_object.py) | [JSON](task_instruction/pick_diverse_object.json) | `demo_clean` |
| Attribute | [attribute_select.py](envs/attribute_select.py) | [JSON](task_instruction/attribute_select.json) | `demo_clean` |
| Arm | [arm_select.py](envs/arm_select.py) | [JSON](task_instruction/arm_select.json) | [demo_clean_arm_select_v3](task_config/demo_clean_arm_select_v3.yml) |
| Sequence | [stack_sequence.py](envs/stack_sequence.py) | [JSON](task_instruction/stack_sequence.json) | `demo_clean` |
| Spatial | [place_relative.py](envs/place_relative.py) | [JSON](task_instruction/place_relative.json) | `demo_clean` |

共享模块包括 grounding/成功判据、空间关系、Noun 物体池和 eval 预算。
`_press_lift_bell.py` 的接触采样、干扰物布局及分类器基类仍被 Stapler 使用；`_press_lift_stapler.py` 定义 Stapler 阈值和朝向采样。
这些源码及当前指令保持发布时的字节，供五任务结果复用审计使用；例如 `_if_eval.py` 中的历史 Bottle 预算条目继续保留，但 Bottle 已不在可运行清单内。

安装并核对 19 个 env/helper/instruction/config 链接：

```bash
bash scripts/bridge_tasks.sh --dry-run
bash scripts/bridge_tasks.sh
bash scripts/bridge_tasks.sh --check
```

Arm v3 配置随 bridge 安装；[`scripts/eval.sh`](../scripts/eval.sh) 启动前校验配置存在且与交付版本一致。首次安装见 [Quickstart](../docs/quickstart.md)。
Bridge 会清理指向本仓库旧任务的链接，包括源文件已删除的旧链接；原生任务与其他来源的链接继续保留。

旧任务、配套 instruction 和 Arm v2 配置的原文件见[清理记录](../docs/archive/obsolete-task-scripts.md)。
历史 Bottle/Bell seed 与结果仍可读取；在当前 checkout 中重新运行这些旧任务会明确报 retired。
