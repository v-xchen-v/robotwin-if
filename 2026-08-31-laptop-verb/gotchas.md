# IF-Verb-Select — gotchas（实现层已知风险）

> 与 [understanding.md](understanding.md) 的"待确认"分工：那边是"没问过用户、靠假设实现的点(理解是否对齐)"；这里是"**即使理解完全对齐,实现本身仍有的已知隐患**"。实现见 commit `56f1149`（+ 清理 `145e9e0`）。

## 正确性 / 边界隐患

### G1.（最尖锐）`use_seed=True` 在全新进程会崩
成对门控依赖"**phase-1 先在同一进程跑过、把 `_pair_ok` 填好**"。如果用 `use_seed=True` 直接跳过 phase-1（例如复用别人给的 seed.txt、或断点续采），`laptop_verb._pair_ok` 是空的 → phase-2 的 `check_success` 会触发伙伴试跑，而此时 `need_plan=False`（来自 `_demo_kwargs`）→ 伙伴 `play_once` 没有可回放的规划路径 → `_raw_success` False → phase-2 结尾的 `assert check_success()` 抛 "Collect Error"。
- **触发**：`collect_data` 配 `use_seed: true`，或任何"不先跑 phase-1 就调门控 check_success"的路径。
- **检测/规避**：只用默认 `use_seed: false` 全流程跑；若要 resume，需先想清楚缓存怎么预热。目前**未处理**。

### G2. 门控依赖"伙伴试跑与真实跑同种子结果一致"——GPU 非确定性可致孤儿
门控逻辑：伙伴试跑 seed `2k+1` 通过 → 缓存该场景可配对 → 于是 open(`2k`) 存盘。随后真实跑 close(`2k+1`)。二者是**同一个 seed、确定性 setup**，正常应同结果。但如果 sapien/curobo 在 GPU 上有**运行间非确定性**（浮点/并行序），伙伴那次 close 过、真实这次 close 偏偏 fail → open 已存、close 没存 → **留下一个孤儿 open**。
- **触发**：底层仿真非确定性 + 恰好卡在判定边界的 close（合盖稳定停在 12–15%，离 20% 线不算远，正是易受扰动的区间）。
- **检测**：采集后按 `seed//2` 分组校验每个 scene 是否开/关都在；发现落单即命中。目前**未加这个采后校验**。

### G3. `_pair_ok` 缓存永不失效、只按 `scene_seed` 建键
类级 `_pair_ok` 整个进程存活、无失效，key 只有 `scene_seed`（一个 int），**不含 config / 变体子集 / 阈值**。同一进程内 `scene_seed→场景` 确定,所以现在没问题;但只要将来"同进程内换 config/换子集再跑",旧缓存会返回错误配对判断。是个埋着的脚枪。
- **规避**：一个进程只跑一种配置(现状如此)。若要复用进程,需按 config 纳入 key 或每次清缓存。

### G4. `play_once` 里 `except AssertionError` 过宽
开/关 servo 循环用 `try/except AssertionError` 兜"抓取位姿规划不出(target_pose None)"的崩溃。但它**吞掉任意 AssertionError**,不止那一种。若运动中别处触发断言,会被当成"优雅停止"静默吞掉,表现为该方向 `_raw_success` False 而无报错。
- **规避**:理想应收窄到具体异常/消息;目前**未收窄**。

### G5. 奇数 `episode_num` 会向上取整到整对（良性）
门控使每个 scene 恰好贡献 0 或 2 条(open/close 同生同灭),`suc_num` 永远偶数。所以 `episode_num` 设奇数时,循环会多采一条凑成整对(如设 5 实采 6)。**不会产生孤儿**,但 episode_num 不被精确兑现。
- **规避**:采集 episode_num 用偶数。

## 并发 / 性能

### G6. 同进程双 `sapien.Engine`(门控伙伴试跑)——规模/硬件脆弱面
每遇到一个新 `scene_seed`,门控会新建一个临时 `laptop_verb` 实例做伙伴试跑,与主 env 的 engine/scene **并存**。本机 6 条 + 20 条各验一次不崩,但这是已知脆弱面:显存、renderer 状态、curobo/CUDA context 都可能在**更小的 GPU / 更大规模 / 不同 sapien 版本**下出问题。
- **检测**:大批量或换机跑时盯 CUDA error / segfault / 显存增长。

### G7. 每个场景 ~2–3× 开销 + 潜在显存增长
`check_success` 对每个新场景多跑一次完整 setup+play(伙伴)。N 对 ≈ (对数+丢弃数)×(2 真实 + 1 伙伴) 次 `play_once`。是吞吐税,非正确性问题。伙伴 env 虽在 `finally` 里 `close_env()`,但**大批量下 engine 是否及时释放显存未在规模上验证**,长采集有 OOM 风险。

## 技术债

### G8. `check_success` 被重载成重副作用谓词(主债)
它从"读一个关节角"变成"可能新建 env、跑一整套 setup+play、并存第二个 engine"。**违反最小惊讶**:任何未来读者/调用者若以为它廉价纯粹就会踩坑——事实上 Layer-B 测试正是因此**被迫改调 `_raw_success`** 而非 `check_success`。这是 [decisions.md](decisions.md) D6 里用户知情接受的债,记在此以便日后偿还(理想是把门控挪回采集层/外部采集器,让谓词回归纯粹)。

### G9. 子集 / 阈值 / 动词池全硬编码
`ALLOWED_MODEL_IDS=[1,9]`、`OPEN_TARGET/CLOSE_TARGET`、`OPEN_VERBS/CLOSE_VERBS` 都写死在类里。单任务够用,但第二个"同场景动词切换"任务只能复制粘贴 + 改常量,没有抽出可复用基类(当前**刻意不抽**,避免过早抽象——见 decisions.md;但若真出现第 2 个,这是该还的债)。

### G10. 伙伴试跑扰动全局 `np.random`(当前良性)
伙伴 `setup_demo` 会 `np.random.seed(partner//2)`,把全局 RNG 状态改成伙伴场景的。当前良性——每个 `setup_demo` 开头都重播种,下一条不受影响。但这是一层**隐性耦合**:若将来有代码依赖"全局 RNG 流跨 episode 连续",会被打断。

---
**下一步**:跑 `just vibe-notes-push`,把 `gotchas.md`(连同 understanding.md / decisions.md)推到 `notes/` 独立仓库。
