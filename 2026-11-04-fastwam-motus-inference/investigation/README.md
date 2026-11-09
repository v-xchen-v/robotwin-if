# Fast-WAM / Motus 接入依据与验证状态

记录日期：2026-11-04。初衷见 [intent.md](../intent.md)。基线分支 `release-20261030`，提交 `57cb69c`；开发分支 `feat/fastwam-motus-inference`。

后续增加的 X-WAM 接口、真实 1/2 pilot、动作/视频复核，以及三模型完整 manifest 运行状态见 [X-WAM 与全量评测](xwam.md)。全量于 11 月 4 日 12:44 UTC 启动，动态报告位于 `/Data/robotwin-if/evaluations/wam-full-20261104/progress.html`。11 月 6 日已核对 Fast-WAM / X-WAM 各 460 个完整回合，Overall 为 51.74% / 42.33%；Motus 仍运行中，详见 [完整结果与剩余范围](full-results-20261106.md)。下文保留最初两个模型的来源与 pilot 证据。

2026-11-05 更新：X-WAM 已有四项完整成绩、325 个有效回合；Sequence 的同 seed oracle 失败导致中断，目前已启动恢复。见 [oracle 中断、复现与恢复](oracle-recovery.md)。

## 官方路径与接口

| 项目 | Fast-WAM | Motus |
| --- | --- | --- |
| 源码 revision | `7faa71108368fbb3b6885649f112af607427a2d4` | `88f6fe30c62af033874b0a2e48ad1cbdaf12cfdf` |
| 核心入口 | [`WorldActionRobotWinPolicy`](https://github.com/yuantianyuan01/FastWAM/blob/7faa71108368fbb3b6885649f112af607427a2d4/experiments/robotwin/fastwam_policy/deploy_policy.py) | [`MotusPolicy`](https://github.com/thu-ml/Motus/blob/88f6fe30c62af033874b0a2e48ad1cbdaf12cfdf/inference/robotwin/Motus/deploy_policy.py) |
| 权重 | `yuanty/fastwam@8eaceeb24c3cc92ff2a9c9a9d266a4941b836705` | `motus-robotics/Motus_robotwin2@ab74bc214f7fc5952c85198e062c5f8bf1dc47a7` |
| 图像 | head resize 到 256×320；两 wrist 各 128×160，拼成 384×320 | head 240×320；两 wrist 各 120×160，拼接后 padding/resize 到 384×320 |
| State | 官方统计 z-score 的 14D joint/gripper | 活跃的官方推理代码传入原始 14D joint/gripper state；不能仅凭存在 normalize 函数就再归一化一次 |
| Action | 官方统计反归一化后的 32×14 qpos；执行前 24 步 | 官方 joint inference 返回 16×14 qpos；全部可执行，受环境终止条件约束 |
| 推理设置 | 10 steps、sigma shift 5、text CFG 1、BF16、action-only | 10 Euler steps、BF16、joint video/action |
| 语言 | 官方 `DEFAULT_PROMPT` 嵌入当前回合实际指令 | 官方 scene prefix + 当前回合实际指令，进入 T5 与 Qwen |

Fast-WAM 的发布推理配置跳过初始化用的 video/action DiT 预训练权重，直接由 RoboTwin checkpoint 覆盖；仍需 Wan T5、tokenizer、VAE。适配器使用本地 Wan2.2 中的同源 UMT5 tokenizer，并关闭 DiffSynth 的自动资源重定向/下载。

Motus 官方推理设置 `load_pretrained_backbones=False`，Stage 3 包含 finetuned backbone；另外显式加载 Wan T5、VAE 和 Qwen processor/config。用户列出的 Stage 1 资源已下载保存，不在加载 Stage 3 后覆盖回模型。其 `action_cache` 只追加、不在官方 `eval` 消费，本适配器返回 chunk 后清空该冗余队列；保留模型的 joint inference。

Fast-WAM LeRobot revision 为 `778a36fb9be052c0d6947aaa735d5a05f7e7d815`，目前只核对发布文件清单。没有加载该格式，也没有证明与官方 `.pt` 数值等价。

## 实现位置与证据边界

- 主项目 `policies/fastwam/`、`policies/motus/`：官方模型包装、安装、下载及入口。
- `policies/wam/`：相机/state 传输、episode reset、单客户端服务、joint-action evaluator、资产清单与文件校验。
- `scripts/eval.sh`：新增模型选择，默认端口 8016 / 8017；固定任务、manifest 和判据沿用 release。
- `tools/summarize_formal_policy_results.py` 与 `tools/policy-video-review/server.py`：新增模型名称识别；现有发布结果保持原内容。
- 每个模型参数文件的 revision、大小与 LFS SHA-256 / Git blob SHA-1 保存在 `policies/wam/assets.json`。实际模型启动还核对 checkpoint 的 state-dict 键与参数形状，避免官方 permissive load 掩盖未加载参数。

## 已执行验证

| 检查 | 当前结果 | 能说明什么 |
| --- | --- | --- |
| `python -m unittest discover -s tests/wam -v`（RoboTwin 环境） | 10 项通过 | 相机/state 输入校验、完整动作与执行前缀、reset/错误隔离、真实本地 WebSocket 单客户端限制、预算/终态落盘、资产同长度篡改检测、新模型汇总识别 |
| `test_branch_delivery.py` | 8 项通过 | 九个 policy 的入口/端口、六任务选择、已有输出保护与固定 seed 行为；X-WAM 加入后已复核 |
| `test_formal_result_scope.py` | 4 项通过 | 部分 block 只计进度、错误与缺失不伪造完成结果 |
| `test_policy_video_review.py` | 11 项通过 | 视频复核入口的现有回归 |
| Fast-WAM `check_env` 与 `pip check` | 通过 | 当前独立环境可导入官方推理模块；未分配完整模型 |
| Motus `check_env` 与 `pip check` | 通过 | Torch 2.7.1+cu128、Transformers 4.57.0、FlashAttention 2.7.4.post1 的独立环境可导入官方推理模块 |
| Fast-WAM 官方预处理 | 通过 | 384×320 拼图、1×14 normalized state、1×32×14 denormalized action |
| Fast-WAM checkpoint 对 meta 架构 | 通过 | 1649 MoT tensors + 2 proprio tensors 的键与形状完整匹配；不等于验证所有计算结果 |
| 两模型真实服务启动的参数覆盖检查 | 通过 | 官方 checkpoint 与已加载模型的全部 state-dict 键和形状匹配；Motus 包含共享模块的重复引用，不能简单加总为独立参数量 |

CPU fake backend 不计入 benchmark 成功率。真实模型进展如下；单次观测预测也不等于完整任务结果。

### Fast-WAM 首次真实预测

- 运行位置：`outputs/policy-eval/servers/fastwam-001/`；`server.json` 保存模型、源码及资产身份，`observation-smoke.json` 和 `.npz` 保存真实预测。
- 输入来自已保存的 RoboTwin `press_lift_stapler` seed `110000` 初始观测，指令为 `Press down on the stapler.`。采用 DM05 归档中的原始 `joint_state`，不是该模型处理后的动作。
- 真实模型返回有限值的 `32×14` qpos，客户端取得 `24×14` 前缀；首次预测耗时约 13.23 秒，GPU 1 占用约 24 GiB。尚未据此判断任务成功率。
- 首次加载经过完整参数键/形状检查。磁盘冷启动较慢，不能把首次预测和冷启动耗时当成稳态吞吐。
- 首次预测暴露本适配器的传输问题：msgpack 解码数组引用只读 bytes，官方 `torch.as_tensor` 发出不可写数组警告。服务端现已使用输入校验函数产生的自有可写副本；新增回归断言后 10 项 WAM 检查通过。重新启动 `fastwam-002` 验证该修改，保留首次运行证据。

### 真实 Press/Lift pilot

任务为 `press_lift_stapler`，配置 `demo_clean`，release 首个完整 block；模型 GPU 1、仿真 GPU 0（均为 RTX A6000）。两个 seed 共用 scene seed 55000，指令分别为 `Press down on the stapler.` 与 `Lift the stapler.`。四回合均通过原 seed 的 oracle qualification，无执行错误。

| 模型 | seed / mode | 结果 | 执行动作 | 预测 chunks | 视频帧数 |
| --- | --- | --- | --- | --- | --- |
| Fast-WAM | 110000 / press | success | 58 | 3 | 59 |
| Fast-WAM | 110001 / lift | success | 79 | 4 | 80 |
| Motus | 110000 / press | success | 29 | 2 | 30 |
| Motus | 110001 / lift | success | 26 | 2 | 27 |

- 结果根目录：`/Data/robotwin-if/evaluations/fastwam-motus-pilot-20261104/`，每模型的 `press_lift_stapler/` 包含 `run.json`、`summary.json`、逐回合 result/status、requests、action arrays、initial observation、oracle、视频和日志。
- 服务身份：主项目 `outputs/policy-eval/servers/fastwam-002/server.json` 与 `motus-001/server.json`；Fast-WAM 初次独立预测另外保存在 `fastwam-001/`。
- 完整动作均为有限值；实际执行序列与预测前缀一致，中途成功时正确截断。视频检查通过，帧数等于动作数加初始帧。
- Fast-WAM pilot 首次 chunk 8.10 秒，后续 0.65–0.67 秒；Motus 首次 10.71 秒，后续约 3.20 秒。观察显存占用约 24 / 41 GiB；这是当前机器和小样本的实测，不是完整性能 benchmark。
- 汇总输出 `progress.md`、`.json`、`.csv` 对每模型显示 2/460、1/120 blocks，Overall 为 null，未生成完整六任务分数。结构化证据索引见 [pilot-results.json](pilot-results.json)。
- 两服务在验证结束后停止。本轮未修改官方 checkpoint、官方 tracked source、任务 manifest 或原有发布结果。

## 本机资源与待办

- 模型目录：`/Data/robotwin-if/checkpoints/wam`；两模型共享 Wan；完整用户资源清单约 76.6 GB。
- 环境：`/Data/robotwin-if/envs/robotwin-if-fastwam`、`/Data/robotwin-if/envs/robotwin-if-motus`。
- 全部官方资源已下载并通过固定对象哈希校验：Fast-WAM `.pt` 与统计、Motus Stage 3、Stage 1、完整 Qwen 与 Wan。完成记录：`/Data/robotwin-if/checkpoints/wam/download-verification-20261104.json`。LeRobot 替代格式不属于本次采用的后端，未下载。
- Motus 环境配置与导入检查完成，安装日志：`/Data/robotwin-if/tmp/motus-env-20261104.log`。
- 上游源码已 clone 到主项目忽略的 `third_party/fastwam`、`third_party/motus`，revision 如上。
- 完整 20 blocks/六任务评测现已完成：三模型各 460 回合。11 月 9 日最终核查、逐任务成绩与证据见 [完整结果](full-results-20261106.md)；原六模型发布包保持不变。Fast-WAM LeRobot 格式仍未验证。

## 2026-11-05 全量 oracle 中断与模型独立性

X-WAM 已保留 325 个有效回合；两次批次在 Sequence seed 100065 的模型调用前 oracle 阶段停止。诊断证实跨回合 CuRobo 状态通路，且显式 reset 仍不足以消除不稳定性。03:31 UTC 已启动新的恢复队列，Fast-WAM → Motus → 剩余 X-WAM；实时状态、恢复限制及可复查证据见 [oracle-recovery.md](oracle-recovery.md)。不能把原型接入成功或恢复已启动当作全量成绩完成。

07:47 UTC 用户授权尝试两套并行，新 coordinator 接管并保留 590 个有效结果，开始 Fast-WAM/X-WAM 双 server/sim 验证；Motus 后续单独运行。容量依据、调度交接和真实短跑证据见 [parallel-evaluation.md](parallel-evaluation.md)。

## 2026-11-09 最终核查

本批于 11 月 6 日 20:21 UTC 全部完成。三模型共 1380 条结果通过原 seed manifest、summary、动作预算和哈希一致性审计；Fast-WAM / Motus / X-WAM 的六任务 Overall 分别为 51.7361% / 53.0556% / 42.3264%。22 次 pre-policy oracle 错误均保留完整归档并在原 seed 恢复，正常模型失败保留。报告末次刷新少计一条的问题已依据真实记录修正，详细成绩、运行边界与复核脚本见 [完整结果](full-results-20261106.md)。


2026-11-09 后续按用户授权将代码合并并推送至 `release-20261030`（`777eff4`），当前 result/ 与 Azure 包已扩展为九模型 4140 回合。新包 `robotwin-if-20261109` 的 68605 个文件通过远端校验，旧包与原六模型记录保留；发布边界和证据见 [完整结果](full-results-20261106.md)。
