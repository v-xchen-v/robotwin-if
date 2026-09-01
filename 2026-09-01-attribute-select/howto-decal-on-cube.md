# How-To：在 SAPIEN/RoboTwin 里给 cube 顶面贴一张图（decal）

> status: 学习笔记 / 可复用技法。从 IF-Attribute-Select 的 decal 档 spike 里抽出来，自包含。
> 配套代码：`tests/attribute_select/spike_decal_top.py`（已跑通，sapien 3.0.0b1）。
> 证据图：`evidence/spike_decal_top.png`（定稿）、`evidence/spike_uv_cal.png`（UV 标定）。
> 母设计：[design-discussion.md](design-discussion.md) §7。

## 0. 一句话

**不是"把图贴到 cube 上"，而是"单独做一张带贴图的薄面片（quad mesh），盖在 cube 顶面，和 cube 焊成一个刚体"。** 核心难点是 **UV 不可控**，核心解法是 **自己写一张 UV=[0,1] 的 quad**。

数据流：
```
PIL 画的 PNG  →  带 UV 的 quad 小方片(mtl 指向 PNG)  →  add_visual_from_file 挂到 cube 本体  →  build 成一个刚体
```

## 1. 先补三个概念（看懂后面全靠这三个）

- **贴图 / 纹理（texture）**：一张 2D 图片，"糊"到 3D 物体表面当颜色。在 SAPIEN 里是 `RenderMaterial.set_base_color_texture(RenderTexture2D(png))`，或经 `.mtl` 的 `map_Kd`。
- **UV**：物体表面每个点对应贴图上的哪个坐标，范围约定成 [0,1]×[0,1]。`(0,0)`=贴图一角、`(1,1)`=对角。**UV 决定图怎么摆**——铺满一次？平铺重复？裁一半？全看 UV。这就是本文的胜负手。
- **primitive vs mesh**：`create_box`/`create_sphere` 是**内置几何体**，UV 是引擎写死的、你改不了；**mesh**（.obj/.glb）是**自定义几何 + 自定义 UV**，你能一个顶点一个顶点地控制。

## 2. 为什么不能直接 `create_box(texture_id=...)`（踩坑 + 调试技巧）

RoboTwin 的 `create_box` 支持 `texture_id`，底层给 `RenderShapeBox` 挂了带贴图的材质。**但内置 box 的面 UV 不是干净的 [0,1]**——它只采样贴图的一个**偏心、约半尺寸的子窗**，于是单张居中的图会被裁掉大半。

**怎么确诊 UV 行为（通用技巧）**：画一张"标定纹理"贴上去看。
- 满幅**边框** + **四角各一个色块**（红/绿/蓝/橙）+ **正中一个黑点**。
- 贴到面上渲染：如果看到完整边框和四角 → UV 是 [0,1]；如果四角/边框全丢、中心点被推到边缘 → UV 是偏心子窗（我们的情况，见 `spike_uv_cal.png`）。

这一步省掉了瞎猜——**UV 迷惑时，先贴标定图量一遍**。

## 3. 正解：自己写一张 quad mesh（UV 写死 [0,1]）

既然内置 box 面 UV 不听话，就绕开它：造一张**面片 mesh**，UV 手写死。两个纯文本文件：

**`quad.obj`**（XY 平面的单位方片）：
```obj
mtllib cat.mtl        # 用哪个材质文件
v -0.5 -0.5 0         # 4 个角顶点（z=0 的正方形）
v  0.5 -0.5 0
v  0.5  0.5 0
v -0.5  0.5 0
vt 0 0                # ← UV：4 个顶点各对应贴图的哪个坐标
vt 1 0                #   (0,0)(1,0)(1,1)(0,1) = 整张图精确铺一次
vt 1 1
vt 0 1
vn 0 0 1              # 法线朝上 +z
usemtl decal
f 1/1/1 2/2/2 3/3/3   # 两个三角拼成方片；格式 = 顶点/UV/法线 的索引
f 1/1/1 3/3/3 4/4/4
```
**`cat.mtl`**：
```mtl
newmtl decal
Kd 1 1 1
map_Kd _head_cat.png  # ← 这张材质用哪张贴图（map_Kd = 漫反射/base color 贴图）
```

要点：
- **胜负手是那 4 行 `vt`**：手写 [0,1] → 整张头像不多不少铺满方片一次。
- **`.obj` 索引从 1 开始**（不是 0）；`f a/b/c` 里三个数分别是 顶点/UV/法线 的编号。
- **路径**：`mtllib`/`map_Kd` 按 **obj 所在目录**解析相对路径；把 obj/mtl/png 放同一目录即可，**不用碰 submodule 的 assets**。

## 4. 组装成一个刚体（cube 本体 + 顶贴片）

用同一个 `ActorBuilder` 加三样，再 `build()`：

```python
def decal_cube(scene, x, quad_obj, body=(0.42, 0.44, 0.5), half=0.05):
    b = scene.create_actor_builder()
    b.add_box_collision(half_size=[half, half, half])              # ① 碰撞盒(抓取/物理)
    b.add_box_visual(half_size=[half, half, half], material=body)  # ② 蓝灰本体外观
    b.add_visual_from_file(                                        # ③ 顶面贴片(纯视觉)
        filename=quad_obj,
        pose=sapien.Pose([0, 0, half + 0.002]),   # 抬到 cube 顶面上方 2mm
        scale=[2 * half * 0.9, 2 * half * 0.9, 1] # ±0.5 单位方片 → 略小于顶面
    )
    b.set_initial_pose(sapien.Pose([x, 0, half]))
    return b.build(name=f"decal{x}")
```
- ①+② = 一个正常灰蓝方块（碰撞 + 外观）。
- ③ `add_visual_from_file` 把 quad mesh（自带贴图）当**纯视觉**贴片，`pose` 摆到顶面正上方一丁点，`scale` 把单位方片缩到顶面大小。
- 三者进**同一个 builder** → `build()` 出**一个刚体**：贴片跟 cube 一起动、一起被抓；贴片**无碰撞**（就是张贴纸），所以不影响抓取物理。

## 5. 最小可跑例（把上面串起来）

```python
import os, sys, numpy as np
from PIL import Image, ImageDraw
import sapien.core as sapien

OUT = "."  # 放 png/obj/mtl 的目录

# --- (a) 画一张图 ---
def draw_head(path, S=512):
    img = Image.new("RGB", (S, S), (248, 240, 229)); d = ImageDraw.Draw(img)
    d.ellipse([S*0.2, S*0.2, S*0.8, S*0.8], fill=(238, 150, 60))  # 随便一个头
    d.ellipse([S*0.38, S*0.45, S*0.46, S*0.55], fill=(20,20,20))
    d.ellipse([S*0.54, S*0.45, S*0.62, S*0.55], fill=(20,20,20))
    img.save(path)

# --- (b) 写 quad.obj + mtl ---
QUAD = ("mtllib {mtl}\nv -0.5 -0.5 0\nv 0.5 -0.5 0\nv 0.5 0.5 0\nv -0.5 0.5 0\n"
        "vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nvn 0 0 1\nusemtl decal\n"
        "f 1/1/1 2/2/2 3/3/3\nf 1/1/1 3/3/3 4/4/4\n")
def write_quad(tag, png):
    open(os.path.join(OUT, f"{tag}.mtl"), "w").write(f"newmtl decal\nKd 1 1 1\nmap_Kd {png}\n")
    obj = os.path.join(OUT, f"quad_{tag}.obj")
    open(obj, "w").write(QUAD.format(mtl=f"{tag}.mtl"))
    return obj

# --- (c) 场景 + 相机 + cube + 渲染 ---
draw_head(os.path.join(OUT, "head.png"))
quad = write_quad("head", "head.png")

eng = sapien.Engine(); rnd = sapien.SapienRenderer(); eng.set_renderer(rnd)
sc = eng.create_scene(sapien.SceneConfig()); sc.add_ground(0)
sc.default_physical_material = sc.create_physical_material(0.5, 0.5, 0)
sc.set_ambient_light([0.6,0.6,0.6]); sc.add_directional_light([0,0.3,-1], [0.8,0.8,0.8])

half = 0.05
b = sc.create_actor_builder()
b.add_box_collision(half_size=[half]*3)
b.add_box_visual(half_size=[half]*3, material=(0.42,0.44,0.5))
b.add_visual_from_file(filename=quad, pose=sapien.Pose([0,0,half+0.002]),
                       scale=[2*half*0.9, 2*half*0.9, 1])
b.set_initial_pose(sapien.Pose([0,0,half])); b.build(name="cube")

cam = sc.add_camera(name="c", width=640, height=480, fovy=np.deg2rad(42), near=0.05, far=20)
pos = np.array([0.0,-0.16,0.42]); fwd = np.array([0,0.35,-1.0]); fwd/=np.linalg.norm(fwd)
left = np.array([-1.0,0,0]); up = np.cross(fwd,left)
m = np.eye(4); m[:3,:3] = np.stack([fwd,left,up],1); m[:3,3] = pos
cam.entity.set_pose(sapien.Pose(m))
sc.step(); sc.update_render(); cam.take_picture()
arr = (np.clip(cam.get_picture("Color")[...,:3],0,1)*255).astype(np.uint8)
Image.fromarray(arr).save("out.png")
```
跑：`conda run -n RoboTwin python thisfile.py`（CWD 无所谓，贴图用相对/绝对路径都行）。

## 6. 常见坑（都踩过）

| 现象 | 原因 | 解法 |
|---|---|---|
| 图被裁一半 / 只见中间一块 | 用了 `create_box(texture_id)`，box 面 UV 是偏心半窗 | 改用自写 quad mesh（§3） |
| 平铺出好几个图 | 为绕 UV 用了 N×N 平铺 | 用 quad mesh 精确铺一次，别平铺 |
| 图上下颠倒 | `.obj` 的 `vt` v 轴方向与图片行序相反 | 翻转 4 行 `vt` 的第二个数（本例已是正立版） |
| 贴图加载失败/纯色 | `map_Kd` 路径按 obj 目录解析、找不到 png | obj/mtl/png 放同目录，或 `map_Kd` 写绝对路径 |
| 抓取被贴片挡住/物理异常 | 给贴片加了碰撞 | 贴片只 `add_visual_from_file`（无碰撞），碰撞只在本体 box |
| cube 和背景糊在一起 | 本体色太浅（接近白背景） | 本体给中灰/蓝灰，如 `(0.42,0.44,0.5)` |

## 7. 延伸

- **换真实猫狗照片**：把 `head.png` 换成 CC0/生成图即可，机制不变（注意授权）。
- **贴多个面**：每面各挂一张 quad（各自 pose/朝向），或直接做一个 6 面带 UV 的 box mesh。
- **为什么不改 box 的 UV**：内置 `RenderShapeBox` 没暴露 UV 缩放接口；自写 mesh 是最短可控路径。
- **和抓取的关系**：贴片无碰撞、本体是标准 box → 抓取参数完全复用 §4 Arm-Select / §7 Grasp-Approach 的 create_box 那套。
