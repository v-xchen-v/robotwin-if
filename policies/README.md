# Policy inference integrations

每个策略使用一个小写目录 `policies/<policy_name>/`，维护自己的推理环境、配置、适配代码与使用说明。采用复数 `policies`，与上游 RoboTwin 的 `policy/` 安装目录区分。

`arm_select` 的可选场景变化配置、双臂预检与独立 manifest 使用方式见
[arm_select v2 试验说明](../docs/arm-select-v2.md)。

`grasp_cube_approach` 的可选平移配置、顶抓/侧抓配对预检见
[grasp approach v2 试验说明](../docs/grasp-approach-v2.md)。

七任务正式评测使用 [if-ext-v2-12-per-mode](../seed-manifests/if-ext-v2-12-per-mode/README.md)：
每项 12 blocks，同名的 arm_select / grasp_cube_approach 采用 v2，附已有结果复用索引与待跑 seeds。

```text
policies/
├── README.md
├── xvla/                 # HTTP, stateless chunks, 20D EE6D
├── lingbot_vla/          # WebSocket, 4B VLA, absolute 14D joint chunks
├── hy_vla/               # WebSocket, six-frame MEM, blended rel+abs EE targets
├── dm05/                 # HTTP, Gemma3/action expert, absolute 14D joint chunks
├── vlact/                # WebSocket, Qwen3OFT, wrap32 absolute joint chunks
└── lingbot_va/           # WebSocket, KV cache, relative EE poses
    ├── README.md
    ├── setup_env.sh
    ├── requirements.txt
    ├── requirements-client.txt
    ├── download_checkpoint.py
    ├── serve.py
    ├── client.py
    ├── eval.py
    ├── outputs.py
    ├── patch_source.py
    └── check_env.py
```

| Policy | Checkpoint | Conda inference environment | 当前状态 |
|---|---|---|---|
| [X-VLA](xvla/README.md) | `2toINF/X-VLA-RoboTwin2` | `robotwin-if-xvla` | 初次闭环已验证：raw `click_bell` 1/1；IF `arm_select` 左成功、右失败（1/2） |
| [LingBot-VA](lingbot_va/README.md) | `robbyant/lingbot-va-posttrain-robotwin` | `robotwin-if-lingbot-va` | 初次闭环已验证：raw `click_bell` 1/1；IF `arm_select` 左右均成功（2/2） |
| [LingBot-VLA 4B](lingbot_vla/README.md) | `robbyant/lingbot-vla-4b-posttrain-robotwin` | `robotwin-if-lingbot-vla` | raw `click_bell` 1/1 成功；IF `arm_select` 完整左右 block 为 0/2，均达到动作上限，IF 成功验收尚未通过 |
| [VLAct Qwen3OFT](vlact/README.md) | `StarVLA/VLAct_Qwen3OFT_Robotwin_Finetune` | `robotwin-if-vlact` | 初次闭环已验证：raw `click_bell` 1/1；IF `arm_select` 完整左右 block 为 1/2（左达到动作上限、右成功） |
| [DM05](dm05/README.md) | `Dexmal/DM05-robotwin2` | `/Data/robotwin-if/envs/robotwin-if-dm05` | 初次闭环已验证：raw `click_bell` 1/1；IF `arm_select` 完整左右 block 为 2/2 |
| [Hy-VLA](hy_vla/README.md) | `tencent/Hy-Embodied-0.5-VLA-RoboTwin` | `/Data/robotwin-if/envs/robotwin-if-hy-vla` | 真实 checkpoint：raw `click_bell` 1/1；IF `arm_select` 完整左右 block 为 0/2，均达到 400 步上限，IF 成功验收尚未通过 |

## 环境与源码约定

- RoboTwin 仿真运行在独立的 `RoboTwin` 环境；模型服务运行在各自的 `robotwin-if-<policy>` 环境，通过客户端通信。
- 每个目录至少提供 `setup_env.sh`、依赖声明和 README；随后按需加入客户端/adapter 和推理配置。
- 第三方模型源码放在 `third_party/<policy>/`，setup 固定其 revision。模型权重保留在 Hugging Face cache 或外部 checkpoint 目录。
- 环境目录、第三方 checkout、权重和运行日志不加入 Git。这里维护安装方法及适配代码。
- 先完成一至两个策略，再从实际实现中提取公共层；公共层的目录和接口在该阶段确定。
- 评测输出统一采用 `outputs/policy-eval/<run>/<policy>/<task>/`，以 `<task>_ep<seed>` 平铺保存 summary、status、指令、日志、视频、初始图像、逐步耗时和 chunk 动作日志，参考 `smoke-blocks1/cogact/arm_select/`。可增加策略专用诊断文件；未采集字段明确标为 `null`。X-VLA 的文件语义与离线转换见其 [README](xvla/README.md#输出格式)。

## 每个策略的验收顺序

1. 安装环境并检查模块导入，启动真实 checkpoint 的推理服务。
2. **先成功完成一个 raw RoboTwin task**，记录命令、配置、seed、结果和视频。
3. **再成功完成一个选定的 RoboTwin-IF task**，使用完整的 balanced seed block 并保留失败记录。

环境检查通过只表示依赖可以导入。任务验证通过后才将策略标记为 inference 已验证。X-VLA 暂定按 `click_bell` → `arm_select` 验证。后续 refactor 和 external RoboTwin bridge 也沿用这一顺序。

## 完整 IF task suite 的小规模评测

六个 `eval.py` 均支持 canonical 七项 IF task。使用同一份固定 manifest，
`--blocks 2` 选择前两个完整 balance blocks，每种 mode 各运行两个回合：

```bash
PYTHONNOUSERSITE=1 conda run --no-capture-output -n RoboTwin \
  python policies/xvla/eval.py \
  --task attribute_select --task-config demo_clean \
  --seed-manifest seed-manifests/if-ext-v1-100-per-mode/attribute_select.json \
  --blocks 2 --instruction-type unseen --sim-gpu 0 \
  --output-dir outputs/policy-eval/if-blocks2/xvla/attribute_select
```

替换 policy 和 task 即可；模型服务须已在对应默认端口运行。同一个 policy 的
有状态服务一次只接一个评测客户端。七项合计每个 policy 54 回合、六个 324 回合。
输出保留固定 seeds、每种 mode 的分母和成功数；基础设施错误标为 incomplete，
不会用新 seed 替换。源码/config 与 manifest 发布版本有差异时，先对选定的
完整 blocks 在当前环境下重新做 oracle qualification，并保留两份 provenance。

属性选择与抓取方向任务在 setup 后即可读取抬起高度基线。抓取方向的
`start_policy_rollout()` 使成功检查采集 policy 首次夹爪接触时的 TCP 方向；
同次接触中的后续转腕不改变抓取方向，无接触时方向信号为 false。报告应同时
列出 `orientation_match` 与 `lifted`，保留任务的联合成功指标。

## 单路评测的渲染与 oracle 优化

六个 evaluator 默认对上述七项 IF task 的 `demo_clean` 启用两项优化：

- `--render-sync observation`：仅推迟 `take_action` 内重复的渲染状态同步，
  `get_obs()` 始终同步后再取图。物理子步、逐子步成功检查、逐动作观测、
  Hy-VLA/LingBot-VA 的历史更新及每步视频都保留。oracle/setup 的同步不变。
- oracle 缓存默认放在 `outputs/policy-eval/oracle-cache/`，可用
  `--oracle-cache-dir /Data/robotwin-if/oracle-cache` 指定六个 policy 共用的位置。
  首次执行完整 oracle 并保存其信息、指令和 policy 初始场景；后续运行仍重新
  setup policy 场景，对三路 RGB 做逐字节哈希核对，对 EE/关节状态以 `1e-6`
  绝对容差核对，同时核对 mode、指令和动作上限。任何不匹配都报执行错误，
  不替换种子。瓶子、属性选择的配对场景验证也复用实际通过的 oracle 证据。

缓存身份包含 RoboTwin envs/task_config/description/assets、仓库任务及 seed
代码、公共 evaluator 代码、解析后的仿真配置、依赖版本、Python 环境与驱动版本。
第一次需读取资源计算 SHA-256；随后每个 evaluator 重新扫描文件，用
device/inode/size/mtime/ctime 判断是否需要重算内容哈希。源码、资源或配置改变
会产生新的缓存身份；运行过程中应保持这些输入不变。旧评测的 `oracle.json`
不能直接当作新缓存使用，因为缺少完整身份和初始场景证据。

raw task、随机化配置等未验证组合自动走原流程。需要完全回退进行对照时，
给任一 evaluator 增加 `--render-sync legacy --no-oracle-cache`。`run.json`
记录优化配置、缓存身份和公共代码哈希；每回合 `result.json` 额外记录缓存
命中情况、oracle/setup 耗时及实际跳过的渲染同步次数。

这两项优化不改变 GPU 调度。继续使用显式绑定设备的单仿真/单模型串行启动方式。
用于检查画面、状态和成功判定的真实动作回放工具如下（需要已完成的 IF 套件）：

```bash
PYTHONNOUSERSITE=1 conda run --no-capture-output -n RoboTwin \
  python tools/benchmark_eval_optimizations.py \
  --suite /Data/robotwin-if/evaluations/if-seven-tasks-2blocks-001 \
  --output /Data/robotwin-if/evaluations/optimization-replay-001 \
  --oracle-cache-dir /Data/robotwin-if/evaluations/optimization-oracle-cache-001 \
  --sim-gpu 0
```

该工具逐个运行七项任务的原流程、首次缓存和缓存命中三组完整动作回放，
比较每一步 RGB、机器人状态、成功信号和视频帧数，并保存耗时和 GPU 记录。
EE 规划器的原生重复求解也可能产生差异，因此 EE 对照组共用一次参考运行
记录的关节规划；关节动作则直接使用原始指令。回放不加载模型，耗时对比
仅代表仿真和准备阶段（不含模型推理和 EE 求解），不能直接当作完整评测加速比。
