---
status: planning
area: robotics
created: 2026-09-18
tags: [robotwin, vla, benchmark, gpt-6-astra, policy-inference]
parent: "[[RoboTwin-IF 复刻]]"
---

# GPT-6 Astra 作为 policy 接入 RoboTwin-IF 评测：讨论与实现计划

> 本文档是**讨论稿 + 实现计划**，不是已落地的设计。目的是在动手写 `policies/gpt6_astra/` 之前，先把接口选型、与现有 policy client（`xvla`、`vlact` 等）的一致性、以及 GPT-6 Astra 这类 reasoning LLM 特有的问题（推理延迟、action chunking、跨步记忆）过一遍，避免边写边改接口。

## 背景

`feat/open-source-policy-inference` 分支下已经跑通了几个开源 VLA 的 policy client（`policies/xvla`、`policies/vlact`、`policies/hy_vla`、`policies/lingbot_vla` 等），共享同一套：

- `if_benchmark/seed_contracts.py` + `seed_manifest.py`：seed 合约与 manifest 加载
- `policies/evaluation.py`：`setup_episode()`（oracle qualification + 场景重建 + instruction 注入）、`finalize_episode_success()`
- `outputs/policy-eval/<run>/<policy>/<task>/` 统一产物目录格式（`*_summary.json`、`*_status.json`、`*_actions.npz`、`*_action_logs.json`、`*_diagnostics.json` 等）

GPT-6 Astra 不是本地权重模型，而是一个**云端 reasoning LLM API**，本质上属于"LLM-as-policy"这一类，和已有的 diffusion/VLA policy client 在**接口层**可以复用同一套 harness，但在**推理调用层**差异很大（HTTP 到自家 server vs HTTPS 到 OpenAI Responses API；单次 forward vs 多轮 reasoning + tool call；本地 GPU 推理延迟 ~100ms 级 vs 云端 API 延迟 1-10s 级）。

本文档要定下来的是：**观测怎么喂给 Astra、Astra 怎么把输出转换成 RoboTwin 能执行的 16D EE action、以及怎么在不改 `policies/evaluation.py` 共享逻辑的前提下把这条链路接进去**。

## 现有 policy client 的接口形状（作为对齐基准）

以 `policies/xvla/client.py` 为例，接口收敛到三个函数 + 一个类：

- `CAMERAS = ("head_camera", "left_camera", "right_camera")` —— 观测里固定的三路相机
- `encode_proprio(observation)` → 20D（每臂 pos(3) + rot6d(6) + gripper(1)）
- `decode_actions(actions, gripper_threshold=0.7)` → 还原成 RoboTwin 原生 16D EE action（每臂 pos(3) + quat(4) + gripper(1)）
- `XVLAClient`：持有一个 HTTP session，`act(obs) -> actions` 是唯一对外暴露的推理入口

`policies/xvla/eval.py` 不关心 checkpoint 内部编码，只负责：加载 seed manifest → `setup_episode()` 拿到 `(instruction, obs)` → 循环调 `client.act(obs)` 拿 action chunk → 执行 → `finalize_episode_success()` → `write_episode_artifacts()`。

**结论**：只要新 policy 也提供一个 `act(obs) -> (N, action_dim)` 的 client，就可以直接复用 `eval.py` 这一层的骨架，`policies/evaluation.py` 完全不用动。

## GPT-6 Astra policy client 设计

### 1. 观测 → Prompt（`encode_observation`）

不套用 X-VLA 的 20D EE6D 编码（那是特定 checkpoint 的数值约定，LLM 不需要），而是让 Astra 直接看**人类可读的状态 + 图像**：

- 三路相机图（`head_camera` / `left_camera` / `right_camera`）编码成 PNG data URL，作为 `input_image` 传入 Responses API。分辨率先沿用 RoboTwin 原始渲染尺寸，若 token/延迟成本过高再考虑下采样。
- Proprio 用文本而非编码向量喂给模型，例如：
  ```
  left_endpose: x=.., y=.., z=.., quat=[..]; left_gripper=..
  right_endpose: x=.., y=.., z=.., quat=[..]; right_gripper=..
  step=12 / step_limit=400
  ```
- instruction 就是 `setup_episode()` 返回的那句自然语言指令，原样作为 system/user prompt 的一部分，不做改写——这是 RoboTwin-IF 要测的东西（instruction-following），改写指令等于污染评测对象。

### 2. Astra 推理调用

- 走 **Responses API**，`model="gpt-6-astra"`，`reasoning.effort` 先定为 `medium`（成本/延迟 vs 质量的初始折中，需要 A/B）。
- 动作输出走**结构化 tool call**，不用自由文本坐标。初版 tool schema：
  ```json
  {
    "name": "set_ee_targets",
    "parameters": {
      "left":  {"x": "number", "y": "number", "z": "number", "quat": "number[4]", "gripper": "number"},
      "right": {"x": "number", "y": "number", "z": "number", "quat": "number[4]", "gripper": "number"}
    }
  }
  ```
  直接输出 RoboTwin 原生 16D EE 语义（绝对位姿，非 delta），跳过 rot6d 这类训练态编码，减少一层无谓的数值转换。
- **跨步记忆**：开 `include: ["reasoning.encrypted_content"]`，把上一步返回的 encrypted reasoning blob 存在 client 内部状态里，下一步 `input` 里带回去。`setup_episode()` 每个 episode 开始前会重建场景 —— client 的 `reset()` 需要在这个时机清空 encrypted_content 和对话历史，避免跨 episode 泄漏（这类似 `env.start_policy_rollout()` 的语义，但要单独在 client 侧实现，`policies/evaluation.py` 不感知这个状态）。

### 3. Action chunking 与调用频率（关键开放问题）

本地 VLA（如 X-VLA）单次 forward 是几十毫秒级，可以接近逐步闭环；Astra 一次 Responses API 调用（尤其带 reasoning）大概率是 1-10 秒级。逐 timestep 调用在 RoboTwin 的 `step_limit`（几百步量级）下会导致单个 episode 跑几十分钟到几小时，不现实。

两个方向，需要讨论定下来再实现：

- **方案 A：粗粒度 action chunk**。一次调用让 Astra 规划未来 K 步（比如 K=5~10）的末端位姿序列，中间不重新推理，类似开环执行一段再重新观测。风险：K 步内环境状态会偏离 Astra 规划时看到的画面，抓取类精细操作容易失败。
- **方案 B：subgoal + 底层插值**。Astra 只输出稀疏的关键 waypoint（比如"移动到物体上方"、"下降抓取"、"抬起"），由一段确定性代码在 waypoint 之间做线性插值/规划执行多个仿真 step。这样 Astra 调用次数少（每个 episode 可能只需 5-15 次），但需要额外写一层"从语义 waypoint 到逐步动作"的胶水代码，等于给 Astra 加了一层簇新的"手脚"，偏离了"直接让 LLM 当 policy"的初衷，需要评估这是否违背评测目的。

初步倾向**先做方案 A**（更接近纯 LLM-as-policy，工程量小，能先拿到一版可运行的 baseline 数字），方案 B 作为后续优化留在开放问题里。

### 4. 与共享 harness 的接入点

复用 `policies/evaluation.py` 不变，新增：

```
policies/gpt6_astra/
├── README.md          # 参照 xvla/README.md 的格式：安装（无需 conda env，只需 API key）、启动方式、验证状态
├── client.py           # GPT6AstraClient: encode_observation / act(obs) -> actions / reset()
├── eval.py              # 结构照抄 xvla/eval.py，把 XVLAClient 换成 GPT6AstraClient
├── outputs.py           # 复用 xvla/outputs.py 的 episode_path/write_episode_artifacts 惯例，
│                         # 额外记录每步的 reasoning effort、token 用量、API 延迟到 action_logs.json
└── requirements.txt     # 只需要 openai SDK + 现有 RoboTwin 环境依赖，无需独立 conda env
```

不需要 `setup_env.sh`（没有本地权重/CUDA 依赖），但需要一个 `check_env.py` 检查 `OPENAI_API_KEY` 是否设置、能否连通 Responses API。

### 5. 输出/记录格式的差异点

沿用 `outputs/policy-eval/<run>/gpt6_astra/<task>/` 目录和现有文件命名（`_summary.json`、`_status.json`、`_actions.npz` 等），但 `action_logs.json` 要多记录 LLM 特有字段：

- 每次调用的 `reasoning_effort`、`input_tokens`/`output_tokens`/`reasoning_tokens`
- API 请求延迟（`request_latency_sec`），单独于 `timings.json` 的 `inference_time_sec`（复用字段但来源不同，需要在文档里注明"这里的推理耗时是网络 API 往返时间，不是本地 forward 时间"）
- 是否发生了 tool call 解析失败/重试（Astra 偶发输出非法坐标或格式错误 JSON 时的 fallback 行为）
- 预估 API 成本（按 token 用量 × 当前 GPT-6 Astra 定价估算），因为这是开源 VLA client 完全没有的维度，但对评估"值不值得用 Astra 做 policy"很关键

## 开放问题（需要讨论定案）

1. **Action chunk 粒度**：方案 A（粗粒度 chunk）vs 方案 B（waypoint + 插值）—— 先出 A 版数字，还是直接做 B？
2. **图像分辨率/token 成本**：三路相机图每步都传 vs 参照 `inspect-robots-agent` 的 `images="on_demand"`（模型自己决定要不要"看一眼"）—— 后者更省钱，但要求 Astra 主动调用 `take_pic` 工具，多一层交互协议。
3. **reasoning effort 选哪个**：`medium`/`high`/`xhigh` 对成功率和延迟/成本的影响需要小样本 A/B（建议先在 `arm_select` 这种已有 baseline 结果的任务上对比，方便和 X-VLA/CogACT 的已有数字放在一起看）。
4. **失败/异常处理策略**：Astra 输出解析失败、API 超时/限流时，是按 `execution_error` 直接判该 episode 不完整（对齐 xvla 现有约定），还是允许重试 N 次？重试会进一步放大本就不便宜的 API 成本。
5. **跨 episode 的 encrypted reasoning 是否要清空**：当前设计是清空（每个 episode 独立、公平对比），但要不要做一个对照实验验证"保留跨 episode 记忆"是否会产生数据泄漏/作弊效果（比如 Astra "记住"了之前 episode 里同一类物体的位置分布）。
6. **是否需要接 `inspect-robots-xpolicylab` 的 websocket 协议**，把 Astra 包成一个 policy-server，而不是在 `policies/gpt6_astra/client.py` 里直接内嵌 HTTP 调用——如果未来要跑 RoboDojo 或者和其他 policy-server 生态对齐，走 XPolicyLab 协议更通用；如果只是在本仓库内部跑评测，直接内嵌更简单。**初步倾向先不接 XPolicyLab，跑通最小闭环后再评估要不要重构。**

## 分阶段实施计划

**阶段 0：最小闭环验证（对齐 xvla 的 "raw task smoke" 做法）**
- 写 `client.py`：`encode_observation` + `act()` + `reset()`，方案 A 的粗粒度 chunk，K 先定一个小值（比如 3）
- 写 `eval.py`：跑通一个 raw task（如 `click_bell`）的单个 exact seed，验证端到端链路（API 调用成功、tool call 能解析成合法 16D action、`finalize_episode_success` 能正确判定）
- 不追求成功率，只验证"链路通"

**阶段 1：IF 任务首个完整 block**
- 跑 `arm_select`（已有 X-VLA/CogACT 基线数字，方便横向对比）的一个完整 seed manifest block
- 补齐 `outputs.py` 里 LLM 特有字段的记录（token/延迟/成本）
- 产出第一版 `README.md`，记录验证状态（参照 `xvla/README.md` 的"验证状态与下一步"章节格式）

**阶段 2：扩大到 IF-Ext 七轴任务集**
- 补齐 seed manifest 覆盖到全部 7 个单轴任务
- 针对开放问题 1/2/3 做小样本 A/B，把结论写回本文档或拆成新的 feature 文档

**阶段 3（视阶段 2 结果决定是否需要）**
- 评估是否要做方案 B（waypoint + 插值）
- 评估是否要接 XPolicyLab 协议

## 风险与成本提醒

- **API 成本**：reasoning effort 越高、图像传得越多、chunk 越细（调用越频繁），成本上升越快；建议阶段 0/1 先用小 seed 数量估算单 episode 成本，再决定要不要跑全量 manifest。
- **延迟**：单 episode 墙钟时间可能是本地 VLA 的几十倍，`step_limit` 相关的超时/中止逻辑要重新评估是否合理（原本按本地推理速度设计的 step_limit，对云端 LLM policy 可能显得过紧或过松，需要单独看是按"墙钟时间"还是"动作步数"限制更合理）。
- **非确定性**：LLM 输出天然比训练好的 VLA policy 更不稳定（同一 seed 不同次调用可能得到不同 action），需要在 README 里明确记录"本 policy 不保证同 seed 结果可复现"，这点要和 xvla 现有文档里"服务端随机性不由 episode seed 控制"的免责声明保持一致的措辞风格。

## 参考

- `policies/xvla/`、`policies/vlact/`（分支 `feat/open-source-policy-inference`）—— 现有 policy client 的接口范式
- `policies/evaluation.py` —— 共享 harness（oracle qualification / episode setup / success finalize）
- [robocurve/inspect-robots](https://github.com/robocurve/inspect-robots) 的 `plugins/inspect-robots-agent`（LLM-as-policy 的 observation/action 组装 + Responses API 调用参考实现）与 `plugins/inspect-robots-xpolicylab`（如果未来要接 XPolicyLab 协议）
- [OpenAI Reasoning models 文档](https://developers.openai.com/api/docs/guides/reasoning) —— `reasoning.encrypted_content` 跨轮传递机制
