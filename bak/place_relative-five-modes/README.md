# Place-Relative 五模式归档

2026-09-15 暂时下线 front/back，当前任务仅保留 left/right/on_top。
[决策、证据边界与新旧统计](../../docs/place-relative-spatial3.md)。

- `envs/`：改动前的五模式任务及几何判定 helper。
- `place_relative.json`：原 instruction 模板。
- `test_check_success.py`：原五模式模拟器正反例测试，仅供历史实现复现。
- `excluded-episodes.csv`：全部 240 个排除回合，含 2 个自动成功。
- `evidence.json`：视频路径及哈希、指令、原判定、复核入口参数。
- `records/`：同一场景的 12 个 front/back 失败与 2 个自动成功例外的原始 JSON。

原始视频保存在 evidence 中所列运行目录，原六任务结果包和 manifest 未改写。
这些是自动结果及用户观察的证据，不是已完成的逐回合人工重标注。
