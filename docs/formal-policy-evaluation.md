# 七任务 v2 正式评测：12 blocks

## 宽范围 grasp 修订

2026-09-10 宽范围修订使用 `seed-manifests/if-ext-v2-wide-12-per-mode/`，
结果目录为 `/Data/robotwin-if/evaluations/if-seven-tasks-v2-wide-12blocks-001`。
新版 grasp 配对范围 x=[0,8] cm、y=[-8.5,-3.5] cm；30 个独立候选 blocks 中 27 个合格，
按三个 x 分层各选最先通过的 4 个完整 blocks。

新运行已复用上轮通过完整性校验的 498 条完成结果（193 成功、305 失败），
初始剩余 1446 条待运行，其中新版 grasp 为 144 条。复用详情见新运行 `support/migration.json`。
源码、配置、manifest 和结果按运行归档；当前同名 v2 配置是宽范围版本，
旧窄范围运行需使用其原始 source/config 快照。

新建宽范围评测时显式指定 release 和尚不存在的结果目录：

```bash
python tools/run_formal_policy_suite.py prepare \
  --release seed-manifests/if-ext-v2-wide-12-per-mode \
  --run-dir outputs/policy-eval/if-wide-example
```

## 初始单机流程（窄范围版本）

以下表格和默认命令描述最初的 276 条复用基线。重放这一版时使用对应的旧源码与配置快照。

正式 seed 固定在 `seed-manifests/if-ext-v2-12-per-mode/`。六个 policies 为
`xvla`、`lingbot_va`、`lingbot_vla`、`vlact`、`dm05`、`hy_vla`。

| 任务 | config | 每个 policy 总 episodes | 复用 | 补跑 |
|---|---|---:|---:|---:|
| bottle_verb | demo_clean | 24 | 4 | 20 |
| pick_diverse_object | demo_clean | 24 | 4 | 20 |
| attribute_select | demo_clean | 96 | 16 | 80 |
| arm_select | demo_clean_arm_select_v2 | 24 | 0 | 24 |
| stack_sequence | demo_clean | 72 | 12 | 60 |
| place_relative | demo_clean | 60 | 10 | 50 |
| grasp_cube_approach | demo_clean_grasp_approach_v2 | 24 | 0 | 24 |
| 合计 | | 324 | 46 | 278 |

六个 policies 共 1,944 个 episodes，复用 276 个，补跑 1,668 个。旧评测的 324 个
episodes 中，48 个属于两个已改场景的任务，因此不复用。复用包含原来的 105 次成功和
171 次失败，不按结果筛选。

默认结果目录为 `/Data/robotwin-if/evaluations/if-seven-tasks-v2-12blocks-001`，
仓库内入口为 `outputs/policy-eval/if-seven-tasks-v2-12blocks-001`。

```bash
# 新建评测并校验复制旧结果；目标目录必须不存在。
/home/xichen6/miniconda3/envs/RoboTwin/bin/python tools/run_formal_policy_suite.py prepare

# 启动或显式恢复；长时间运行应由持久后台进程承载。
/home/xichen6/miniconda3/envs/RoboTwin/bin/python tools/run_formal_policy_suite.py run

# 只读进度。
/home/xichen6/miniconda3/envs/RoboTwin/bin/python tools/run_formal_policy_suite.py status

# 校验当前已归档的结果。
/home/xichen6/miniconda3/envs/RoboTwin/bin/python tools/run_formal_policy_suite.py verify
```

调度器只使用一个 simulator（GPU 0，显式绑定 SAPIEN 渲染设备）和一个 model server
（GPU 1）。同一个模型依次跑完各任务，再释放模型。GPU 查询超时、显存/温度超限、
日志长时间停止更新或基础设施错误会停止队列。唯一的自动重试情形是：明确的 oracle
资格阴性结果、尚未调用模型、GPU 检查正常。此时新建 simulator，对原 seed 最多重试
两次；失败次数跨调度器重启保留，所有尝试留档。GPU、网络、缓存一致性或执行异常均不走此重试。

每个 episode 的文件复制并验证 SHA-256 后，最后写入 `_provenance.json` 才计入完成数。
该文件记录来源目录、成功/失败和正式 manifest 中的 block 序号。`summary.json`、
`status.json` 和 `report.md` 在推理期间每 15 秒更新，分别显示完成 episodes 和完整 blocks；
缺任一回合的 block 不计入完成。最终要求 42 个 policy/task 组合各完成 12 blocks，
即 504 个完整 blocks、1,944 个 episodes，未跑齐不会标为 complete。

完整 manifest 始终不变。worker 跳过已有有效 provenance 的 episodes，因此中断在 block
中间也可以恢复，且不重跑已完成的 policy failure。`batches/` 保留每次启动的原始输出和
执行错误；各次 `*-resume.json` 说明跳过了哪些旧记录，`*-oracle-retry.json` 记录有限重试。
排除其他基础设施问题后，显式重新执行 `run` 才会补未完成的 episodes，不替换 seed。
同一 oracle 连续失败三次后仍保持该 block incomplete，需要复核统一资格；重启调度器不会清零次数。

原 checkpoint、指令 split 和推理参数保持一致。五个 `demo_clean` 任务使用已验证的渲染
同步优化和 oracle 缓存；两个 v2 config 当前仍使用原来的渲染与 oracle 路径。旧结果与补跑
结果的耗时应分开统计。X-VLA 的官方接口不能控制 server RNG，复用与新跑也不应宣称逐位确定。
