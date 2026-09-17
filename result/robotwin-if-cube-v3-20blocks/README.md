# RoboTwin-IF cube-v3：六任务、六 policies、20 blocks

已完成并校验 **2760/2760 回合、720/720 blocks**。共 1292 次成功、1468 次 policy failure。
Arm-Select 的 240 回合使用 5 cm cube 重新评测；其他五任务的 2520 回合逐字节复用最新 Bottle v6 结果。
各 policy 的 checkpoint 与推理参数沿用上一轮。
共有 4 次推理前 oracle 初始化失败，均在新 simulator 中用原 seed 恢复；
已完成的 policy 成功/失败回合没有重跑，详见[初始化重试记录](oracle-setup-retries.json)。

- [HTML 结果表](results.html) · [Markdown](results.md) · [分模式 CSV](results.csv) · [逐回合 CSV](episodes.csv)
- [来源](provenance.json) · [正式校验](validation.json) · [Checkpoint](checkpoints.json) · [运行计划](plan.json)
- [新 taskset](../../seed-manifests/robotwin-if-cube-v3-20-per-mode/README.md) · [Cube 环境](../../docs/recon/arm-select-cube-v3.md)

Arm-Select 使用 `demo_clean_arm_select_v3`，20 个配对场景、左右臂各 20 回合/policy，动作预算 400。
Bottle-Verb 保留 v6 回合末判定；Spatial 仅含 left/right/on_top。
Overall 对六个 Task Avg. 等权平均；每项 Task Avg. 对 modes 等权。
此轮改变了 Arm-Select 任务环境，新旧 Arm/Overall 差异包含环境变化的影响。

原始视频与动作：`/Data/robotwin-if/evaluations/robotwin-if-cube-v3-20blocks-001/<policy>/<task>/`。
视频复核：`python tools/policy-video-review/server.py --run-dir /Data/robotwin-if/evaluations/robotwin-if-cube-v3-20blocks-001`。
在本目录执行 `sha256sum -c SHA256SUMS` 可核对发布文件。
