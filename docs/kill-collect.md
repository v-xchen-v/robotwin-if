# 清理中断的采集任务（kill_collect）

`bash collect_data.sh <task> <config> <gpu>` 跑到一半按了 **Ctrl+Z** 想停,结果发现
显存/内存还占着、`nvidia-smi` 里进程赖着不走。这篇说明为什么会这样,以及怎么彻底清干净。

## 为什么中断了还占资源

1. **Ctrl+Z 不是退出**。它发的信号是 `SIGTSTP`,只把进程**挂起**(`ps` 里状态变
   `T` = stopped),进程连同它占的显存、内存原封不动。真正要它退出得用 Ctrl+C
   (`SIGINT`)或 `kill`。

2. **一条采集命令 = 一串进程,不是一个**:
   ```
   bash collect_data.sh          ← 壳,几乎不占资源
     └─ python collect_data.py   ← 主进程,占大头内存
          └─ mp 子进程 × N       ← multiprocessing spawn 出来的,占 GPU
   ```
   所以杀单个 PID 常常杀不干净:杀了壳,python 还在;杀了 python 父进程,mp 子进程
   可能变孤儿继续占 GPU。**正确做法是按「进程组(PGID)」整组带走**,一次连子孙一起清。

3. **挂起(`T`)的进程只认 SIGKILL**。stopped 进程收不到可捕获信号(`SIGTERM` 要先
   `SIGCONT` 唤醒才处理),而 `SIGKILL`(`-9`)不可拦截、立即生效。所以对挂起的采集
   进程直接 `-9`。

## 一键清理:`tools/kill_collect.sh`

```bash
bash tools/kill_collect.sh                    # 默认清理命令行含 'collect_data' 的进程
bash tools/kill_collect.sh operate_stapler    # 用能唯一锁定这次任务的关键词
bash tools/kill_collect.sh collect_data -y    # 跳过确认,直接杀
bash tools/kill_collect.sh collect_data --gpu # 顺便杀掉自己残留的 GPU 计算进程
```

它做的事:
1. `pgrep -u $USER -f <关键词>` 找出**当前用户**的匹配进程(不碰共享机上别人的任务),
   并**排除脚本自身**(否则命令行里含关键词会误杀自己);
2. 预览 pid / 进程组 / 状态 / 内存,确认后**按进程组 `-9` 整组杀**,再 `pkill` 兜底漏网的;
3. 检查 `nvidia-smi`,列出(可选一并清掉)当前用户残留的 GPU 计算进程。

默认**先预览再确认**;共享机上跑请务必核对预览列表,别误伤别人。

## 手动版(记不住脚本时的通用套路)

```bash
pgrep -af collect_data          # ① 预览要杀什么(-f 匹配整条命令行)
pkill -9 -f collect_data        # ② 按模式一把梭杀掉(关键词要能唯一锁定,别用 'python' 这种泛词)
nvidia-smi                      # ③ 确认显存真的放了;有残留就 kill -9 对应 pid
```

更稳的按进程组杀:
```bash
ps -o pid,pgid,cmd -C python | grep collect_data   # 拿 PGID
kill -9 -<PGID>                                     # pid 前加负号 = 杀整个进程组
```

如果就在**同一个交互 shell** 里 Ctrl+Z 的,最省事:
```bash
jobs -l         # 看作业号和 pid
kill -9 %1      # 杀掉 1 号作业
```

## 清完之后重跑

采集脚本 `collect_data.py` **支持断点续传**:它会跳过 `data/<task>/<config>/data/` 下
已存在的 `episodeN.hdf5`,从缺口继续。所以:

- **想接着采** → 进程清掉后直接重跑 `bash collect_data.sh <task> <config> <gpu>`,自动续。
- **想从头重采** → 先删数据目录再跑:
  ```bash
  rm -rf data/<task>/<config>
  bash collect_data.sh <task> <config> <gpu>
  ```

> 一句话:`kill_collect.sh` 清进程 → `nvidia-smi` 验显存 → 按需删数据 → 重跑。
