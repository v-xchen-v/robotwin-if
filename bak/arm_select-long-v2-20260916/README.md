# Arm-Select 长柱 v1/v2 备份（2026-09-16）

在探索 cube-v3 前保存。旧物体尺寸 6 × 6 × 20 cm，oracle 使用侧面抓取。

- `source/`：当时的任务、配置、指令、测试、seed manifests、评测入口与 RoboTwin 关键依赖源码快照。
- `result-package/`：当时最新六任务发布包的完整副本；其中 Arm v2 共 240 回合。
- `arm_select-episodes.csv`：提取的 6 个 policy × 40 回合记录。
- `raw-results/<policy>/arm_select/`：240 回合的独立文件副本，包括视频、动作、初始观测、JSON 和日志（约 296 MiB，Git 忽略）。这些不是链接或硬链接。
- `inventory.json`：复制文件的大小和 SHA-256；240 个 episode JSON 另与发布包记录的哈希核对通过。
- `provenance.json`：备份时间、父仓库/RoboTwin commit、原结果位置和备份前 Git 状态。

旧成功数：X-VLA 25/40、LingBot-VA 37/40、LingBot-VLA 15/40、VLAct 0/40、DM05 39/40、Hy-VLA 8/40。
它们属于长柱环境，不能用作 cube-v3 的结果。

需要恢复任务时，从 `source/tasks/envs/arm_select.py` 复制回同名工作区路径；
配置、指令和 evaluator 的旧版本也都在 `source/` 对应路径。恢复前先保留届时的新改动。
原 `result/` 发布包和原运行目录没有移动或改写。
