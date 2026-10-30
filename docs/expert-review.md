# 采集 expert 场景供人工 review

[`scripts/collect.sh`](../scripts/collect.sh) 用原生 expert 规划和采集数据，方便在跑 policy 前查看各个 mode 的场景、instruction 和成功动作。
默认六任务、每任务 **1 个完整 block**，合计 23 个 episodes；不需要模型服务，也不要求 manifest。
环境和 bridge 先按 [Quickstart](quickstart.md)安装；Arm v3 配置已包含在 bridge 中。

```bash
conda activate RoboTwin

# 默认各采 1 个 block，自动尝试 seeds，失败则跳过整个 block。
bash scripts/collect.sh

# 单任务，各 mode 采 3 条成功演示。
bash scripts/collect.sh --task press_lift_stapler --blocks 3 \
  --output-dir outputs/expert-review/stapler-three

# 可选：直接用当前已筛选的 seeds，减少无效场景尝试。
bash scripts/collect.sh \
  --seed-manifest seed-manifests/20-blocks \
  --output-dir outputs/expert-review/current-suite

# 也可以提供单个 manifest 文件，自动识别任务和配置。
bash scripts/collect.sh \
  --seed-manifest seed-manifests/20-blocks/press_lift_stapler.json
```

`--seed-manifest` 可重复传入多个文件；目录默认读取六任务，也可用 `--task` 选一个。
自动采样从 seed 0 开始，`--start-seed` 可调整起点。`--dry-run` 只展示任务、配置与首个候选 block。
默认使用物理 GPU 0，可用 `--sim-gpu` 指定；解释器可通过 `SIM_PYTHON` 指定。
外部 runtime 使用 `--robotwin-dir`，兼容性检查沿用[bridge 规则](task-bridge.md)。
若安装 bridge 时使用了 `--allow-compatible-commit`，采集时也传入该参数；本机已核验的 RoboTwin UTF-8 修改属于这种情况。

一个 block 覆盖该任务的所有 mode：Stapler 2、Noun 2、Attribute 8、Arm 2、Sequence 6、Spatial 3。
先检查整个 block 的 expert，再重置相同 seeds、重放原生规划轨迹并保存数据；**规划或采集阶段任一 mode 失败，都丢弃整个 block**。
因此 `--blocks 3` 意味着每个 mode 都有 3 条成功演示，同场景对照不会由不同候选 block 拼接。

自动采样持续到采够；可用 `--max-candidate-blocks N` 限制尝试次数。Manifest 模式只按文件中的完整 blocks 顺序尝试，不会追加文件外的 seeds。
候选用尽而数量不足会返回非零，保留已有完整 blocks 并标记 incomplete。文件、配置或数据导出错误会终止；失败场景简记在 `rejected.jsonl`。

每次使用新输出目录，默认是 `outputs/expert-review/<timestamp>/`。打开其中的 **`index.html`** 即可浏览，采集期间每完成一个 block 就更新。
目录可以整体复制备份，页面使用相对路径。每个 mode 包含：

- 原生 head-camera MP4、初始三路相机拼图；HDF5 保留三路 RGB、关节和末端状态。
- `instruction.txt` 和 `episode.json`：与 policy 共用的指令生成逻辑（默认 unseen）、seed、mode、场景信息及 expert 成功状态。
- 原生 `_traj_data/` 规划轨迹；plan/collect 日志。中间图像缓存在导出后删除。

自动采样展示当前任务的场景样例；使用正式 manifest 才对应其指定的评测 seeds。采集仍会检查当前代码下的 expert 成功，不把 manifest 当作无条件成功保证。
这些是 expert 演示，不是 policy 成绩，也不会改动正式 manifest 或已发布结果。

实现验证：当前 manifest 六任务各 1 block（23 条）及自动采样 Stapler 1 block（2 条）均完成真实采集。
视频/HDF5 帧数、policy instruction 一致；六任务样例中非 Noun 的 8 组初始 RGB 和机器人状态对照完全一致。相关 CPU 测试 25 项通过。
