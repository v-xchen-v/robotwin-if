# Bottle Hold / Place 实验

分支：`experiment/bottle-hold-place`。独立任务名：`bottle_hold_place`。

本实验比较同一画面下的两条指令：

| Mode | 固定 instruction | 目标 |
|---|---|---|
| hold | `Hold the bottle steadily above the blue pad.` | 将瓶子移到蓝垫上方，悬空握持并稳定 |
| place | `Place the bottle on the blue pad and release it.` | 将瓶子拿起，放到同一个蓝垫上并释放，保持稳定 |

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
- 两边的 policy 预算均为 **700 个完整动作**，中途不成功早停；使用末尾连续至少 **2 秒仿真时间**的稳定状态。
  推理等待和反复查询判据不累计时间。物理采样频率为 50 Hz。
- 瓶子几何中心的水平投影距离垫子中心不超过 **5 cm**。稳定期间位移容差 **1.5 cm**，旋转容差 **10°**。
- Hold：瓶子与夹爪接触、与垫子不接触；瓶子包围盒最低点高于垫面 **5–20 cm**。
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

先执行上述 oracle 配对资格检查，再复用 X-VLA evaluator 的真实 policy rollout、末尾裁决和视频/动作产物。
`summary.json` 同时报 hold、place 的成功数和整对均成功数。正常完成的 policy failure 保留；执行错误标记为不完整。
目前独立入口提供 oracle 和 X-VLA；这不构成六模型正式评测。`seen/unseen` 在此仅是接口兼容值，两者使用同一句固定指令。
HTTP 服务端 checkpoint 为运行者声明，服务端随机数不受 episode seed 控制。

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
<output>/xvla/                       # 选用 --policy xvla 时产生
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

真实仿真使用当前 task / monitor 源码（SHA-256 与运行产物核对一致），连续覆盖 seeds 0–7：

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
