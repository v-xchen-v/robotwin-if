# RoboTwin-IF cube-v3 taskset：六任务 × 20 blocks

每个 policy 460 回合；六个 policies 合计 2760 回合、720 blocks。
Arm-Select 使用 5 cm cube 与 `demo_clean_arm_select_v3`，seeds 500000–500039，左右臂各 20 回合。
其余五任务与上一版清单逐字节一致；Bottle-Verb 保留 v6 回合末判定，Spatial 保留 left/right/on_top。

本轮复用最新 Bottle v6 结果包中的五任务共 2520 回合，只重跑 Arm-Select 的 240 回合。
复用包含所有成功和 policy failure，逐回合来源及所有 artifact SHA-256 见 `reusable-results.yml`。
Cube 的 20 个场景已通过 54/54 oracle/对照回合检查；配对图像、位姿与句式一致。

- [套件与任务配置](suite.yml) · [seed/mode JSON](seed-modes.json) · [CSV](seed-modes.csv)
- [复用审计](reuse-audit.json) · [绑定的资格证据](qualification-files.json)
- [Cube 环境与验证](../../docs/recon/arm-select-cube-v3.md)

校验：`python seed-manifests/robotwin-if-cube-v3-20-per-mode/verify.py`。
运行：`bash scripts/eval.sh --policy <policy> --manifest-dir seed-manifests/robotwin-if-cube-v3-20-per-mode --output-dir <new-output>`。
复用并重跑的正式入口见 `tools/run_formal_policy_suite.py prepare/run`，须指定本目录与最新 Bottle v6 的 `--old-run`。
