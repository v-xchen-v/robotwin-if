# Press/Lift Stapler v1 · 六任务 × 20 blocks

当前 Verb 为 `press_lift_stapler`；不包含 Bell 或 Bottle。
其余五个任务的 seeds 与 Arm-only-v2、Bell-v1 完全相同。
共 460 回合/model；六个模型合计 2760 回合。

订书器从 seed 110000 开始顺序筛选，接受 20 组，拒绝 0 组。
每组 Press/Lift 各一次，expert 均成功，初始图像、机器人状态及位姿相同。
订书器 yaw ±15°，鼠标和玩具车各自 yaw ±180°，由 scene seed 固定。
指令：`Press down on the stapler.` / `Lift the stapler.`；各 250 actions。
没有根据模型表现筛 seed；本版尚未进行模型 eval。

- [六任务清单](suite.yml) · [seed/mode JSON](seed-modes.json) · [CSV](seed-modes.csv)
- [资格汇总](qualification-summary.json) · [订书器筛选记录](press_lift_stapler.generation.json)
- 验证：`python seed-manifests/robotwin-if-press-lift-stapler-v1-20-per-mode/verify.py`
- 默认评测入口：`scripts/eval.sh`
