# 过时任务脚本清理

当前入口见 [tasks/README.md](../../tasks/README.md)。以下原文件均保存在已推送的
[清理前提交 `ff5dd2f`](https://github.com/v-xchen-v/robotwin-if/tree/ff5dd2f/tasks)。

| 范围 | 处理 |
|---|---|
| `bottle_verb`、`press_lift_bell` | 已被 Stapler 替代；移除两个 env 与对应 instruction JSON。 |
| `laptop_verb`、`operate_stapler`、`operate_tabletop`、`operate_mic_drawer`、`smoke_click_bell` | 移除五个停用实验 env 与对应 instruction JSON。 |
| `demo_clean_arm_select_v2.yml` | 旧长柱配置退休；当前 Arm 使用 cube-v3 配置。 |
| `_if_bottle_verb.py` | 当时迁移为[历史 legacy_bottle_checker.py](https://github.com/v-xchen-v/robotwin-if/blob/b15374c/if_benchmark/legacy_bottle_checker.py)，后续在 [if_benchmark 清理](obsolete-benchmark-scripts.md)中退休。 |

共移除 **7 个旧任务实现、7 份 instruction 和 1 份旧配置**，另迁移 1 个历史判据模块。
Bottle 的 9 项 env 接线测试与 2 项旧任务预算测试一并退休；纯 CPU 轨迹与历史结果兼容检查保留。

Bridge 收敛为当前六任务、六个共享模块和六份指令，共 18 个链接。
Bottle/Bell 的 seed 契约转为只读历史元数据；六个 policy 入口在创建产物或加载仿真前拒绝所有已退休任务。
当前六任务场景、指令、共享判据、seed manifest 和已发布成绩保持原字节。

更早退休的 `grasp_cube_approach` 见[原下线说明](../../bak/grasp_cube_approach/README.md)。
重放旧任务需使用对应历史 checkout、配置及运行环境。

清理后根目录 **242 项 CPU 回归全部通过**，任务 inventory、manifest 校验和 eval dry-run 通过。
18 份当前任务/共享模块/指令与清理前逐字节一致；五任务复用所需的 14 个源码哈希均匹配旧运行。
本机 bridge 已移除 5 个旧 env/helper/instruction 软链及单独安装的 Arm v2 配置软链，18 个当前链接检查通过。
本机沿用已核对的 UTF-8 兼容设置；RoboTwin 原有 tracked 改动保持原样。本次未运行模型或 GPU 仿真。
