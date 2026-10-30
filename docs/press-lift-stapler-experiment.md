# Press / Lift Stapler：当前场景、指令与判据

当前 Verb-Select 任务为 `press_lift_stapler`，属于[六任务、每任务 20 blocks 的正式清单](../seed-manifests/20-blocks/README.md)。
随机朝向场景完成 20 组资格筛选，expert Press 20/20、Lift 20/20；六个开源 checkpoint 的正式评测也已完成，见[结果包](../result/README.md)。

## 指令与场景

| Mode | Instruction |
|---|---|
| press | `Press down on the stapler.` |
| lift | `Lift the stapler.` |

对象短语均为 `the stapler`，只改变动作短语。`seen` / `unseen` 返回相同的 mode 指令，是接口别名。
Episode seed `2k` 为 Press，`2k+1` 为 Lift；初始场景使用 scene seed `k`。
正式 seeds 为 `110000–110039`，包含 20 个配对场景。

目标使用原生 `048_stapler` 的 model 0 / 4，两个 modes 都是质量 0.05 kg 的动态物体。
目标左右位置和干扰物位置由 scene seed 决定；干扰物为鼠标、玩具车，场景没有目标垫。
订书器绕世界 Z 轴随机旋转 ±15°；两个干扰物分别在 ±180° 内随机旋转。
各物体使用独立的随机流，Press/Lift 配对共享位置、朝向、三路初始 RGB 与机器人状态。

原生 `move_stapler_pad` 包含 Lift / Pick up 动作以及后续放到垫上的步骤。
当前 Lift 保留抓持和抬升动作，去掉目的地、放置动作和详细对象描述；它不是原生完整任务句子的逐字复制。
原生模板中存在某个动作，不等于某个 checkpoint 见过这条独立指令。

## 成功判据

版本：`press-lift-stapler-v1-native-press-contact`。两个 modes 的预算都是 **250 次 policy action**。

- **Press**：夹爪已闭合至少 0.08 秒，向下接近至少 5 mm，在原生 contact point 2 附近的 ±3 cm 窗口内接触；目标仍由桌面支撑，抬升不超过 1.5 cm、横向位移不超过 3 cm。接触满足条件即完成，不要求撤离。
- **Lift**：目标相对初始高度抬升至少 3 cm，与闭合夹爪接触，并连续至少 0.1 秒离开桌面。
- **动作顺序**：第一个完成的动作锁定分类。完成另一个动作后，再执行指令要求的动作不能修正本回合结果。
- **采样**：每个实际物理步读取接触与状态，当前 timestep 为 4 ms，保留零冲量接触点。

原生 `press_stapler` 使用静态目标和接触即成功条件；当前任务使用动态目标，并增加动作区分条件。
`native_press_success` 仅作为原生接触条件的诊断，最终成绩使用上述任务判据。
实现见 [`press_lift_stapler.py`](../tasks/envs/press_lift_stapler.py) 和 [`StaplerMonitor`](../tasks/envs/_press_lift_stapler.py)。

## 正式模型结果

| Policy | Press | Lift | 同场景双成功 |
|---|---:|---:|---:|
| X-VLA | 9/20 | 15/20 | 7/20 |
| LingBot-VA | 18/20 | 0/20 | 0/20 |
| LingBot-VLA | 18/20 | 1/20 | 1/20 |
| VLAct All | 20/20 | 16/20 | 16/20 |
| DM05 | 20/20 | 12/20 | 12/20 |
| Hy-VLA | 17/20 | 18/20 | 17/20 |

这些成绩来自随机朝向、固定 seeds 的正式清单。Stapler 共 240 回合。
模型成功、policy failure 和初始场景校验均按正式流程保留。

[当前视频示例](assets/demos/press_lift_stapler.mp4) ·
[逐回合诊断](../result/episodes.csv) ·
[完整六任务结果](../result/README.md) ·
[新评测入口](branch-delivery.md)
