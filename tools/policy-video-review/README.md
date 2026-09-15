# Policy video review

人工检查 policy rollout 视频，记录 Success / Fail / 待确认，快速定位自动成功判定与肉眼观察不一致的回合。
原始视频、`_result.json`、provenance、正式结果表均只读。人工判定存入独立 SQLite 数据库，清除或修改判定也保留历史。

## 启动

只需要 Python 3.10+ 标准库。无需安装模型环境、Node、前端依赖或启动 GPU 作业。
可选 `ffprobe` 用于读取视频的真实编码帧率，以支持逐帧查看；缺少它仍可播放、拖动和标注。
不使用 episode 耗时计算出的吞吐率代替视频帧率。

```bash
python tools/policy-video-review/server.py \
  --run-dir outputs/policy-eval/if-seven-tasks-v2-wide-20blocks-001

# 等价入口（已安装 just 时）
just video-review
```

打开 **http://127.0.0.1:8893/**。默认只监听本机。
远程 SSH 开发时转发 `8893` 端口，或在自己的电脑执行：

```bash
ssh -N -L 8893:127.0.0.1:8893 msrait-04
```

然后在本机浏览器访问同一地址。`--port` 可换端口；`--host` 可指定监听地址。
这是本地复核工具，不含用户登录；多人通过同一服务协作时共享一套标签，并检查版本冲突以防覆盖。

## 复核流程

1. 选择 policy、task、mode、block、自动结果或人工状态。搜索框支持 seed、指令和备注。
   默认排除已下线 grasp，当前归档为 **3000 回合**；打开归档开关后为 **3240 回合**。
   Block 显示 `B1…B20`，同时注明原始零基 index，不能用 `seed // block_size` 代替。
2. 播放视频，切换全部 / 主相机 / 左腕 / 右腕，慢放、逐帧、跳到末帧或最后两秒。
   相机顺序读取 `_diagnostics.json`，未知相机布局时只显示完整视频。
3. 按 `1` Success、`2` Fail、`3` 待确认，点击标签立即保存当前备注。
   默认保存后自动进入当前筛选队列的下一回合；可关闭自动切换。
   单独保存备注使用 `Ctrl/Cmd + Enter`，不会把未复核回合算作已经判定。
4. 用同 seed 跨 policy 面板对比其他模型，再点击「复核此回合」切换标注对象。
   对比视频按需加载，独立播放；不同 policy 的视频时长不同，不能据播放时间假定动作同步。
5. 点击「疑似误报成功」或「疑似漏判成功」，集中回看分歧，再导出 CSV。

快捷键：空格播放 / 暂停；`←` / `→` 逐帧；`P` / `N` 上一个 / 下一个。
输入备注时不会触发判定快捷键。可以记录当前时间与零基视频帧号，便于后续复现问题。
诊断页可查看原始 result、summary、oracle、provenance；oracle 成功不代表 policy 成功。

已知待复核的 coffee box 案例可直接打开：

```text
http://127.0.0.1:8893/?episode=hy_vla/pick_diverse_object/100052
```

网页不会预先代替人工给该回合贴标签。

## 标注与导出

默认标注目录为 `outputs/policy-eval/video-reviews/<run-name>-<resolved-path-hash>/reviews.sqlite3`，
页面会显示具体路径。可以用 `--review-dir /path/to/reviews` 覆盖，必须放在原始评测目录之外。
同一个数据库绑定一个 run 的真实路径；用另一个 run 打开会拒绝，避免混用。

| 状态 | 含义 |
|---|---|
| 疑似误报成功 | 自动 Success，人工 Fail |
| 疑似漏判成功 | 自动 Fail，人工 Success |
| 与自动一致 | 两种判定相同 |
| 待确认 | 画面不足以得出明确结论，不计入分歧 |
| 源文件已更新 | 结果 / provenance / 视频身份发生变化，旧人工判定暂不计入分歧 |
| 自动判定无效 | 运行错误或原始 success/status 不一致，人工标签单独保留 |

页面顶部的统计覆盖当前任务范围，不随单个 policy/task 的筛选缩小。
「已明确复核」仅统计当前源文件对应的人工 Success / Fail。
「导出全部 CSV」导出当前任务范围内所有回合；「导出分歧」只导出明确的误报/漏判，
均不受队列里 policy、mode 或搜索筛选影响。字段包括 policy、task、seed、block、mode、指令、
自动/人工标签、分歧类型、备注、更新时间、源文件指纹、原视频路径。
`/api/export.json` 提供同样的 JSON；`?only=disagreements&archived=1` 可导出包含历史任务的分歧。

源指纹包含 result/provenance 内容 SHA-256 与视频路径、大小、mtime；不会为了浏览扫描全部视频内容。
若评测文件继续更新，点击「刷新归档」重新索引；保存和导出也会检查源变化。
多标签页同时修改同一条标注时，旧 revision 的保存会拒绝并提示刷新。
修改标签的完整历史保留在 `history` 表。正式成功率仍以原自动结果为准，工具不会重算或覆盖已发布结果。

## 支持的数据布局与限制

```text
<run-dir>/
  plan.json                                  # 可选，用于准确定位 block
  <policy>/<task>/<task>_ep<seed>_result.json   # 必需：seed/task/status/success/instruction
  <policy>/<task>/<task>_ep<seed>_[01].mp4
  <policy>/<task>/<task>_ep<seed>_step0000.png
  <policy>/<task>/<task>_ep<seed>_diagnostics.json
  <policy>/<task>/<task>_ep<seed>_provenance.json
```

支持当前六个 policy，读取正式归档和 `scripts/eval.sh` 产生的 policy/task 目录。
只扫描 canonical 目录，忽略 `batches/`、`incoming/` 等重复或未归档回合。
缺少视频的回合仍可查看记录并标记待确认；损坏的结果会在页面提示，不静默算成失败。
服务只开放索引中的视频/诊断资产；不会把整个仓库或 `/Data` 作为静态目录公开。
MP4 支持 HTTP Range 请求，浏览器无需下载整条视频便可跳转。

## 验证

```bash
python -m unittest discover -s tests -p test_policy_video_review.py
node --check tools/policy-video-review/app.js  # 开发检查，运行工具不需要 Node
```

测试覆盖归档只读、标签持久化、清除后的历史、并发冲突、源文件变化、两类分歧、
导出范围、缺视频、HTTP Range、路径限制与写入请求校验。浏览器验证使用独立 fixture 标注库，
不把测试判定写入正式复核数据库。
