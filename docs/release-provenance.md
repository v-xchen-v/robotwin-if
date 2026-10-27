# 当前发布与溯源校验

当前 seed 清单为 **Press/Lift Stapler v1**，包含 6 个任务、每任务 20 blocks：

- [Seed manifest](../seed-manifests/robotwin-if-press-lift-stapler-v1-20-per-mode/README.md)：460 回合/policy。
- [完整评测结果](../result/robotwin-if-press-lift-stapler-v1-20blocks/README.md)：6 个开源 checkpoint，共 2760 回合、720 blocks。
- [Checkpoint 版本](../result/robotwin-if-press-lift-stapler-v1-20blocks/checkpoints.json)与[复用来源](../result/robotwin-if-press-lift-stapler-v1-20blocks/provenance.json)：Stapler 新跑 240 回合，其余五任务复用 2520 回合。

`seed-manifests/` 与 `result/` 分别只保留这一套清单和结果包。旧 Arm-only-v2 结果及旧清单已从 master 移除，
可在[备份分支 master-261027-staper-v1](https://github.com/v-xchen-v/robotwin-if/tree/master-261027-staper-v1)查阅。

## 当前版本校验

```bash
python tools/export_seed_modes.py --check
python seed-manifests/robotwin-if-press-lift-stapler-v1-20-per-mode/verify.py
(cd result/robotwin-if-press-lift-stapler-v1-20blocks && sha256sum -c SHA256SUMS)
bash scripts/eval.sh --policy hy_vla --output-dir outputs/policy-eval/hy-vla-new --dry-run
```

以上检查不启动模型或仿真。当前清单自带订书器筛选证据、其余五任务的原资格证据、
父清单描述及源码快照；浅克隆和源码下载包都能校验，不需要恢复旧清单目录或访问原机器的 `/Data`。
实际 policy eval 仍对 manifest 中的固定 seeds 执行标准 setup 检查，不替换失败 seed。

清单、seed/mode 导出、资格记录及已发布结果保持原始字节。资格记录中的旧路径是来源标识；
校验使用当前包内保留的证据。旧结果包的路径和哈希也保留为发布时的历史记录。
[历史 Arm-only-v2 来源分析](recon/open-source-eval-provenance.md)及旧发布工具应在备份分支的对应版本下使用。

## 清理后的五任务结果复用

`prepare_stapler_policy_suite.py`、formal prepare 和 `publish_stapler_policy_results.py`
通过 `tools/release_history.py` 从固定提交 `ac582a75267126c7a8fe17c220475d517b73882b` 读取旧包的
`episodes.csv` 和 `checkpoints.json`。读取不 checkout、不恢复旧目录、不修改当前已发布结果。
原有逐回合哈希、seed/config、成功判据及 checkpoint 核对继续生效；原始运行产物仍由 `--old-run` 提供。

浅克隆执行这类历史复用/重新发布前，可取回对应提交：

```bash
git fetch origin ac582a75267126c7a8fe17c220475d517b73882b
```

查看当前结果、校验当前包或从当前 manifest 全新评测，不需要历史 Git 提交。
