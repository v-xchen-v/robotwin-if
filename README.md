# robotwin-if

复刻 [Qwen-RobotManip Technical Report](https://arxiv.org/abs/2606.17846) 中提出的 **RoboTwin-IF** (Instruction Following) 基准。

在 [RoboTwin 2.0](https://github.com/RoboTwin-Platform/RoboTwin)（作为 git submodule 引入，**不 fork、零改上游源码**）之上实现 5 个指令跟随任务集：

| 任务集 | 测试维度 | 状态 |
|---|---|---|
| Operate-Stapler | 共享场景下的动词判别 | ✅ |
| Operate-Tabletop | 三选一动词 + 目标判别 | ✅ |
| Pick-Diverse-Object | 目标物体 grounding（颜色+名词） | ✅ |
| Place-Relative | 空间关系（beside / on-top） | ✅ |
| Operate-Mic-Drawer | 多步双臂协调 | ⏸ 搁置（资产几何不兼容，见 feature-06） |

范围仅限复刻基准本身（场景 / 干扰物 / 指令模板 / 成功判定），**不训练模型**。真实 VLA 评测（Layer C/D）另在 CogACT 侧进行（把本仓库作为 submodule 挂入）。

## 设计原则：零改上游

我们的任务文件维护在 `tasks/` 下，靠 `scripts/bridge_tasks.sh` 用软链注入 submodule 的 3 个「按 `task_name` 发现」的桥接点（`envs/` / `description/task_instruction/` / `description/objects_description/`）。submodule 一字不改，升级/解绑都干净。

## 用法

### 1. 环境搭建
```bash
bash setup_robotwin.sh [--assets_cache <本地资产缓存目录>]
```
装 RoboTwin 2.0 仿真环境（SAPIEN/CUDA/curobo 等）。详见 [docs/features/01-环境搭建.md](docs/features/01-环境搭建.md)。

### 2. 桥接任务进 submodule
```bash
bash scripts/bridge_tasks.sh      # 注入我们的任务（幂等）
bash scripts/unbridge_tasks.sh    # 逆操作：只移除我们的软链，不碰原生文件
```

### 3. 采数据（oracle 专家演示）
RoboTwin 的 collect 是**单任务**的，多任务用循环遍历 `eval_cfg/` 里的任务清单：
```bash
bash scripts/bridge_tasks.sh
cd third_party/robotwin
for t in $(python3 -c "import yaml;print(' '.join(yaml.safe_load(open('../../eval_cfg/if_tasks.yml'))['tasks']))"); do
  bash collect_data.sh "$t" demo_clean 0   # <task> <config> <gpu_id>
done
```
- 任务清单二选一：`eval_cfg/if_tasks.yml`（仅 4 个 active IF 任务）/ `eval_cfg/all_tasks_plus_if.yml`（原生 50 + IF）。
- 每任务收尾会自动生成指令（`gen_episode_instructions.sh`），无需手动跑。

### 4. 评测
RoboTwin 无顶层 eval 入口，评测**每个 policy 走自己的** `eval.sh`，且**必须挂一个 policy 模块**（无 oracle-only 模式）：
```bash
cd third_party/robotwin/policy/<PolicyName>
bash eval.sh <task_name> demo_randomized <ckpt_setting> <expert_data_num> <seed> <gpu_id>
```
- task 名替成任意 IF 任务即可（harness 靠 bridge 认任务，与原生等价）——但需要一个覆盖该任务的 checkpoint 才有意义。
- `instruction_type` 在各 policy 的 `deploy_policy.yml` 里默认 `unseen`（IF 正解；要 seen sanity 可 override）。
- 真实 VLA 评测计划在 CogACT 侧做（本仓库作 submodule）。

### 5. 测试（Layer A/B，无需仿真或极轻量）
```bash
python tests/<task>/test_instructions.py     # Layer A：指令池不变量（seen/unseen 无重叠、路由）
python tests/<task>/test_check_success.py    # Layer B：成功判定正反例
```

## 仓库结构

```
tasks/            我们的任务（envs/ + task_instruction/），bridge 注入 submodule
eval_cfg/         任务清单 yml（if_tasks / all_tasks_plus_if），供 collect/eval 循环
scripts/          bridge_tasks.sh / unbridge_tasks.sh
tests/            Layer A/B 验证
tools/            可视化（object-gallery / dataset-viewer，`just gallery` / `just dataset-viewer`）
docs/             design.md + features/（逐任务实现记录）
third_party/robotwin   RoboTwin 2.0 submodule（锁定 commit，零改）
```

设计文档：[docs/design.md](docs/design.md)。逐任务实现记录见 [docs/features/](docs/features/)。

## Status

4/5 任务集完成（Layer A 结构 + Layer B 判定正反例 + oracle 冒烟成熟度），Operate-Mic-Drawer 搁置。合并评测任务清单（`eval_cfg/`）已就位；真实 VLA 评测（Layer C/D）待在 CogACT 侧进行。
