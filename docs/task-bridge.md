# 将 IF 任务安装到 RoboTwin

Bridge 将本仓库的任务、共享 helper、指令 JSON 和专用 task config 软链到 RoboTwin，检查已有目标的归属和兼容性。
它负责让 runtime 找到任务；当前执行哪六项任务由 [IF inventory](../eval_cfg/if_tasks.yml) 和 [Stapler manifest](../seed-manifests/robotwin-if-press-lift-stapler-v1-20-per-mode/README.md)决定。
安装列表包含当前六任务、六个共享 helper、六份 instruction 和 Arm cube-v3 配置，共 19 个软链。

## 仓库内的 runtime

当前 submodule、installer 与 bridge 使用 [`runtime_pins.json`](../scripts/runtime_pins.json) 中的官方已验证基线 `0aeea2d`，不自动追踪上游最新版本。
历史 `b82ffb81` 仅在该基线上提交了四个 IF 软链，无法从配置的官方上游获取；这些链接现在统一由 bridge 管理。
已发布 manifest/result 中的历史 commit 记录保留原样。
从项目根目录执行：

```bash
git submodule update --init third_party/robotwin
bash scripts/bridge_tasks.sh --dry-run
bash scripts/bridge_tasks.sh
bash scripts/bridge_tasks.sh --check
```

软链与 `.robotwin-if-bridge.json` 是本机安装状态。新 clone 或 worktree 需要重新 bridge。
Arm 的 `task_config/demo_clean_arm_select_v3.yml` 随 bridge 安装、校验和解绑，无需手工 `ln -s`。
升级旧安装时，已正确指向本仓库配置的软链会被接管；同名真实文件（即使内容一致）或其他来源的软链会保留并报告冲突。
其他原生配置不由 bridge 管理。首次安装完整流程见 [Quickstart](quickstart.md)。

## 外部 runtime

```bash
bash scripts/bridge_tasks.sh --robotwin-dir /path/to/RoboTwin --dry-run
bash scripts/bridge_tasks.sh --robotwin-dir /path/to/RoboTwin
bash scripts/bridge_tasks.sh --robotwin-dir /path/to/RoboTwin --check
```

目标解析顺序为 `--robotwin-dir`、`ROBOTWIN_DIR`、默认 `third_party/robotwin`。
使用不同 commit 或存在兼容性文件修改时，先审阅差异，再显式传入 `--allow-compatible-commit`；
后续 `--check` 使用同一参数。该参数保留 Base_Task、工具导出、指令生成和目录布局的 API 检查。

```bash
bash scripts/bridge_tasks.sh --robotwin-dir /path/to/RoboTwin --allow-compatible-commit --dry-run
```

确认检查结果后，去掉 `--dry-run` 执行安装。Bridge 只修改自己管理的链接，真实文件和冲突链接会使 preflight 失败。

## 解绑

```bash
bash scripts/unbridge_tasks.sh --dry-run
bash scripts/unbridge_tasks.sh
```

解绑依照 ownership manifest 处理；安装后被外部修改的目标会保留并报告。
外部 runtime 同样传入 `--robotwin-dir`。完整参数与实现见 [`_task_bridge.py`](../scripts/_task_bridge.py)。
