# Operate-Stapler check_success 反例测试计划（Layer B 反例）

> 目的：证明 `check_success` **有区分度**——不只"做对→True"，还要"做错→False"。正例（oracle 正确操作→success，见 `operate_stapler-impl-verify.md`）证明不了这一点：一个恒 True 的判定也能通过所有正例，却让基准失去意义。IF 基准的效力**完全取决于**判定的紧度。
>
> 脚本：`tools/test_operate_stapler_check.py`（在 GPU 机器、RoboTwin conda 环境跑）。

## 可构造性（决定怎么测）

看 `check_success` 两分支（`tasks/envs/operate_stapler.py:226-245`）：

- **move 分支 = pose-based**：判 `stapler.pose ≈ pad.pose` + 姿态对齐 + 双爪张开。→ **可用 `set_pose` 直接伪造末态**，无需跑完整轨迹。可精确构造正例/反例。
- **press 分支 = contact-based**：判 `get_gripper_actor_contact_position` 里夹爪-订书机在按压点 cp2 的**物理接触**。→ **伪造不了接触**（set_pose 不产生 contact），正例必须真跑专家；反例可用"无接触默认态"廉价断言。

## 测试矩阵

| # | mode | 构造方式 | 期望 | 证明什么 |
|---|---|---|---|---|
| **T1** | move | `set_pose` 把**订书机**放到 pad 位姿（对齐四元数 `[.5,.5,.5,.5]`），双爪张开 | **True** | 位姿/姿态/夹爪三条件满足时判定能 True（正控） |
| **T2** ★ | move | `set_pose` 把**干扰物**放到 pad，订书机留原位 | **False** | 判定认的是"**订书机**到垫子"，不是"任意物体到垫子"——design.md 点名的最易漏坑 |
| **T3** | move | setup 后默认态（订书机离 pad >0.1） | **False** | 没放到位就不算成功 |
| **T4** | move | 订书机放到 pad 但**闭合一只夹爪** | **False** | "松手"是成功必要条件（防抓着不放蒙混） |
| **T5** | press | setup 后默认态（无夹爪-订书机接触） | **False** | 没按压就不算成功 |
| **T6** | press | 真跑 `play_once` 专家（产生 cp2 接触） | **True** | 接触判定能 True（正控，contact-based 只能这样构造） |

★ **T2 是核心**：move 正例(T1)+错物体反例(T2) 的对比，直接证明判定**对象特异**——这是共享场景 IF 基准立得住的前提。

## 机制说明

- 复用 `collect_data.main` 的 args 构造：import 后把 `cd.run` 换成拦截函数，`main("operate_stapler","demo_clean")` build 好 `task`+`args` 就被截住（不跑采集循环），零 copy-paste 漂移。
- 每个 case 前 `task.setup_demo(seed=SEED, **args)` 重建场景；**seed 偶→press、奇→move**（`seed%2`）。
- move 反例/正例用 `actor.set_pose()` 构造末态后**立即** `check_success()`（不 step，读的就是设定位姿）。
- press 正例(T6)调 `play_once()` 真跑专家（需运动规划，较慢）。

## 怎么跑

```bash
cd /home/xichen6/Documents/repos/robotwin-if
conda activate RoboTwin      # 或对应环境
python tools/test_operate_stapler_check.py
```

脚本对每个 case 打印 `实际 vs 期望` 和 PASS/FAIL，末尾汇总；有 FAIL 则退出码非 0，可纳入回归。

## 解读

- **全 PASS**：判定对两 mode 都有区分度，尤其 T2 证明了对象特异性 → 基准判定可信。
- **T2 若 False 期望但实际 True**（即干扰物上垫子也判成功）：说明判定太松、只看位置不看对象 → **基准失效，必须收紧**（改成校验是 `self.stapler` 到位）。当前代码看 `self.stapler.pose` 应该 OK，但必须实测坐实。

## 边界（这个脚本不覆盖）

- press 的"假阳"细案（抓侧面而非按顶部是否误判 True）——contact-based 难静态构造，需专门设计错误抓取轨迹，暂缺。
- 跨 mode 误触（强制 `mode` 与动作错配）——可加，暂未纳入。
