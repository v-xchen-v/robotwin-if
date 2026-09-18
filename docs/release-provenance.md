# 当前发布与溯源校验

当前分支只提供一套六任务正式清单与结果：

- [Seed manifest](../seed-manifests/robotwin-if-arm-only-v2-20-per-mode/README.md)：每任务 20 blocks，460 回合/policy。
- [Result](../result/robotwin-if-arm-only-v2-20blocks/README.md)：6 policies，共 2760 回合、720 blocks。
- [当前判据的验证证据](../result/robotwin-if-arm-only-v2-20blocks/evidence/README.md)：Arm/Attribute 的诊断控制，不是另一套模型成绩。

旧清单、旧成绩、归档目录、兼容软链接和旧版本的一次性发布工具已从当前分支移除。
依赖本仓库的项目应固定本次整理之后的 commit，并使用上面的当前入口。
已经固定到旧 commit 的其他项目仍会读到它所固定的版本，需要更新其引用。

## 不依赖历史数据的检查

```bash
python tools/export_seed_modes.py --check
(cd seed-manifests/robotwin-if-arm-only-v2-20-per-mode && sha256sum -c SHA256SUMS)
(cd result/robotwin-if-arm-only-v2-20blocks && sha256sum -c SHA256SUMS)
bash scripts/eval.sh --policy hy_vla --output-dir outputs/policy-eval/hy-vla-new --dry-run
```

这些入口适用于浅克隆和源码下载包；新评测仍在每个 seed 上执行 oracle qualification，
不需要旧结果、Git 历史或原机器的 `/Data` 目录。结果包本身可以离线阅读。

## 完整历史溯源

已发布的 `qualification-files.json`、`suite.yml`、`reusable-results.yml` 和
`provenance.json` 保留原始路径、哈希及复用记录，内容没有改写。
其中的旧路径是发布时的来源标识，不是当前可选 release。

```bash
python seed-manifests/robotwin-if-arm-only-v2-20-per-mode/verify.py
```

这项检查通过 `tools/release_history.py` 从固定 Git commit
`2670a13f53f6e3f1cc2e6f0fdae558782cb88d7d` 读取原始证据，在仓库外的临时目录还原旧路径，
完成后自动清理。它仍核对所有原资格文件哈希、六份父清单、源码审计及 2520 条复用记录的
原始视频/动作等产物，任何失败都会传播，不会因文件迁走而跳过检查。
当前 checkout 不生成旧 release，也不会自动联网拉取。

完整检查仍需要原机的历史运行目录、源码快照和原始产物。
浅克隆缺少该提交时，校验会明确报错；仅在需要完整溯源时取得历史：

```bash
git fetch origin 2670a13f53f6e3f1cc2e6f0fdae558782cb88d7d
```

当前结果的 19 个原文件和 manifest 的 14 个原文件保持逐字节一致。
新增的 `evidence/` 收录当前判据的验证材料，各子目录有独立 `SHA256SUMS`；
证据 README 的链接和完成状态已更新，原诊断 JSON、图片及记录哈希保持不变。
旧版本及其一次性构建/打包工具保留在上述 Git 提交中，当前入口只维护已发布版本的校验。
