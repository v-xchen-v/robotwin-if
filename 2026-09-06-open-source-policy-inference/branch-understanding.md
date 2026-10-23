# open-source-policy-inference：基于 Git 的分支理解与清理

核对日期：2026-09-18。依据为远端分支、Git log/diff、源码引用关系和本轮验证，不使用对话转述推断设计意图。

## 当前理解（基于代码倒推）

远端不存在 `main`；`origin/HEAD` 指向 `origin/master`，提交为
`1685b397a97dc6aee55d60ea4980d9cdacfc0597`，也是当前 feature 分支的 merge base。
本轮清理前 HEAD 为 `833d496`，领先主分支 41 个提交，涉及 294 个文件。
以下描述的是代码实际实现，不代表这些内容最初就计划在同一个 feature 内完成。

| 范围 | Git/源码证据 | 实际行为 |
|---|---|---|
| 六个模型推理接入 | `48a4e68` 至 `d7d06f5`；`policies/{xvla,lingbot_va,lingbot_vla,vlact,dm05,hy_vla}/` | 独立模型环境、checkpoint 下载/校验、服务、客户端、动作解码和回合产物 |
| 公共评测生命周期 | `155857a`、`feaae02`、`8950235`；`policies/evaluation.py`、`scripts/eval.sh` | 固定 seed 的 oracle qualification 与 policy reset；失败保留；便携六任务入口 |
| 正式运行、结果与复核 | `ac932e0`、`c25f5cf`、`0214166`；`tools/run_formal_policy_suite.py`、`summarize_formal_policy_results.py`、`policy-video-review/` | 冻结来源、有限初始化重试、逐文件导入/校验、均衡计分和视频复核 |
| 场景与判据 | `d15573d`、`72d7c36`、`cb4e143`、`cb7a186` | Arm cube-v3；Bottle 完整预算后裁决；Attribute 错物体抬升和 Arm 错臂抬升历史锁定 |
| 任务范围 | `8950235`、`bf25bc3`；inventory/seed contracts | Grasp 下线；Spatial 仅 left/right/on_top，保留原 scene stride |
| 并发运行 | `c72632e`、`50716ec` | 远端模型、多 simulator lane、独立 Hy-VLA 实例和不重叠 seed 分片 |
| 发布入口 | `ce17465`、`2b68b83`、`833d496` | 当前只暴露 Arm-only-v2 manifest/result；历史资格证据按固定 Git commit 临时恢复 |

边界：diff 没有引入模型训练或更新顶层 RoboTwin gitlink。工作区原有的 submodule 修改、
`.claude/settings.json`、`third_party/robotwin-manifest-clean/` 不属于本轮清理。

## 关键改动点与方向调整

提交历史显示调度先后经历 distributed/dual queues → 串行维护入口 → Attribute 双路 → 远端多 lane → 独立模型分片。
`run_parallel_attribute_suite.py` 的 CLI 已无当前文档入口，但远端控制器仍导入它的进程身份和场景检查函数。
因此不能直接删除整个模块；本轮提取这些共用能力后才移除旧调度器。

发布数据曾先移动到根目录 archive 并保留软链接，随后在 `2b68b83` 改为只保留当前发布，
完整审计通过 `tools/release_history.py` 从 `2670a13` 读取原字节。
本轮不再改动这些发布文件，也不改任务源码或 inference/evaluator 行为。

本轮清理范围：

- 移除 39 个旧文件：Arm 长柱、Grasp、Spatial 的历史源码/配置/测试副本；旧 Attribute 双路入口；
  早期 Bottle raw-predicate 诊断脚本；过时试验文档和长柱演示媒体。
- 其中有 10 个归档测试副本。删除的是历史快照；保留当前 policy 客户端、任务判据、入口拒绝退休任务等回归。
- 将仍被远端与分片控制器使用的代码集中到 `tools/remote_eval_support.py`：模型显存预算、PID/start-ticks
  身份检查、已复用 PID 不发送信号、源码冻结、父场景 RGB/state/指令校验。
- 原 `test_parallel_attribute_suite.py` 改为 `test_remote_eval_support.py`；保留进程/场景负例测试，
  删除仅针对废弃本地 admission 分支的 5 个测试。删除与历史源码副本比较 AST 的迁移期断言。
- 保留 `bak/` 中供错误消息使用的下线说明，以及 Spatial 被排除的 240 回合、14 个示例与视频哈希证据。
- 保留当前 Arm oracle 资格探测、Arm/Attribute 真实验证脚本、Bottle 真实轨迹 fixture 和全部最新发布证据。
- 精简 README、policy 总览、Bottle 判据、Cube 场景、正式评测文档；去除旧 smoke 状态和旧 Overall 表，
  保留当前契约、运行参数、来源边界及可执行检查入口。

## 验证与限制

- 114 项相关 CPU 回归通过：远端资源与进程管理、模型分片、当前发布、便携入口、Spatial/退休任务、
  六个 policy seed 入口、正式复用与报表、Bottle 与终态落盘。
- 当前 release 完整溯源通过：全部原资格哈希、父清单、源码审计和 2520 个复用回合的原始产物。
- 48 个现有 result/manifest/evidence 发布文件与清理前 SHA-256 完全一致。
- 远端/分片 CLI `--help`、六任务 `eval.sh --dry-run`、Bash 语法、152 个改动文档/图片链接通过。
- 提取后的进程所有权函数 AST 与原实现相同。父场景检查改为要求显式 task，当前调用方均提供。
- 没有启动模型或 GPU 仿真，没有修改历史成功/失败标签，没有改动 Git 忽略的原始视频与动作文件。
- 这些检查不等于在真实多 GPU 环境重新运行并发调度。当前控制器/helper 的文件名与源码哈希变化后，
  原冻结运行仍须使用原源码快照；新运行应建立新配置和对应哈希，检查本身没有放宽。

## 待确认（代码层面的疑点）

- [ ] `tools/run_formal_policy_suite.py` 的 `DEFAULT_RUN` 仍指向 Attribute-v2，而 `--release` 默认值已是 Arm-only-v2。
  当前文档要求显式传 `--run-dir`，便携 `eval.sh` 要求新的 `--output-dir`。若将内部 runner 作为通用产品入口，
  应单独设计默认目录/必填参数策略，并同步冻结源码审计；本轮没有为了清理而改变发布时运行语义。
- [ ] 正式/远端 runner 仍使用本机 Python、环境目录和部署配置；`scripts/eval.sh` 才是可移植入口。
  若要推广多机调度到任意机器，需要明确配置生成、源码哈希收集及旧运行迁移接口，不能只重命名 Attribute 脚本。
