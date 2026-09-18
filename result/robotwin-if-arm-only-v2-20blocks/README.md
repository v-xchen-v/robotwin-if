# RoboTwin-IF Arm-only-v2：六任务、六 policies、20 blocks

已完成并校验 **2760/2760 回合、720/720 blocks**。共 1097 次成功、1663 次 policy failure。
Arm-Select 使用 `target-arm-only-lift-v2` 全新运行 240 回合；其他五任务逐字节复用上一版 Attribute-v2 的 2520 回合。
各 policy 的 checkpoint、推理参数和所有 seeds 保持原版。Arm 使用 5 cm cube-v3，Attribute 保留 target-only-lift-v2，Bottle 保留 v6 terminal 判据。
共有 4 次推理前 oracle 初始化失败，均在新 simulator 中用原 seed 恢复；
已完成的 policy 成功/失败回合没有重跑，详见[初始化重试记录](oracle-setup-retries.json)。

- [HTML 结果表](results.html) · [Markdown](results.md) · [分模式 CSV](results.csv) · [逐回合 CSV](episodes.csv)
- [来源](provenance.json) · [正式校验](validation.json) · [Checkpoint](checkpoints.json) · [运行计划](plan.json)
- [新 taskset](../../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md) · [新判据与回放](../../docs/arm-select-target-arm-only.md)
- [Arm 新旧逐回合结果与错误手臂记录](arm-comparison.csv)

新 Arm 判据要求指定臂当前抬升严格超过 5 cm，且非指定臂本回合从未完成该抬升，先错后对仍失败。
全部 240 个新回合的初始观测与上一版逐数组核对。动作预算仍为 400。
Overall 对六个 Task Avg. 等权平均；每项 Task Avg. 对 modes 等权。Spatial 仅含 left/right/on_top。
Arm/Overall 的变化包含成功判据变化及重新推理的影响，不能视为模型能力变化。

原始视频与动作：`/Data/robotwin-if/evaluations/robotwin-if-arm-only-v2-20blocks-001/<policy>/<task>/`。
视频复核：`python tools/policy-video-review/server.py --run-dir /Data/robotwin-if/evaluations/robotwin-if-arm-only-v2-20blocks-001`。
在本目录执行 `sha256sum -c SHA256SUMS` 可核对发布文件。
