# 下载完整评测结果与视频

当前备份为 **Attribute Size 6 cm**：2760 个正式回合 / 视频、720 blocks，约 **5.78 GiB**。
Size 使用已完成的 240 条 6 cm 重测输出，其余 2520 条复用旧输出；正式分数只有 VLAct 更新。
原 seed manifest 不变。仓库仅保存[精简成绩](../result/README.md)，完整证据保存在 Azure。
[上传校验记录](../result/robotwin-if-press-lift-stapler-v2-size6cm-20blocks/azure-backup.json)包含地址、文件数和校验清单哈希。

## 访问权限

备份存放在 Azure Storage 账号 `eaidatashare`、容器 `xichen` 下：

```text
https://eaidatashare.blob.core.windows.net/xichen/robotwin-if/results/
```

当前目录为 `opensource-eval-stapler-v2-size6cm-20blocks-20261030`，已完成上传和远端校验。

**当前需要授权下载。** 此存储账号禁用了匿名访问，直接用浏览器打开链接会返回
`409 PublicAccessNotPermitted`。下载账号需要该容器的读取、列出权限，例如容器范围的
`Storage Blob Data Reader` 角色；请由存储管理员授予。

以下为 Linux / WSL 的 Bash 命令，需要 [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)、
[AzCopy v10](https://learn.microsoft.com/azure/storage/common/storage-use-azcopy-v10) 和 `sha256sum`。
在有浏览器的电脑上通过 `az login` 完成网页登录，AzCopy 随后复用 Azure CLI 的登录状态。

## 下载

```bash
# 已登录可省略；需要登录时使用浏览器，不使用 device code。
az login
export AZCOPY_AUTO_LOGIN_TYPE=AZCLI

BUNDLE_URL=https://eaidatashare.blob.core.windows.net/xichen/robotwin-if/results/opensource-eval-stapler-v2-size6cm-20blocks-20261030
BUNDLE_SHA256=248faf9b4943ddc577b3eab7a382b1a47674e6eb83b2043f01f023fd40e60c44
BUNDLE=${BUNDLE_URL##*/}
BUNDLE_DIR="$PWD/downloads/$BUNDLE"

# 选择新的空目录，保持备份内部的相对路径。
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
printf '%s  %s\n' "$BUNDLE_SHA256" 'SHA256SUMS' | sha256sum --check -
bash verify_backup.sh
```

预期分别输出 `SHA256SUMS: OK` 和 `Backup integrity OK.`。清单覆盖打包时的所有文件，自身除外。
打开视频查看器后新增的人工标注文件不在这份冻结清单内。

## 查看成绩与全部视频

也可在 repo 根目录直接运行当前网页，从 Azure 按需加载，无需完整下载：

```bash
just video-review-azure
```

打开 **http://127.0.0.1:8893/**。顶部成绩表支持模型 × 任务 / mode 对比，点击单元格进入视频队列。
服务所在机器需要已完成浏览器 `az login`，账号需有 Blob 读取权限。
入口直接读取当前结果目录的 `azure-backup.json`，不依赖 release registry；不用 just 的命令见[工具说明](../tools/policy-video-review/README.md)。
已发布备份中自带的是当时冻结的查看器；新增的 Azure 入口和成绩总览使用当前 repo 中的版本。

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
| `audit/`、其他 support 目录 | 随版本保留的运行源码、推理参考及来源证据；内容范围见该包 `BACKUP.json` |
| `tools/policy-video-review/` | 随备份提供的独立视频查看器 |
| `BACKUP.json`、`SHA256SUMS` | 打包范围、核验记录及文件校验清单 |

备份包含 checkpoint 的 repo、revision、哈希和推理配置；**模型权重、模型环境和仿真资产需另行安装**，
见 [policies](../policies/README.md) 与 [Quickstart](quickstart.md)。
原始 JSON / 日志中的绝对路径保留为历史来源记录；下载后的定位以 `episode-index.csv` 的相对路径为准。
整个目录可继续复制或移动。v2 的人工标注另存于备份目录的 `reviews/`；旧 v1 使用 `outputs/policy-eval/video-reviews/`。正式结果保持只读。

旧 8 cm 备份仍保存在相同前缀的 `opensource-eval-stapler-v1-20blocks-20261027`，
校验清单 SHA-256 为 `15224cd42cbe37f6603574a62780fed5c1a7d7d64131bffdd20953f79f80928b`。
下载时替换上面的 URL 和哈希即可；下载后用包内 `view_videos.sh` 浏览。
