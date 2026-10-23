# Press/Lift Bell v1 · 六任务 × 20 blocks

旧版为 `robotwin-if-arm-only-v2-20-per-mode`；本版只把 `bottle_verb` 替换为 `press_lift_bell`。
其余五份 flat manifest 与旧版逐字节相同，沿用原资格证据；旧目录保留。
每个任务 20 个完整 blocks，共 460 回合/model；六个模型合计 2760 回合。

铃铛为 20 个场景，每场景 Press/Lift 各一次：`2k` 是 Press，`2k+1` 是 Lift。
指令为 **Press down on the bell.** / **Pick up the bell.**，均为 250 actions。
`seen`/`unseen` 返回这同一组固定指令，并非两个不同语言池。
使用 `random-back-region-v1` distractors 和 `press-lift-bell-v3-native-contacts-every-step` 判据。
物理步长为 4 ms，每步采样，保留零冲量 contact；完整 Press 仍要求回撤和释放。

从 episode seed 100000 开始顺序筛选，接受 20 blocks，拒绝 0 blocks。
只按 expert 的 setup/plan/success 及配对初始 RGB/proprio 一致性筛选，整组接受或拒绝。
没有启动模型评测，也没有导入旧版模型成绩。

- [suite](suite.yml) · [seed/mode JSON](seed-modes.json) · [CSV](seed-modes.csv)
- [筛选汇总](qualification-summary.json) · [完整筛选记录](press_lift_bell.generation.json)
- `qualification/` 保存旧资格原件、Git 路径和哈希、新源码快照、运行命令及 runtime patch。
- runtime patch 记录本机已有 UTF-8 IO / episode_num 设置；没有修改 RoboTwin gitlink。
- 跨机器复现需匹配源码、配置、资产与模拟器环境；保存的数组哈希来自本次运行主机。

```bash
python seed-manifests/robotwin-if-press-lift-bell-v1-20-per-mode/verify.py
bash scripts/eval.sh --policy lingbot_va --manifest-dir seed-manifests/robotwin-if-press-lift-bell-v1-20-per-mode --blocks 20 --output-dir outputs/policy-eval/bell-v1-lva --dry-run
```

后续评测使用 `scripts/eval.sh --manifest-dir`，继续保留每个固定 seed 的模型失败。
`tools/run_formal_policy_suite.py` 是旧成绩复用工作流，依赖旧模型元数据，不作为本版新任务入口。
