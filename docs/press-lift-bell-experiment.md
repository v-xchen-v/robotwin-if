# Press / Lift Bell 实验

分支 `press_lift_bell`，从 master `8035546` 新建。旧瓶子实验已保存在
[`experiment/bottle-hold-place` 的 e7a7f7c](https://github.com/v-xchen-v/robotwin-if/commit/e7a7f7c)。

本任务在铃铛、鼠标、玩具车的共享场景中，用一个可移动铃铛比较 `Press the bell.` 和 `Lift the bell.`。去掉第二个目标、搬运和长时间悬停，
测试第一项完成的动作是否符合指令；不加入正式六任务成绩。

## 场景与原生依据

- Episode `2k` 为 press，`2k+1` 为 lift。完整初始化（包括相机、背景、机器人）均使用 scene seed `k`。
- 同一对共享动态 `050_bell`、0.05 kg 质量、碰撞网格和所有物理参数；mode 不参与场景生成。
- 铃铛置于桌面近处，左右交替；scene 0/1 使用 model 0，scene 2/3 使用 model 1。
- 默认 `--scene-layout context`：后侧固定摆放 `047_mouse/base0` 和 `057_toycar/base0`，均为动态 0.05 kg 原生资产，
  与铃铛间距约 30 cm 以上，避开近处的操作路径；没有秤、展台或目标垫。`--scene-layout bare` 保留单铃铛基线。
  布置区别于原生单铃铛 click 和“物体+展台”place 场景，降低整场景模板识别的机会；不能保证消除铃铛的按压先验。
  陪衬物体带来少量目标识别要求，但只有一个铃铛，指令无需增加颜色、位置或手臂描述。
  主指标是同一画面下两条指令都成功，不能仅凭总成功率声称模型理解动词。
- 两句只改变动词，不指定手臂。`seen/unseen` 仅为 runner 兼容值，实际都返回同一句固定指令。
- 原生 `click_bell` 支持按压，但使用静态铃铛；原生 `place_object_scale` / `place_object_stand` 的动态资产池
  包含铃铛，oracle 会先抓起它。它们的 instruction 是完整搬运任务，不能证明模型见过独立的 `Lift the bell.`。

## 判据

[物理监测器](../tasks/envs/_press_lift_bell.py) 每 0.02 秒仿真时间采样；推理等待不计时。
两个指令共用同一个、与 mode 无关的动作分类器。最大动作数均为 **250**。

- Lift：铃铛相对初始位置抬高至少 **3 cm**，与闭合夹爪实际接触、与桌面不接触，连续 **0.10 秒**。
  不要求搬运、特定朝向或长时间稳定。碰撞接触点须有非零物理冲量（范数 > 1e-7），不把近邻接触算抓持。
- Press：夹爪预先闭合至少 **0.08 秒**，自闭合后且无接触的接近过程中累计下降至少 **5 mm** 后首次接触铃铛顶端区域；
  接触时铃铛由桌面支撑。随后闭合夹爪向上撤离至少 **2 cm**，与铃铛无抓持接触且桌面支撑持续 **0.06 秒**。
  从触碰到撤离期间铃铛上升不得超过 **1.5 cm**，水平位移不得超过 **3 cm**。
  顶端区域沿用原生 contact point 0 周围 XY 各 **2.5 cm**、Z **3 cm** 的接触代理。
- 按第一项完成的动作锁定结果。先 press 后 lift 只能通过 press 指令，反之亦然。
  正确动作可提前成功结束；先做错动作后，仍保留余下最多 250 动作的诊断轨迹，结果不会翻转。
  未完成任何动作是超时失败。单次接触不计按压，抓取时闭合夹爪也不直接计按压。

铃铛资产没有可动按钮或声音模拟，press 是“闭合夹爪从上方接触、随后撤离”的物理代理，不能称为按钮实际被按响。
这个实验测首个完成动作；不衡量最终保持状态，也不要求 lift 后仍保持到预算末尾。
判据先在 oracle 上验证再冻结，模型结果不用于调阈值。模型失败可能来自语言、动作执行或此代理的限制，需结合轨迹分析。

## 入口与产物

前提：仓库根目录，已安装 RoboTwin SAPIEN/cuRobo 环境及资产。输出目录必须不存在。

```bash
/home/xichen6/miniconda3/envs/RoboTwin/bin/python tools/press_lift_bell.py \
  --pairs 4 --sim-gpu 0 --output-dir outputs/policy-eval/press-lift-bell-oracle-new
```

这会运行完整配对 oracle，保存每回合图片、视频、物理信号、初始三路 RGB/proprio 数组与配对资格报告。
`--scene-seeds 0 3` 可选两个明确场景，始终展开完整 press/lift 对；不能用失败替换 seed。

启动现有模型服务后，可运行：

```bash
/home/xichen6/miniconda3/envs/RoboTwin/bin/python tools/press_lift_bell.py \
  --scene-seeds 0 3 --policy xvla --sim-gpu 0 \
  --output-dir outputs/policy-eval/press-lift-bell-xvla-new
```

`--policy` 支持 oracle、xvla、lingbot_va、lingbot_vla、vlact、dm05、hy_vla，端口沿用现有服务。
每次运行先通过完整配对 oracle，再逐回合复用现有 policy evaluator；推理前逐数组核对 RGB、统一编码 proprio、
指令及动作预算。共享 evaluator 仅补充 opt-in `policy_instruction` 接口，旧任务继续走原模板生成器。

| 产物 | 含义 |
|---|---|
| `run.json` / `resolved_config.json` | 参数、Git 身份、源码/配置哈希和实际配置 |
| `oracle/qualification.json` | 两边可行性和初始数组完全相同的证据 |
| `oracle/*_trace.jsonl` / `*_oracle.mp4` | oracle 物理轨迹（10 Hz 写盘）与视频 |
| `<policy>/*_result.json` / `*_actions.npz` / `*_[01].mp4` | 真实模型结果、动作和视频 |
| `<policy>/physics/*.jsonl` | 完整 50 Hz 物理监测轨迹，含先完成动作和接触信号 |
| `<policy>/*_scene_check.json` | 推理前观测、指令、预算核对 |
| `results.jsonl` / `summary.json` | 逐回合追加记录、press/lift 各自成功数及两边均成功数 |

产物位于 Git 忽略的本机 `outputs/`；文档中的路径不表示已上传运行产物。
所有已完成的 policy failure 保留；oracle / 服务错误与行为失败分开，禁止静默补抽场景。

## 验证记录

2026-10-23：10 项 classifier/runner 测试通过，9 项共享 setup 测试通过，六个 evaluator 的末尾裁决回归通过。
测试覆盖错误接触、闭合抓取、无抓持弹起、抬起后放回、时间中断、首动作不可翻转和固定 instruction 接线。

第一轮真实 oracle（`outputs/policy-eval/press-lift-bell-oracle-001`）在 model 0 的左右场景上 4/4 成功；
两组初始 RGB/proprio 完全相同。按压最高上升约 0.7 mm，lift 抬高约 10 cm。该轮尚无模型推理。

第二轮 `outputs/policy-eval/press-lift-bell-oracle-002` 覆盖两款铃铛、左右两侧，共 **8/8 成功**，
4 对初始三路 RGB/proprio 均完全一致，所有 press oracle 的首动作是 press，lift oracle 的首动作是 lift。
此阶段仅调整了 runner 的 policy 轨迹存储位置；任务和物理判据未修改。模型评测前将对最终 runner 再做配对资格检查。

随后的最终预检查（`press-lift-bell-six-models-2blocks-001/preflight`）中，seed 6 的固定深度 press oracle
把动态铃铛顶离桌面，该轮资格检查失败，**未启动任何模型推理**。此前 8/8 不能证明 oracle 每次都稳定。
已保留失败轨迹，并仅将 oracle 的固定 4.5 cm 下降改成先下降 2.5 cm、再以 2 mm 小步接近，检测到接触后撤离。
动态物理参数、instruction、250 动作预算和 v1 分类器全部不变。新版在 `press-lift-bell-six-models-2blocks-002` 验证。


小步 oracle 在 `002/preflight` 中未再出现顶飞，但 4 个 press 均未通过 v1 的“0.5 秒内下降 5 mm”速度条件；
4 个 lift 全部通过，仍未启动模型。此速度要求并非按压语义所需，v2 改为自闭合/上次接触后无接触接近阶段的
累计下降距离，同时保留预闭合、顶部接触、撤离、支撑和位移上限；短暂接触中断也不会清掉已经确认的按压候选。
新增慢速按压和接触抖动反例测试。最终评测改用 v2，前述 v1 历史结果不混入新分数。


v2 单铃铛验证（`003/preflight`）8/8 成功，4 对初始 RGB/proprio 全部相同。
随后根据用户对原生场景识别捷径的担忧，新增三物体 context 布置并保留 bare 基线；v2 判据、指令和铃铛位置不变。
六模型仍未启动，新的主实验使用 `press-lift-bell-six-models-2blocks-004`。

最终 context 场景的 `004/preflight` 已完成 **8/8 oracle 成功**（press 4/4、lift 4/4），覆盖两款铃铛与左右两侧。
4 对初始 RGB/proprio 完全一致；陪衬鼠标和玩具车未离开各自初始位置。11 项新任务测试通过。
本阶段只证明三物体场景中两种动作可行，尚无模型能力结论。
