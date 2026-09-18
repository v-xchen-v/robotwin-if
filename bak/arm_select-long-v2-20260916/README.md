# Arm-Select 长柱 v1/v2 源码备份（2026-09-16）

这里保留 cube-v3 之前的任务实现、配置、指令、测试、评测入口与 RoboTwin 关键依赖源码。
旧物体尺寸为 6 × 6 × 20 cm，oracle 使用侧面抓取；这些文件不作为当前评测入口。

旧发布包、seed manifests、逐回合表和带旧成绩的 README 副本已从当前分支移除，
可通过 Git commit `2670a13f53f6e3f1cc2e6f0fdae558782cb88d7d` 追溯。
`inventory.json` 和 `provenance.json` 保留备份时的文件哈希、原位置与版本身份。
其中记录的旧发布文件路径属于历史清单，不表示该文件仍在当前 checkout 中。

本机 `raw-results/<policy>/arm_select/` 保留视频、动作、初始观测和日志的独立副本，
约 296 MiB，Git 忽略；本次整理没有移动或删除这些原始仿真文件。

当前清单、结果与溯源要求见[发布说明](../../docs/release-provenance.md)。
