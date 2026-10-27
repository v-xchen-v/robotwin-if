# 过时 if_benchmark 代码清理

当前模块见 [if_benchmark/README.md](../../if_benchmark/README.md)。原文件保存在已推送的
[清理前提交 `b15374c`](https://github.com/v-xchen-v/robotwin-if/tree/b15374c)。

- 删除 `if_benchmark/legacy_bottle_checker.py`、专用测试 `tests/test_bottle_verb_success.py` 和 `tests/bottle_verb/fixtures/rotation-hold-traces.json`。
- 删除 formal runner 中将 Bottle/Bell 当作当前判据的分支及 Bottle 专用末尾裁决检查；当前判据查询明确拒绝退休任务。
- 移除 3 项 Bottle 版本/末尾裁决测试。通用结果复用、阈值校验、完整 block 和断点续跑测试改用 Stapler，继续保留。
- 保留四个 seed 模块、当前资格证据所需的旧 schema/Spatial 映射，以及供历史结果读取的简短任务元数据。
- 直接调用 seed generation API 也不能为退休任务新建或继续运行；历史 checkpoint 仍可读取和校验。

这次移除旧动作算法，当前六任务场景、指令、manifest、成绩与五任务复用来源均保持原样。
重放旧 Bottle 轨迹判据需使用上述历史版本。

清理后 **217 项 CPU 回归全部通过**，当前 manifest/资格证据校验、seed/mode 核对和 eval dry-run 均通过。
未运行模型或 GPU 仿真；当前任务源码、清单及已发布结果没有改动。
