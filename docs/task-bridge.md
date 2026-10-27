# 将 IF 任务安装到 RoboTwin

Bridge 将本仓库的任务、共享 helper 和指令 JSON 软链到 RoboTwin，检查已有目标的归属和兼容性。
它负责让 runtime 找到任务；当前执行哪六项任务由 [IF inventory](../eval_cfg/if_tasks.yml) 和 [Stapler manifest](../seed-manifests/robotwin-if-press-lift-stapler-v1-20-per-mode/README.md)决定。
安装列表仍包含 Bottle / Bell 兼容任务及共享 helper，这些兼容项不计入当前六任务成绩。

## 仓库内的 runtime

当前 submodule 与 installer 锁定 RoboTwin commit `b82ffb81d291d14c24be444bb7b6f81719481e0f`。
从项目根目录执行：

```bash
bash scripts/bridge_tasks.sh --dry-run
bash scripts/bridge_tasks.sh
bash scripts/bridge_tasks.sh --check
```

软链与 `.robotwin-if-bridge.json` 是本机安装状态。新 clone 或 worktree 需要重新 bridge。
Arm 的 `demo_clean_arm_select_v3.yml` 按[交付说明](branch-delivery.md)另行安装。

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
