# 下载完整评测结果与视频

当前完整备份为 **`opensource-eval-stapler-v1-20blocks-20261027`**：六个开源 checkpoint、六任务、
每任务 20 blocks，共 **2760 个正式回合 / 视频、720 blocks**，包含成功和失败。
整个目录有 **52,821 个文件，8,790,812,054 bytes（约 8.19 GiB）**，建议预留至少 10 GB 空间。

只查看成绩，可直接打开仓库内的[结果包](../result/robotwin-if-press-lift-stapler-v1-20blocks/README.md)；
任务示例视频见[主 README](../README.md#task-demos)。下面的完整备份还包含动作、初始观测和运行证据。

## 访问权限

备份存放在 Azure Storage 账号 `eaidatashare`、容器 `xichen` 下：

```text
https://eaidatashare.blob.core.windows.net/xichen/robotwin-if/results/opensource-eval-stapler-v1-20blocks-20261027
```

**当前需要授权下载。** 此存储账号禁用了匿名访问，直接用浏览器打开链接会返回
`409 PublicAccessNotPermitted`。下载账号需要该容器的读取、列出权限，例如容器范围的
`Storage Blob Data Reader` 角色；请由存储管理员授予。

以下为 Linux / WSL 的 Bash 命令，需要 [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)、
[AzCopy v10](https://learn.microsoft.com/azure/storage/common/storage-use-azcopy-v10) 和 `sha256sum`。
在有浏览器的电脑上通过 `az login` 完成网页登录，AzCopy 随后复用 Azure CLI 的登录状态。

## 下载

```bash
az login
export AZCOPY_AUTO_LOGIN_TYPE=AZCLI

BUNDLE=opensource-eval-stapler-v1-20blocks-20261027
BUNDLE_URL="https://eaidatashare.blob.core.windows.net/xichen/robotwin-if/results/$BUNDLE"
BUNDLE_DIR="$PWD/downloads/$BUNDLE"

# 选择一个新的空目录，保持备份内部的相对路径。
mkdir -p "$BUNDLE_DIR"
azcopy copy "$BUNDLE_URL" "$BUNDLE_DIR" \
  --recursive=true --as-subdir=false --check-md5=FailIfDifferentOrMissing
```

`--as-subdir=false` 使 `README.md`、`SHA256SUMS` 和 `evaluation/` 直接位于 `$BUNDLE_DIR` 下。
下载时逐文件检查 Azure 的 Content-MD5，完成后继续执行下方 SHA-256 校验。
若已登录仍提示权限不足，请确认登录账号、租户及该容器的数据读取权限。

## 校验

先验证随备份下载的校验清单，再检查其覆盖的全部文件：

```bash
cd "$BUNDLE_DIR"
printf '%s  %s\n' \
  '15224cd42cbe37f6603574a62780fed5c1a7d7d64131bffdd20953f79f80928b' \
  'SHA256SUMS' | sha256sum --check -
bash verify_backup.sh
```

预期分别输出 `SHA256SUMS: OK` 和 `Backup integrity OK.`。清单覆盖打包时的所有文件，自身除外。
打开视频查看器后新增的人工标注文件不在这份冻结清单内。

## 查看成绩与全部视频

打开 `reports/results.html` 查看六模型成绩。视频查看器只需 **Python 3.10+ 标准库**，
可选安装 `ffprobe` 以支持准确帧率与逐帧查看。

```bash
cd "$BUNDLE_DIR"
bash view_videos.sh
```

浏览器访问 **http://127.0.0.1:8898/**，按 policy、task、mode 和成功/失败筛选全部 2760 回合。
可用 `bash view_videos.sh --port 8899` 更换端口；在远程机器运行时，在本机另开终端转发：

```bash
ssh -N -L 8898:127.0.0.1:8898 user@your-server
```

然后在本机访问同一浏览器地址。这个地址对应自己启动的服务。
操作说明见[视频复核工具](../tools/policy-video-review/README.md)。

## 备份内容

| 路径 | 内容 |
|---|---|
| `reports/` | 冻结成绩、逐回合表、六任务 manifests、checkpoint 身份和来源证据 |
| `evaluation/<policy>/<task>/` | 正式回合的视频、动作、初始观测、instruction、判定和 provenance |
| `episode-index.csv` | 2760 个正式回合的相对路径索引，可定位每条视频与对应数据 |
| `evaluation/batches/`、其他 support 目录 | 原始批次、推理中间产物、源码快照和恢复记录；重复/中断尝试不计入正式索引 |
| `audit/` | 调度日志与五任务复用来源 |
| `tools/policy-video-review/` | 随备份提供的独立视频查看器 |
| `BACKUP.json`、`SHA256SUMS` | 打包范围、核验记录及文件校验清单 |

备份包含 checkpoint 的 repo、revision、哈希和推理配置；**模型权重、模型环境和仿真资产需另行安装**，
见 [policies](../policies/README.md) 与 [Quickstart](quickstart.md)。
原始 JSON / 日志中的绝对路径保留为历史来源记录；下载后的定位以 `episode-index.csv` 的相对路径为准。
整个目录可继续复制或移动。人工标注另存于备份目录的 `outputs/policy-eval/video-reviews/` 下，正式结果保持只读。
