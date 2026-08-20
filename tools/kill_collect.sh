#!/usr/bin/env bash
# kill_collect.sh — 彻底清理被中断（Ctrl+Z / Ctrl+C）但仍占资源的采集任务。
#
# 背景：`bash collect_data.sh ...` 只是壳，真正吃显存/内存的是它 fork 出的
# python，python 又会 fork 出 multiprocessing 子进程。Ctrl+Z 只是把它们挂起
# （状态 T），资源全都还占着。杀单个 PID 常杀不干净 —— 要按「进程组」整组带走。
#
# 用法:
#   bash tools/kill_collect.sh                 # 默认清理匹配 'collect_data' 的进程
#   bash tools/kill_collect.sh operate_stapler # 用别的关键词锁定这次任务
#   bash tools/kill_collect.sh collect_data -y # 跳过确认，直接杀
#   bash tools/kill_collect.sh collect_data --gpu # 顺便清掉自己残留的 GPU 计算进程
#
# 安全:
#   - 默认只动「当前用户」的进程，不碰共享机上别人（如 root）的任务。
#   - 默认先预览、再确认，才动手。
set -uo pipefail

PATTERN="collect_data"
ASSUME_YES=0
CLEAN_GPU=0

for arg in "$@"; do
  case "$arg" in
    -y|--yes)  ASSUME_YES=1 ;;
    --gpu)     CLEAN_GPU=1 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)        echo "未知选项: $arg" >&2; exit 2 ;;
    *)         PATTERN="$arg" ;;
  esac
done

ME="$(id -un)"

# 排除脚本自身：否则 `bash kill_collect.sh <pattern>` 的命令行里既含脚本名、
# 又含 pattern，会把本进程和它的 shell 匹配进来，整组一杀就把自己干掉了。
SELF_PGID="$(ps -o pgid= -p "$$" 2>/dev/null | tr -d ' ')"
SELF_NAME="$(basename "$0")"

echo "== 匹配进程 (user=$ME, pattern='$PATTERN') =="
mapfile -t PIDS < <(
  pgrep -u "$ME" -f "$PATTERN" 2>/dev/null | while read -r p; do
    [ "$p" = "$$" ] && continue                                  # 本进程
    pg="$(ps -o pgid= -p "$p" 2>/dev/null | tr -d ' ')"
    [ "$pg" = "$SELF_PGID" ] && continue                         # 本脚本所在进程组
    cmd="$(ps -o cmd= -p "$p" 2>/dev/null)"
    case "$cmd" in *"$SELF_NAME"*) continue ;; esac              # 脚本自身的其它调用
    echo "$p"
  done
)

if [ "${#PIDS[@]}" -eq 0 ]; then
  echo "没有匹配的进程。"
else
  # 预览：pid / 进程组 / 状态(T=挂起) / 内存 / 运行时长 / 命令
  ps -o pid,pgid,stat,rss,etime,cmd -p "$(IFS=,; echo "${PIDS[*]}")"

  if [ "$ASSUME_YES" -ne 1 ]; then
    read -rp "杀掉以上进程 + 它们所在的进程组？[y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || { echo "已取消。"; exit 0; }
  fi

  # 按进程组整组 SIGKILL：一次带走 python 及其 mp 子进程。
  # 对挂起(T)进程直接用 -9，因为它们收不到可捕获信号，唯有 SIGKILL 立即生效。
  declare -A DONE_PGID=()
  for pid in "${PIDS[@]}"; do
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
    [ -n "$pgid" ] || continue
    [ -n "${DONE_PGID[$pgid]:-}" ] && continue
    DONE_PGID[$pgid]=1
    kill -9 -- "-$pgid" 2>/dev/null || true
  done
  # 兜底：再按模式扫一遍漏网的（比如已脱离原进程组的孤儿）。
  pkill -9 -u "$ME" -f "$PATTERN" 2>/dev/null || true

  sleep 1
  leftover="$(pgrep -u "$ME" -f "$PATTERN" 2>/dev/null | grep -vx "$$" | tr '\n' ' ')"
  if [ -n "$leftover" ]; then
    echo "!! 仍有残留 PID: $leftover （可能权限不足或正在退出，稍等重跑本脚本）"
  else
    echo "进程已清干净。"
  fi
fi

# ---- GPU 检查 / 清理 ----
command -v nvidia-smi >/dev/null 2>&1 || { echo "（无 nvidia-smi，跳过 GPU 检查）"; exit 0; }

echo "== 当前用户($ME) 残留的 GPU 计算进程 =="
found_gpu=0
while IFS=, read -r gpid gmem; do
  gpid="$(echo "$gpid" | tr -d ' ')"
  [ -n "$gpid" ] || continue
  owner="$(ps -o user= -p "$gpid" 2>/dev/null | tr -d ' ')"
  if [ "$owner" = "$ME" ]; then
    found_gpu=1
    printf "  pid=%s  mem=%s\n" "$gpid" "$gmem"
    if [ "$CLEAN_GPU" -eq 1 ]; then
      kill -9 "$gpid" 2>/dev/null && echo "    -> 已杀"
    fi
  fi
done < <(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader 2>/dev/null)

if [ "$found_gpu" -eq 0 ]; then
  echo "  无。显存已释放。"
elif [ "$CLEAN_GPU" -ne 1 ]; then
  echo "  （加 --gpu 可一并杀掉这些残留 GPU 进程）"
fi
