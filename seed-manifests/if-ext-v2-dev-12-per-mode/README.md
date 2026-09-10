# IF v2 开发阶段 seed manifests

2026-09-09 从两个已完成的串行 oracle 预检中导出。每个任务 **12 个完整 blocks / 24 个 episodes**，
每种 mode 各 12 回合。每个任务的场景位置分区为左、中、右各 4 个。

| Manifest | task_config | Modes | Blocks | Episodes |
|---|---|---|---:|---:|
| [arm_select.json](arm_select.json) | `demo_clean_arm_select_v2` | left / right | 12 | 24 |
| [grasp_cube_approach.json](grasp_cube_approach.json) | `demo_clean_grasp_approach_v2` | top / side | 12 | 24 |

两份 manifest 都包含 exact episode seeds `100000..100023`，对应 block IDs `50000..50011`。
任务名沿用 `arm_select` 和 `grasp_cube_approach`，由不同 task_config 选择 v2 场景。
每个 policy 跑完两个任务共 48 回合；六个 policy 合计 288 回合。

## 场景与证据

- arm_select：x ±2 cm、y 10–12 cm、yaw ±3°。
- grasp_cube_approach：方块和底座一起平移，x ±1 cm、y −6～−5 cm，不旋转；oracle 固定右臂。
- 两个预检分别通过 24/24 候选抓取、6/6 重复抓取、6/6 错误指令反例、2/2 v1 回归。
  反例通过表示物体实际抬起，但因执行手臂或抓取方向不符而被成功判据拒绝。
- 每个 block 的初始 RGB、位姿与句式配对检查通过，只替换该任务考查的指令词。

原始运行目录：

- `outputs/policy-eval/arm-select-v2-probe-002`
- `outputs/policy-eval/grasp-approach-v2-probe-002`

相邻的 `<task>.probe.yml` 保存完整预检报告、原始源码哈希、控制回合、supervisor 结果、
独立检查和原始文件 SHA-256。证据来自预检工具，保留其真实 provenance；
它不是通用生成器的 `.generation.json` checkpoint。

导出时任务源码与配置哈希仍匹配。arm_select 预检后，共享语言函数增加了 grasp v2 分支；
arm v2 的配对规则等价，导出时 5 项 arm 场景/语言/CLI 检查通过，此差异也记录在证据中。

**这批 seeds 参与过场景范围调试，属于开发集。** 两个任务都保留首轮失败记录；
扩大到 50 blocks 或评估泛化时，应另外预先确定 seeds 并完成 oracle 预检。

## 使用

六个 policy 共用以下参数，模型连接参数沿用各自配置：

```text
--task arm_select
--task-config demo_clean_arm_select_v2
--seed-manifest seed-manifests/if-ext-v2-dev-12-per-mode/arm_select.json
--blocks 12
```

```text
--task grasp_cube_approach
--task-config demo_clean_grasp_approach_v2
--seed-manifest seed-manifests/if-ext-v2-dev-12-per-mode/grasp_cube_approach.json
--blocks 12
```

快速检查可用 `--blocks 2` 选择前两个完整 blocks。保持各 policy 的 seed 顺序和分母一致，
不按 policy 成败增删 seeds。旧 `demo_clean` 配置与这两份 manifest 不匹配。
配置安装方式见 [arm v2](../../docs/arm-select-v2.md) 和 [grasp v2](../../docs/grasp-approach-v2.md)。

## 校验

在仓库根目录执行，无需启动 simulator：

```bash
python tools/validate_if_seed_manifest.py seed-manifests/if-ext-v2-dev-12-per-mode
```

预期每份显示 `blocks=12`，两个 mode 的分母都是 12。此命令校验 flat manifest；
其 `--require-evidence` 选项只接受通用生成器的 `.generation.json`，不读取本目录的 `.probe.yml`。
本次导出另行核验了完整预检报告、所有控制回合、manifest 哈希和任务/配置哈希。

Canonical manifest SHA-256：

```text
arm_select          1471bd2ffa9e8ae6d6675e33d9c63897aa8f8749aa91308dbad9a02b92d8c44c
grasp_cube_approach  d0ca555ba05e0a4f53667d63d281a46fe9ed2f18c57871dac05669571773b797
```
