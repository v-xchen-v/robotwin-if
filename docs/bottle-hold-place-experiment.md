# Bottle Hold / Place 实验

分支：`experiment/bottle-hold-place`。独立任务名：`bottle_hold_place`。

本实验比较同一画面下的两条指令：

| Mode | 固定 instruction | 目标 |
|---|---|---|
| hold | `Pick up the bottle and hold it steady above the blue pad.` | 将瓶子拿起，移到蓝垫上方，悬空握持并稳定 |
| place | `Pick up the bottle and place it on the blue pad, then release it.` | 将瓶子拿起，放到同一个蓝垫上并释放，保持稳定 |

两条共享 `Pick up the bottle and` 前缀和 `the blue pad` 目标称谓，明确两个模式都需要先抓起瓶子。
区别集中在终态：`hold it steady above` 要求悬空握稳；`place it on ... then release it` 要求放到垫上并松手。
不指定手臂或直立姿态，不添加 shake 等其他动作词，也不随机抽取瓶子的颜色、品牌描述。
本轮只使用这对固定句子，`seen/unseen` 都返回相同文字；同义改写留待单独的措辞鲁棒性实验。
实际文字的唯一来源是 `tasks/envs/_bottle_hold_place.py` 的 `INSTRUCTIONS`，oracle 和 policy 共用。

使用 RoboTwin 已有抓取、搬运、放下动作，探索新的完整任务组合。并不据此声称两个组合对每个模型都同等熟悉。
本实验保留瓶子本身的动作先验；默认 shake 在两个模式下均不会直接满足末尾稳定条件。

旧 `bottle_verb` 的实现、指令、判据、预算和结果保持原样。新任务不加入正式六任务 inventory、seed manifests
或整体分数。独立入口只扩展当前进程的 `envs` 模块搜索路径，不向 RoboTwin checkout 安装软链或改配置。

## 场景与判据

- Episode `2k` 为 hold，`2k+1` 为 place。整个场景初始化都使用 `k`，包括相机、背景、机器人和物体。
- 初始瓶子侧躺于桌面，蓝色静态垫子位于前方。pilot 使用 `001_bottle` 的 13、16 号模型；左右臂侧交替，
  每种瓶子覆盖两个臂侧。两条指令不指定手臂，判据接受任一夹爪对瓶子的实际接触。
- Oracle 共用抓取、抬起、调整瓶子直立和移到蓝垫上方的路径；place 随后下降、松手和撤离。
  Oracle 的直立姿态是实现选择，policy 判据不要求特定绝对朝向。
- 两边的 policy 预算均为 **700 个完整动作**，中途不成功早停；仅在预算结束时裁决，hold 要求末尾连续至少
  **5 秒仿真时间**稳定悬停，place 要求末尾连续至少 **2 秒仿真时间**稳定放置。
  推理等待和反复查询判据不累计时间。物理采样频率为 50 Hz。
- 瓶子几何中心的水平投影距离垫子中心不超过 **5 cm**。稳定期间位移容差 **1.5 cm**，旋转容差 **10°**。
- Hold：瓶子与夹爪接触、与垫子不接触；瓶子包围盒最低点高于垫面 **5–20 cm**。
  松手、碰垫、离开位置或高度范围、位移或转角超出稳定容差，都会重启连续悬停计时。
  即使曾悬停满 5 秒，随后放下且没有重新完成末尾 5 秒悬停，也不算 hold 成功。
- Place：此前曾被夹爪拿起至少 5 cm，当前与垫子接触、与夹爪无接触。放在桌面、仍握住瓶子碰垫子，
  或只把瓶子推到垫子上均不通过。支撑接触加中心位置判定不要求整个瓶子轮廓都位于垫子边界内。
- 两种成功状态互斥。允许前期失误后纠正，最终需要重新完成稳定窗口；不附加“整段轨迹绝不能摇过”的隐藏要求。
  小于稳定容差的运动可能被接受；累计竖直路程和转角只作为诊断，不自动解释为模型意图。

源码：[`bottle_hold_place.py`](../tasks/envs/bottle_hold_place.py)，
独立物理判据：[`_bottle_hold_place.py`](../tasks/envs/_bottle_hold_place.py)。
共享 evaluator 仅增加可选 `policy_instruction(split)` 接口：新任务提供固定文字及 mode；已有任务仍走原生成路径。

## 运行

在仓库根目录，使用已安装 SAPIEN / cuRobo 和 RoboTwin assets 的 `RoboTwin` Conda 环境。
输出目录必须是新目录。入口支持 `--robotwin-dir`、`--task-config`、`--sim-gpu`；pilot 会固定为 clean 场景，
有效配置写入 `resolved_config.json`。`--start-pair K --pairs N` 总是运行完整的连续配对，不换 seed、不补抽失败。
`--blocks` 是 `--pairs` 的别名；也可用 `--scene-seeds 0 3` 明确选择两个场景，展开为完整的 seeds `0/1`、`6/7`。
后者覆盖瓶子 13 的左侧场景与瓶子 16 的右侧场景；不能同时指定连续 block 选项。

```bash
conda run --no-capture-output -n RoboTwin python tools/bottle_hold_place.py \
  --pairs 4 --sim-gpu 0 \
  --output-dir outputs/policy-eval/bottle-hold-place-oracle-new
```

每一对都运行两种 oracle，核对三路初始 RGB 和 proprio **逐数组完全相同**，保存初始/最终图片、oracle 视频、
物理轨迹和逐回合结果。可用 `--no-video` 跳过视频，仍保留图片与轨迹。
只有两边 oracle 均成功且观测一致，整对才合格；任意配对不合格时整个 policy pilot 不启动。

准备好现有 X-VLA HTTP 服务后：

```bash
conda run --no-capture-output -n RoboTwin python tools/bottle_hold_place.py \
  --pairs 4 --policy xvla --server-url http://127.0.0.1:8010 --sim-gpu 1 \
  --output-dir outputs/policy-eval/bottle-hold-place-xvla-new
```

入口支持 `--policy xvla / lingbot_va / lingbot_vla / vlact / dm05 / hy_vla`。
先按[对应 policy 的说明](../policies/README.md)启动独立模型服务；省略 `--server-url` 时使用其标准本机端口。
例如对已启动的 DM05 服务运行两个指定场景：

```bash
conda run --no-capture-output -n RoboTwin python tools/bottle_hold_place.py \
  --scene-seeds 0 3 --policy dm05 --sim-gpu 0 \
  --output-dir outputs/policy-eval/bottle-hold-place-dm05-new
```

先执行上述 oracle 配对资格检查，再复用所选 policy 的现有 evaluator、末尾裁决和视频/动作产物。
每次 policy 初始化后、请求模型前，还会逐数组核对初始 RGB 与统一编码的 proprio，并检查固定指令和动作预算；
结果写入 `_scene_check.json`。模型自己的动作编码、历史状态和推理参数沿用现有客户端默认值。
`summary.json` 同时报 hold、place 的成功数和整对均成功数。正常完成的 policy failure 保留；执行错误标记为不完整。
本任务仍为独立实验，不加入正式六任务成绩。`seen/unseen` 在此仅是接口兼容值，两者使用同一句固定指令。
`run.json` 记录服务端 metadata（接口提供时）、实际参数及适配器源码哈希。
X-VLA 的服务端 checkpoint 为运行者声明，服务端随机数不受 episode seed 控制；其余模型使用原适配器的 seed 接口。

输出结构：

```text
<output>/run.json                    # Git 身份、源码和配置哈希
<output>/resolved_config.json
<output>/oracle/qualification.json   # 每对可行性与初始数组一致性
<output>/oracle/*_initial.npz / .png
<output>/oracle/*_terminal.png
<output>/oracle/*_oracle.mp4
<output>/oracle/*_trace.jsonl
<output>/oracle/*_result.json / *.log
<output>/<policy>/                   # 逐回合 policy 产物与 _scene_check.json
<output>/results.jsonl               # 每个 policy 回合完成后追加记录
<output>/summary.json
```

CPU 回归使用相同 Conda 环境（共享 evaluator 测试需要其 client 依赖，但不连接服务或启动仿真）：

```bash
conda run --no-capture-output -n RoboTwin python -m unittest discover \
  -s tests -p test_bottle_hold_place.py -v
```

## 本次验证

2026-10-23：判据、指令接线、配对统计和两种 mode 的完整动作预算裁决已通过 CPU 回归。
新任务、共享 setup、六个 evaluator 末尾裁决、旧 bottle 判据共 **53 个测试通过**；正式任务 inventory
的 **52 项静态检查通过**。旧任务源码、helper、instruction 和正式 inventory 相对 `master` 没有改动。

下列真实仿真对应 commit `867ddc7` 的 task / monitor 源码（SHA-256 与运行产物核对一致），连续覆盖 seeds 0–7。
这些是 **v1 判据（hold / place 均为 2 秒）**的历史验证，不能作为当前 5 秒 hold 判据的通过证据：

| Bottle model | Seeds | Hold | Place | 两边均成功、初始数组完全相同 |
|---|---|---|---|---|
| 13 | 0–3 | 2/2 | 2/2 | 2/2 pairs |
| 16 | 4–7 | 2/2 | 2/2 | 2/2 pairs |

本机验证产物：

- [第一款瓶子资格检查](../outputs/policy-eval/bottle-hold-place-oracle-003/oracle/qualification.json)：图片、轨迹和逐回合结果。
- [第二款瓶子资格检查](../outputs/policy-eval/bottle-hold-place-oracle-004/oracle/qualification.json)：另含四段 oracle 视频。
- [Hold 视频](../outputs/policy-eval/bottle-hold-place-oracle-004/oracle/bottle_hold_place_ep4_oracle.mp4) /
  [Place 视频](../outputs/policy-eval/bottle-hold-place-oracle-004/oracle/bottle_hold_place_ep5_oracle.mp4)。

这些是本机 `outputs/` 下的忽略产物，不随 Git 提交分发。8/8 只说明这四个场景的 oracle 可行；不是大规模可靠性结果。
尚未运行模型推理，不据 oracle 结果声称模型会 follow。视频已录制，本次验收依据是物理信号和初始数组核对。

2026-10-23 后续指令更新：在两条指令前统一补充拿起动作，形成本文开头的固定指令对；场景、oracle 动作和成功判据不变。
`oracle-001`–`004` 均为更新前的运行产物，保存的是旧版 `Hold the bottle steadily above the blue pad.` /
`Place the bottle on the blue pad and release it.`。本次文字更新后通过新任务的 11 个 CPU 回归测试；未重新运行仿真或模型推理。

2026-10-23 后续运行接线：独立入口扩展到六个现有开源 policy，增加显式场景选择和推理前观测核对。
新任务 CPU 测试为 13/13 通过；另通过覆盖六个 evaluator 成功 / 失败两种末尾裁决的回归测试。

2026-10-23 悬停判据更新：checker 升为 `bottle-hold-place-v2-terminal-10s-hold`，将 hold 连续稳定窗口
从 2 秒延长到 10 秒，place 仍为 2 秒；oracle 按 mode 等待对应窗口再加 0.5 秒余量。两个模式仍跑完
700 个 policy 动作，指令和场景未变。17/17 新任务 CPU 测试通过，覆盖 10 秒边界、短暂停顿后放置、
悬停中断后重新计时和末尾裁决；六个 evaluator 的成功 / 失败产物回归也通过。
本次未启动真实仿真或恢复模型评测，v2 尚无 oracle 可行性结果；历史 v1 产物保持原样。

2026-10-23 重跑准备：前次暂停运行中，scene 0 的 place oracle 末尾已经接触垫子并松手，但释放后的晃动
重启了稳定计时，终态仅累计 1.68 秒。因此将 oracle 的额外物理稳定等待余量从 0.5 秒增至 3 秒；
判据仍为 hold 10 秒 / place 2 秒，policy 预算仍为 700 动作。重跑使用新输出目录保留全部历史产物。

2026-10-23 用户将本轮 hold 窗口调整为 **5 秒**，以减少额外持续控制能力的影响。checker 升为
`bottle-hold-place-v3-terminal-5s-hold`；place 仍为 2 秒，oracle 的额外稳定等待余量仍为 3 秒。
10 秒版本的 `bottle-hold-place-six-models-2blocks-002` 在 oracle 阶段停止，没有启动模型推理。
5 秒版本使用 `bottle-hold-place-six-models-2blocks-003`，相同 scenes 0 / 3，每个模型运行 2 个完整 blocks。

## 5 秒判据的六模型 pilot 结果

2026-10-23：已完成 **24/24 个 policy 回合**，每个模型各 2 个完整 blocks，episode seeds 为 0 / 1 / 6 / 7。
所有回合使用 `bottle-hold-place-v3-terminal-5s-hold`（hold 5 秒、place 2 秒），均运行完整 700 动作。

| Model | Hold | Place | 整对均成功 |
|---|---|---|---|
| X-VLA | 0/2 | 0/2 | 0/2 |
| LingBot-VA | 0/2 | 0/2 | 0/2 |
| LingBot-VLA | 0/2 | 0/2 | 0/2 |
| VLAct | 0/2 | 0/2 | 0/2 |
| DM05 | 0/2 | 0/2 | 0/2 |
| Hy-VLA | 0/2 | 0/2 | 0/2 |

12 个 hold 回合的末尾瓶子中心均超出垫子中心 5 cm 的范围，最近也相距约 11.6 cm。
因此这些 hold 失败都已经违反位置条件；仅缩短稳定窗口不会改变这些回合的末尾裁决。
这里依据物理信号描述终态，不据此认定模型的动作意图或整段轨迹；2 个 blocks 也不足以给模型排名。

VLAct seed 7 的首次尝试、DM05 seed 7 的前两次尝试在 oracle 阶段失败，均为 **0 次推理、0 个模型动作**。
保留这些错误产物后，仅在全新仿真进程中重试相同 seed，分别在总第 2 / 3 次尝试通过 oracle 和初始观测核对，
再各执行一次完整 policy 回合。没有重跑已经完成的 policy failure，没有替换 seed 或调整 policy 判据。
原 `runs/vlact/summary.json` 和 `runs/dm05/summary.json` 保留首轮不完整状态；下面的根目录汇总合并了补跑结果。

最终校验确认：跨模型初始三路 RGB 和统一编码的 proprio 完全相同，指令与判据一致；
24 个回合均有完整动作记录和可解码的 **701 帧**视频。所有评测进程及模型服务已退出。

- [汇总及逐回合视频](../outputs/policy-eval/bottle-hold-place-six-models-2blocks-003/results.md)
- [机器可读汇总](../outputs/policy-eval/bottle-hold-place-six-models-2blocks-003/summary.json)
- [产物校验记录](../outputs/policy-eval/bottle-hold-place-six-models-2blocks-003/validation.json)
- [仅针对推理前错误的重试记录](../outputs/policy-eval/bottle-hold-place-six-models-2blocks-003/recoveries.json)
