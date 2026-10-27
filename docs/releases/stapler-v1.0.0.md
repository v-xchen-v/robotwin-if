# Stapler v1.0.0

日期：2026-10-27 · Git tag：`stapler-v1.0.0`

本版冻结 robotwin-if 的六任务 instruction-following benchmark：从 RoboTwin 原生任务的原子技能出发，
在共享场景中改变指令，检验模型能否切换动作或目标。除 Noun 的独立 Seen/Unseen 场景外，五项任务的组内初始观测已验证 pixel-equal。

## 任务与评测范围

任务为 `press_lift_stapler`、`pick_diverse_object`、`attribute_select`、`arm_select`、`stack_sequence`、`place_relative`。
每任务固定 **20 blocks**，每模型 **460 回合 / 120 blocks**；六个开源 checkpoint 共 **2760 回合 / 720 blocks**。
Stapler 新跑 240 回合，其余五任务原样复用 2520 回合，包含成功和已完成的 policy failure。
Seeds 按 expert 与场景资格筛选完整 blocks，冻结后不按模型表现替换。

Stapler 使用随机位置和朝向的订书器、鼠标与玩具车背景，同场景对照指令为
`Press down on the stapler.` / `Lift the stapler.`；成功判据锁定第一个完成的动作。

## 六模型成绩

| Checkpoint | Overall (%) | Press | Lift | 同场景双成功 |
|---|---:|---:|---:|---:|
| X-VLA | 27.6 | 9/20 | 15/20 | 7/20 |
| LingBot-VA | 56.2 | 18/20 | 0/20 | 0/20 |
| LingBot-VLA | 31.6 | 18/20 | 1/20 | 1/20 |
| VLAct All 100K | 57.4 | 20/20 | 16/20 | 16/20 |
| DM05 | 50.1 | 20/20 | 12/20 | 12/20 |
| Hy-VLA | 38.9 | 17/20 | 18/20 | 17/20 |

Overall 对六任务成功率等权平均，每任务内部各 mode 等权。X-VLA 使用 clean checkpoint，其余五个使用 clean + randomized checkpoints。
完整分任务成绩、checkpoint revisions 与逐回合证据见[冻结结果包](../../result/robotwin-if-press-lift-stapler-v1-20blocks/README.md)。
Verb 任务已替换，Overall 与旧版的变化不能视为同一任务上的能力提升。
Hy-VLA 的 Noun seed `100052` 保留原自动标签及[人工复核分歧记录](../assets/task-demos/README.md)。

## 安装与固定版本

| 组件 | 固定 commit |
|---|---|
| RoboTwin | `0aeea2d669c0f8516f4d5785f0aa33ba812c14b4` |
| CuRobo | `d64c4b005459db10c5dd867d8b30a87d5bda9bdb` |

版本由 [`runtime_pins.json`](../../scripts/runtime_pins.json) 统一定义。安装器使用官方可获取的 RoboTwin 基线并安全复用已有 CuRobo 源码。
Bridge 统一管理六任务、helper、instruction 与 Arm cube-v3 配置，共 19 个软链。
Expert review 默认采集每任务 1 个完整 block，支持自动跳过失败场景，也可使用正式 manifest。

```bash
git clone --branch stapler-v1.0.0 --recurse-submodules https://github.com/v-xchen-v/robotwin-if.git
cd robotwin-if
```

后续安装与运行见 [Quickstart](../quickstart.md)；固定 seeds 见[当前 manifest](../../seed-manifests/robotwin-if-press-lift-stapler-v1-20-per-mode/README.md)。

## 验证与下载

- 53 项安装/bridge/采集/评测入口 CPU 回归、54 项任务清单检查，以及六模型的六任务 eval dry-run 通过。
- 干净 checkout 下复用已有依赖和资产，六任务 expert 采集 **23/23** 成功；8 组非 Noun 初始画面及机器人状态完全一致，视频与 HDF5 帧数、instruction 对齐。
- 复用已有模型环境和权重，VLAct 的一个 Stapler block **Press 1/1、Lift 1/1** 成功。这是安装验收，正式成绩使用上方冻结结果。
- Azure 备份的 **52,821 个文件**已核对大小与 Content-MD5；49 个抽样下载文件通过 SHA-256 校验，覆盖六模型。下载的查看器可索引完整备份的 2760 回合。

完整备份约 **8.19 GiB**，包括视频、动作、观测和结果证据，访问需要 Azure 容器读取权限。
下载、SHA-256 校验和本地视频浏览见[授权下载说明](../download-results.md)；模型权重与环境按 [policies](../../policies/README.md) 单独准备。

代码采用 [MIT License](../../LICENSE)；[CITATION.cff](../../CITATION.cff) 提供待填写的引用模板。
