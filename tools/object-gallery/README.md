# RoboTwin Object Gallery

一个纯前端、免构建的可视化 web app，把 RoboTwin 数据集里 `assets/objects/` 下的所有物体列成一个可交互的 3D 画廊：网格缩略图实时渲染，点开可旋转/缩放、切换同一物体的不同实例。

当前覆盖 **148 个物体条目 / 735 个实例**，三种网格格式：

| type | 来源 | 加载器 | 数量 |
|------|------|--------|------|
| `glb`  | 编号物体 `NNN_name/visual/base*.glb`、`vis_box` | `GLTFLoader` | 119 |
| `obj`  | `objaverse/<类别>/<实例>/textured.obj`(+独立 `.obj.mtl`+贴图)、`cube` | `OBJLoader` + `MTLLoader` | 27 |
| `urdf` | PartNet-mobility 铰接物体 `NNN_name/<id>/mobility.urdf` | `urdf-loader`(内部走 `OBJLoader`) | 2 |

> 只有 `points_info.json`、没有可渲染网格的目录（如 `sapien-block1/2`）会被自动跳过。

---

## 快速开始

```bash
just gallery          # 默认 8891 端口；just gallery 8080 换端口
```

这条 recipe 会：先跑 `gen_manifest.py` 扫描生成 `manifest.json`，再**从 repo 根**起 `python -m http.server`。然后打开：

```
http://localhost:8891/tools/object-gallery/
```

手动等价命令（不想用 just）：

```bash
python tools/object-gallery/gen_manifest.py
python -m http.server 8891          # 必须在 repo 根目录跑
```

### 远程机（SSH Remote）注意端口转发

服务默认监听 `0.0.0.0`，本机 curl 能通，但如果你的 VSCode 是 **Remote-SSH** 连的远程机，本地浏览器的 `localhost:8891` 需要经 SSH 隧道转发才能访问，否则会 `ERR_CONNECTION_REFUSED`。

- 在**自己的集成终端**里跑 `just gallery`，VSCode 通常会自动探测到新监听端口并弹「端口已转发」提示；
- 或手动转发：底部 **PORTS** 面板 → *Forward a Port* → 填 `8891`。

---

## 为什么必须从 repo 根起服务？

浏览器要直接 `fetch` 本地的 `.glb/.obj/.urdf` 文件。`manifest.json` 里的 `objectsRoot` 是一个 **服务器绝对路径**：

```
/third_party/robotwin/assets/objects
```

它假设 http server 的根就是 repo 根，这样 app（`/tools/object-gallery/`）和模型（`/third_party/...`）都在同一个 origin 下可达。换个目录起服务，路径就对不上了。

（这也是为什么它不是一个 claude.ai Artifact——Artifact 的 CSP 读不了本地模型文件。）

---

## 界面功能

**网格页**
- 顶部搜索框（按物体名 / id 过滤）+ 分组 chips：`all / numbered / objaverse / misc`
- 每张卡片显示：实时 3D 缩略图（缓慢自转）、名字、类型徽章、`id · N instances`
- 深链参数：`?q=bottle`、`?group=objaverse`（可组合），过滤时地址栏会同步更新，方便分享

**详情弹窗**（点卡片打开，`Esc` 关闭）
- `OrbitControls`：拖拽旋转、滚轮缩放
- `instances`：一排按钮切换同一物体的不同网格实例
- 开关：`auto-rotate` / `wireframe` / `ground grid`

---

## 架构 & 关键实现点

```
tools/object-gallery/
├── gen_manifest.py   扫描 assets/objects → 分类 → 写 manifest.json
├── manifest.json     生成物（assets 变了要重跑生成器）
├── index.html        importmap（three + addons + urdf-loader 走 unpkg CDN）
├── app.js            画廊逻辑
└── style.css
```

- **单渲染器 + scissor 网格**：120+ 个卡片不可能各开一个 WebGLRenderer（浏览器 WebGL context 上限 ~16，超了会丢上下文）。这里用**一个**共享 renderer，铺一张 `position:fixed` 的全屏 canvas 垫在卡片下面；每帧遍历屏幕内的卡片，用 `setScissor/setViewport` 把各自的 scene 画到卡片位置。卡片本身背景透明，露出后面的 canvas。
- **懒加载**：`IntersectionObserver`（含 300px 预加载边距）+ 并发上限 6，卡片进视口才拉模型。
- **三类加载器分派**见 `loadModel()`；每个物体默认只加载第 0 个实例做缩略图，详情页按需加载其它实例。
- **朝向 / 尺寸归一化** `fit()`：把物体包围盒中心移到原点、按最大边缩放到单位大小，再据包围球半径摆相机取景。URDF（PartNet 是 Z-up）额外绕 X 转 -90° 到 Y-up。
- **URDF 的坑**：`urdf-loader` 的 `load()` 回调在**异步网格加载完成前**就触发，此时机器人没有几何体、包围盒为空 → 取景半径≈0 → 相机落进模型内部（表现为一整片灰面）。解决办法是等 `LoadingManager.onLoad`（所有 mesh 子请求排空）后再 `fit()`。

---

## 常见操作

**assets 增删了物体 → 重新生成 manifest**
```bash
python tools/object-gallery/gen_manifest.py
```
（`just gallery` 每次启动都会自动重跑，无需手动。）

**新增一种物体格式** → 在 `gen_manifest.py` 的分类逻辑里加一支，并在 `app.js::loadModel()` 里加对应加载器。

---

## 已知限制

- **URDF 是静态 pose**：只按初始关节角渲染，不做关节交互动画。
- **依赖联网**：three.js / urdf-loader 走 unpkg CDN（模型文件是本地的）。想离线可把这几个库 vendored 到本地再改 importmap。
- **软件渲染下较慢**：无 GPU 的 headless 环境里缩略图会转圈久一点；正常有 GPU 的浏览器很快。
