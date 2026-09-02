# IF-Attribute-Select — task design 讨论（实现前，设计已收敛）

> status: 讨论中 / 设计已收敛、未开始实现。这不是实现记录，是"形容词/视觉特征轴往哪个方向落地"的选型讨论 + 决策链。
> 母设计：[docs/features/09-IF-Ext-六轴扩展任务设计.md](../../docs/features/09-IF-Ext-六轴扩展任务设计.md) §3（已按本讨论结论改写）。
> 相关：[[verify-asset-colors-by-texture]]、[[if-tasks-need-in-repertoire-behaviors]]、[[ifext-eval-test-only]]、[[reuse-native-instruction-pools]]；同帧对照机制来自上一批 [../2026-08-31-laptop-verb/design-review.md](../2026-08-31-laptop-verb/design-review.md)、[../2026-09-01-sequence-container/design-discussion.md](../2026-09-01-sequence-container/design-discussion.md)。

## 1. 出发点

母文档 §3 原设计 = **IF-Attribute-Ladder（形容词优先级阶梯 color > texture > shape > 大小）**：用**累积档**干扰物验证 policy 是否"只在必要时才升级到更细的修饰词"——Tier1 只颜色可分、Tier2 需颜色+纹理、Tier3 需颜色+纹理+形状。诊断"按需升级"这一行为，靠 Tier drop 读退化。资产走**多物体抓取池**（`base{N}` 变体），是 6/7 个任务里可信度最低、风险最高的一个。

本讨论把它整个翻掉，落到 **primitive 版四特征 mode**。四个转折依次记录。

## 2. 四个设计转折（本轮决策链）

### 2a. 累积阶梯 → 按属性型分独立 mode

**问题**：累积档升 Tier 时「属性种类」和「累积个数」**同时**在动 → Tier3 失败分不清是 shape 挂了还是"累积到三个属性"挂了。这违背 IF-Ext 的**单轴隔离**立身之本。

**改法**：按**属性型**拆成独立 mode，每 mode 只动一种属性。关键洞见——**「优先级退化」照样从 per-mode 成功率读得出**（color 高 / 其它低 = policy 靠颜色、无视细属性），而且**没有累积个数的交叉污染**，比阶梯读得更干净。阶梯唯一多测的「过度指定」（颜色够了却用更细修饰）在 pick 任务里不致失败、不体现在成功率 → 诊断价值薄，舍弃。

> 一句话：阶梯的 Tier-drop 和 per-mode 成功率测的是同一个退化，但 per-mode 隔离掉了 count 的混淆 → 分 mode 在有效性上压过阶梯。

### 2b. 物体池 → primitive（cube/球/柱）

**触发**：用户提议直接用 cube / 简单几何体，不用物体池。

**为什么是强 win**：`create_box`/`create_sphere`/`create_cylinder`（[third_party/robotwin/envs/utils/create_actor.py](../../third_party/robotwin/envs/utils/create_actor.py)）直接生成，属性由参数写死。一刀**同时**消掉旧设计三大风险 + 一个依赖：

1. **池盘点**（~120 物体凑"只差一属性"的干扰组）→ 没了，属性你 set。
2. **属性标注 noisy**（[[verify-asset-colors-by-texture]]，描述里颜色词不可信、绑 `base{N}`）→ 没了，不用反推。
3. **per-object 抓取参数** → 没了，box/sphere 抓取 §4/§7 已验证、`create_box` 自带 contact_points。
4. **pick_diverse_object 池 infra 依赖**（断链 symlink，本是"延后"的横切阻塞）→ 没了 → §3 **自包含**、与 §4 Arm-Select / §7 Grasp-Approach 同级共用 create_box 脚手架。

**代价（诚实）**：裸几何比池里真实物体**更合成**，是"干净下界"而非自然场景。但对**单轴隔离诊断**，除被测属性外逐字节相同恰是优点，也契合 IF-Ext 独立组允许自定义资产。若日后要生态效度，可加池物体变体作第二 condition——非首选。

### 2c. 抽象 texture → decal（贴图）

**触发**：用户问能否网上下载猫/狗图贴 cube 上、按图构造指令。

**先厘清一个岔路**（重要）：猫/狗贴图测的**不是** texture（表面材质），是**表面图像语义**。两者不同——"条纹/木纹"是材质属性、"印着猫"是贴在表面的图像内容，既非颜色也非材质、**也不是严格意义的形容词**。用户知情后仍选"用贴图替换 texture 档"（而非另立任务）。

**为什么这么换是对的**：抽象材质纹理的老风险是 (c) **同色不同材质相机分不分得清**——这是原 §3 最高风险。换成 decal 后：
- **视觉可分免费**：猫 vs 狗在相机分辨率下一眼可分 + VLA 有强语义先验。
- **易构造**：下载/生成一张 PNG 即可。
- **机制现成**：`create_box(texture_id=...)` 把图当 `baseColorTexture` 贴上（sphere 同款 `RenderTexture2D`→`set_base_color_texture`，wall/table 随机化在用）。

→ 中间档从"7 任务最高风险"退成低风险。**诚实定位写进母文档**：decal 是视觉特征之一、取它"可分免费 + 易构造"，但标清它不是材质纹理、不是形容词。

### 2d. size 预留 → 正式第四 mode

先设计成"列表化 + 双分派、size 作 drop-in 预留"，再决定**直接收进来**（effort 极低）。四档 **color / decal / shape / size** 正好收齐原"color > texture > shape > size"四类（decal 顶替 texture 档）。

**size 是最省事的 mode**：同一 cube 缩放大/小两实例、零素材、抓取沿用 box。因四 mode 一起上，`k=4` 从头固定，**不存在**"k 从 3→4 重映射 seed"的跨版本问题（那是分步上才有的坑）。

## 3. 最终设计（收敛版，已写入母文档 §3）

- **测试目标**：隔离单一视觉特征——物体其余特征固定，只有一种是区分量，测 policy 能否真正用上该特征 grounding。分 mode 统计成功率，某 mode 骤降 = 用不上那类特征。
- **单 env·mode 结构**（复用 laptop_verb）：`MODES=["color","decal","shape","size"]`、`k=4`；`scene_seed=seed//4` 定场景、`mode=seed%4` 定特征轴 → **同场景、只变特征轴**结构性保证（相邻种子组同帧、仅指令特征不同）。
- **分派式**：成功判定 `check_attr_match(picked,target,ATTRS[mode])`（color 比 baseColor / decal 比 texture 标签 / shape 比几何类型 / size 比 scale·bbox 体积）；干扰物构造各 mode 一个 primitive builder。指令统一 `{ADJ}` 槽、跨 mode 占位符集合一致 → 框架标准路由直接通（不 hack）。
- **反例（Layer B）**：oracle 抓"本 mode 特征不匹配、其余都对"的干扰 primitive → 必判失败；每 mode 分别测。
- **指令示例**：color「拿起红色的方块」；decal「拿起有猫的方块」；shape「拿起球」；size「拿起大的方块」。
- **可信度**：中偏高（从原"最高风险"降下来）。

## 4. 诚实标注 / 已知皱褶

- **decal ≠ 形容词**：见 2c，是表面图像语义，作中间档取其可分性红利，定位已标清。
- **shape mode 的名词贴边**：primitive 的"方块 vs 球"里，形状词近似物体名词，和 §2 Noun 有一点语义重叠。但 §2 是**跨类别真实物体**、这里是**同色同尺寸的几何体**，仍算 shape 特征。若要更"纯形状"可再议。
- **size 可分性最弱**：连续量、依赖相机；需大/小 scale 比够大（1.5–2×）才分得清，是四档里最弱的一档。且大 cube 别超夹爪开度、小 cube 别扁到抓不住——两档都卡在可抓区间。
- **in-repertoire 检查通过**：四 mode 全是纯 pick、动作在库内，不会像 close-laptop 那样塌成 action-OOD（[[if-tasks-need-in-repertoire-behaviors]]）；decal 的强先验反而是优点。按 [[ifext-eval-test-only]]（ifext 无 finetune 数据、只 zeroshot/native-ft），本任务用方向性/分 mode 指标即可，无 OOD 归因问题。

## 5. 与 §2 Noun-Grounding 的界限（互补独立）

- §2 = 纯名词、**跨类别**真实物体（杯/瓶/盒），抓对类别即成功，用物体池 infra。
- §3 = 同一物体上的**单一视觉特征**，用 primitive，**infra 不再共用**。
- §2 提供"无特征、纯类别 grounding"的对照读数；§3 在其上换成按特征区分。decal 与 §2 划界：§2 跨类别、decal 是同一 cube 只换贴图（物体身份中性）。

## 6. 待验 / 下一步（均小、可控）

- [x] ~~**decal UV 映射**：每面完整图 vs 平铺~~ → **已验，见 §7**：box 面 UV 只采样偏心半窗（都不是），改用 UV-correct quad mesh 解决。
- [ ] **图像授权**：decal 用 CC0 / 生成图，别扒版权图；选无歧义图案对（猫/狗/…）。当前 spike 用**程序画的**猫/狗图标占位，真实图后续换。
- [ ] **size scale 比 / 可抓区间**：定大/小两档尺寸，确认相机可分 + 都可抓。
- [ ] **实现骨架**：单 env + `check_attr_match` 四分派 + 四 primitive builder + `{ADJ}` 指令池；Layer A（路由）/ Layer B（四 mode 反例）对齐 laptop_verb / stack_sequence 的 footprint。
- 排期：母文档已把本任务从"延后 / 池阻塞 / 最高风险"上调为**自包含 / 低风险 / 可提前**（估 1.5–2d）。

## 7. Spike 结论（2026-09-01，渲染/可行性阶段②，全绿）

> 目标：证 §3 四 mode 在渲染层可行、可区分。抓取本身复用 §4/§7 已证的 box/sphere 抓取，未在此重跑。脚本 `tests/attribute_select/spike_decal_render.py`（初版四物体渲染）、`tests/attribute_select/spike_decal_top.py`（decal 顶面定稿）；证据图在 `evidence/`。环境 `conda run -n RoboTwin`（sapien 3.0.0b1，2×A6000）。

### 7a. color / shape / size —— PASS（sanity）
`spike_shape_size.png`：cube / sphere / cylinder 一眼可分（shape）；大 cube（half 0.07）vs 小 cube（half 0.03，~2.3×）明显可分（size）；红/蓝纯色 box 干净（color）。三档渲染无悬念。

### 7b. decal —— 真正的未知，验证 + 踩坑 + 定稿
- **踩坑：box 面 UV 不是 [0,1]**。`create_box(texture_id=...)` 把整张图当 baseColorTexture，但 `RenderShapeBox` 的**面 UV 只采样贴图一个偏心的、约半尺寸的子窗**（标定图 `spike_uv_cal.png`：满幅边框 + 四角色块 + 中心点 → 面上只见中心点被推到右缘、四角/边框全丢）。后果：单张居中头像被**裁切**；先用 3×3 平铺绕过（`spike_decal_top.png` 早期版），但平铺会**露出两个头**、看着不对。
- **定稿：顶面用 UV-correct quad mesh**。放弃 box 面 UV，改成 `add_visual_from_file` 贴一张**显式 [0,1] UV 的 quad.obj + mtl 贴图** → 整图精确铺一次、居中不重复。`vt` 的 v 轴要翻转否则上下颠倒。
- **top-face-only + 单刚体**：一个 actor = 灰蓝 cube 本体（box collision+visual）+ 顶面 quad 贴片（本体色与贴片解耦，贴片只在顶面）→ 整体可抓，正是生产配方。
- **猫/狗可辨**：程序画（无联网/无版权）——猫=橙、**尖三角耳**；狗=棕、**两侧垂耳**+浅口鼻。轮廓（尖 vs 垂）+ 颜色双重可分，最终 `spike_decal_top.png` 单头居中、方向正、cube 蓝灰不撞白背景。

### 7c. 生产配方（decal mode 直接用）——**纯内存、零文件为首选**

资产管理决策（讨论后定）：**decal 走程序生成 + 纯内存构造，不落任何磁盘资产**。动机是 [howto-decal-on-cube.md](howto-decal-on-cube.md) §5.5 的抗嵌套考量——若 robotwin-if 被别的 repo 当 submodule，文件路径解析（CWD 相对 / symlink 被拷成实体 / `realpath(__file__)` 反解）都有失效面；**内存版没有任何路径 → 全免疫**，env 也退回纯代码、自包含（和 laptop_verb/arm_select 一样，`bridge_tasks.sh` 无需新增 assets 注入点）。

SAPIEN 两个类都有"吃 numpy 数组"的重载，是这条路的关键：
```
ent = Entity():
  PhysxRigidDynamicComponent + PhysxCollisionShapeBox(half)     # 碰撞（抓取用）
  RenderBodyComponent:
    RenderShapeBox(half, 灰蓝本体色)                             # 四 cube 同色，不构成 color 混淆
    RenderShapeTriangleMesh(verts, tris, normals, uvs, mat)     # 顶面 decal：quad 来自数组、UV 写死[0,1]（v 翻转正立）
      mat.set_base_color_texture(RenderTexture2D(rgba_arr, "R8G8B8A8Unorm", srgb=True))  # 纹理来自数组
      mesh.set_local_pose([0,0,half+0.002])                     # 抬到顶面
```
- **抓取元数据**：手动 entity 没有 `create_box` 的 contact_points → 真 env 里改成**用 `create_box` 建本体（拿 Actor+抓取点），再把 decal mesh attach 到它的 RenderBodyComponent**。
- **上真实照片仍零文件**：照片 base64 内嵌 .py（或 `.npy`）解码成数组，走同一条内存路径；授权在模块里记一行。
- **备选（讲原理用）**：文件版 = quad.obj+mtl+png + `add_visual_from_file`（`spike_decal_top.py`），直观但引入路径解析，不作首选。

### 7d. 证据
- `evidence/spike_shape_size.png` —— shape+size 四 primitive。
- `evidence/spike_decal_color.png` —— 初版 box 面贴图（暴露 UV 半窗裁切）+ 纯色 box。
- `evidence/spike_uv_cal.png` —— UV 窗口标定（证半窗偏心）。
- `evidence/spike_decal_top.png` —— 文件版定稿：顶面单头猫/狗、quad mesh。
- `evidence/spike_inmem.png` —— **纯内存版定稿（首选配方）**：猫+狗，全程零文件。
- 脚本：`tests/attribute_select/{spike_decal_render,spike_decal_top,spike_decal_inmem}.py`。

### 7e. 仍未做（进阶段③前）
- 抓取 oracle 未在本 env 实跑（借 §4/§7 结论）；env 接线后补一个 4-mode 抓取成功率 spike。
- decal mode 用 `create_box` 本体 + attach decal mesh 的整合（保留抓取点）；size 两档尺寸最终值；shape/color/size 的干扰物 builder。
- 阶段③：seed→mode→instruction→check 四者同源（`MODES=[color,decal,shape,size]`、`k=4`）。
- 资产管理已定（7c：纯内存、零文件），**无 bridge/submodule 改动**。

## 8. 阶段③ 接线（2026-09-01）+ 一个关键 IF-correctness bug

### 8a. env 落地
`tasks/envs/attribute_select.py`：4 轴一个 env，`create_box` 建 color/shape/size 物体，decal 走**手工建刚体**（纯内存 texture+quad mesh，见 §7c；不能用 create_box 事后 attach——"adding shape to render body that is already part of an entity is not implemented"，故 build 前 attach 再 `scene.add_entity`，并手配默认 box top-down 抓取点让 grasp_actor 照常工作）。

seed 结构（细化母文档，见下 8b）：`axis = MODES[(seed//2)%4]`、`value = seed%2`、`scene_seed = seed//2`。wiring spike `tests/attribute_select/spike_wiring.py` N 局×4轴×正例/Layer-B：**四轴正例 100% / Layer-B（抓 distractor）0%**。shape 轴的 bar 一开始因长边 0.11m 超夹爪开度偶发抓不住，改到 `BAR_HALF=(0.04,0.02,0.03)`（长边 0.08 ≤ 夹爪跨度）后 100%。

### 8b. ⚠ 关键 bug：对比对不是"同场景"（用户 2026-09-01 抓到）

**症状**：color 轴里，`(2k,2k+1)` 两局的场景不一样——红/蓝盒位置互换了。

**根因**：初版 `load_actors` 把 **target 放在一个 value-无关的固定 slot**（由 `scene_seed` 的 `slot_flip` 定、pair 内不变）。于是：
1. `value` 翻转时，被命名的颜色跟着 target 换了位置 → 场景不再相同；
2. **更致命**：target **永远在同一个 slot** → policy 只要"抓固定位置那个"就 100% 正确，**根本不用读指令/看属性** → IF 诊断被完全击穿（假阳性上天花板）。

**修复**：`scene_seed` 固定的应是**特征值→slot 的映射**（`v0@SLOTS[flip]`、`v1@SLOTS[1-flip]`），pair 内**像素级同场景**；只让 `value` 决定**命名哪个值当 target**（target 的位置随之变，但场景不变）。这样位置不再和答案相关，policy 只能靠读指令赢。

**验证**：`evidence/ep_0_color0_ok.png`（target=red）与 `ep_1_color1_ok.png`（target=blue）初始帧**完全相同**（蓝左红右），只有抓走的 cube 不同。修复对 4 轴同时生效（共用 `load_actors`）。

### 8c. 教训（可推广到所有单轴 IF 任务）
**IF 对比对必须像素级同场景；任何与答案相关的位置/几何都是泄露。** 单轴隔离不只是"只变一个属性"，还要求"**除被命名的目标外，一切**（含物体摆位）在对比对内不变"——否则 policy 能走位置/几何捷径拿假阳性。落地防线：Layer A 里加**同场景结构断言**（断言 `(2k,2k+1)` 两局物体位姿集合相同、仅 target 标签翻），像 laptop_verb/stack_sequence 的"种子对同场景零违例"。→ 已排进阶段③ Layer A（§7e 之后）。

### 8d. 视频/采集
补了 per-task config `task_config/attribute_select.yml`（mirror stack_sequence，`episode_num=4`）。`collect_data.py attribute_select attribute_select` **能跑通并出 head/wrist mp4**（`data/.../video/episodeN.mp4`）；末尾 `gen_episode_instructions.sh` 因指令池未写而报 FileNotFound——**预期**，视频在该步之前已生成。注意：首批视频是 8b **修复前**采的（场景会互换），已过时，收尾后重采。
