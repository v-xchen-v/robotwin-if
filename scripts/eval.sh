#!/usr/bin/env bash
# One existing model server, one simulator, sequential exact-seed task evaluation.
set -euo pipefail
REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONNOUSERSITE=1
SIM_PYTHON=${SIM_PYTHON:-python3}
POLICY= TASK=all OUTPUT_DIR= SERVER_URL=
BLOCKS=20 SIM_GPU=0 MODEL_GPU=1 DRY_RUN=0
MANIFEST_DIR="$REPO_ROOT/seed-manifests/robotwin-if-arm-only-v2-20-per-mode"
ROBOTWIN_DIR="$REPO_ROOT/third_party/robotwin"

usage() {
  cat <<'HELP'
Usage: bash scripts/eval.sh --policy POLICY --output-dir PATH [options]
Start the policy's model server first, following policies/<policy>/README.md.
Policies: xvla, lingbot_va, lingbot_vla, vlact, dm05, hy_vla

  --task TASK          One maintained task, or all (default: all six)
  --blocks N           First N complete blocks, 1..20 (default: 20)
  --sim-gpu N          Physical GPU index for the simulator (default: 0)
  --model-gpu N        Physical GPU index of the running server (default: 1)
  --server-url URL     Override the policy's localhost HTTP/WebSocket endpoint
  --robotwin-dir PATH  Installed RoboTwin checkout
  --manifest-dir PATH  Six-task 20-block release with checked seed-modes exports
  --python PATH        RoboTwin Python (default: SIM_PYTHON or python3)
  --dry-run            Print the plan; no GPU, server connection or output writes
  -h, --help           Show this help

Task output: PATH/<policy>/<task>/; existing task directories are never overwritten.
A completed policy failure counts as a result; infrastructure errors stop the script.
GPU queries time out after 8s; temperature >=87C or memory pressure stops this sim.
The separately started model server remains owned by its launcher.
HELP
}
fail() { echo "error: $*" >&2; exit 2; }
while (($#)); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --policy|--task|--output-dir|--blocks|--sim-gpu|--model-gpu|--server-url|--robotwin-dir|--manifest-dir|--python)
      (($# >= 2)) || fail "missing value for $1"
      case "$1" in
        --policy) POLICY=$2 ;; --task) TASK=$2 ;; --output-dir) OUTPUT_DIR=$2 ;;
        --blocks) BLOCKS=$2 ;; --sim-gpu) SIM_GPU=$2 ;; --model-gpu) MODEL_GPU=$2 ;;
        --server-url) SERVER_URL=$2 ;; --robotwin-dir) ROBOTWIN_DIR=$2 ;;
        --manifest-dir) MANIFEST_DIR=$2 ;; --python) SIM_PYTHON=$2 ;;
      esac
      shift 2 ;;
    *) fail "unknown argument: $1" ;;
  esac
done
case "$POLICY" in
  xvla) DEFAULT_URL=http://127.0.0.1:8010 ;;
  lingbot_va) DEFAULT_URL=ws://127.0.0.1:8011 ;;
  lingbot_vla) DEFAULT_URL=ws://127.0.0.1:8012 ;;
  vlact) DEFAULT_URL=ws://127.0.0.1:8013 ;;
  dm05) DEFAULT_URL=http://127.0.0.1:8014 ;;
  hy_vla) DEFAULT_URL=ws://127.0.0.1:8015 ;;
  *) fail "--policy must name one of the six policies (see --help)" ;;
esac
[[ -n "$OUTPUT_DIR" ]] || fail '--output-dir is required'
[[ "$BLOCKS" =~ ^([1-9]|1[0-9]|20)$ ]] || fail '--blocks must be 1..20'
[[ "$SIM_GPU" =~ ^[0-9]+$ && "$MODEL_GPU" =~ ^[0-9]+$ ]] || fail 'GPU indices must be nonnegative integers'
SIM_GPU=$((10#$SIM_GPU))
MODEL_GPU=$((10#$MODEL_GPU))
[[ "$SIM_GPU" != "$MODEL_GPU" ]] || fail 'sim and model must use separate GPUs'
SERVER_URL=${SERVER_URL:-$DEFAULT_URL}
# Resolve user paths before the evaluator changes cwd into RoboTwin.
OUTPUT_DIR=$("$SIM_PYTHON" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$OUTPUT_DIR")
ROBOTWIN_DIR=$("$SIM_PYTHON" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$ROBOTWIN_DIR")
MANIFEST_DIR=$("$SIM_PYTHON" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$MANIFEST_DIR")
TASK_ROWS=$("$SIM_PYTHON" - "$MANIFEST_DIR" "$TASK" "$BLOCKS" <<'PY'
import sys
from if_benchmark.seed_modes import build_seed_modes, check_seed_modes
from if_benchmark.seed_contracts import validate_active_seeds
check_seed_modes(sys.argv[1])
data = build_seed_modes(sys.argv[1])
selected = [t for t in data['tasks'] if sys.argv[2] in ('all', t['task'])]
if not selected:
    raise SystemExit('Unknown or retired task: ' + sys.argv[2])
for task in selected:
    validate_active_seeds(task['task'], [e['seed'] for e in task['episodes']])
    count = sum(e['block'] < int(sys.argv[3]) for e in task['episodes'])
    print(task['task'], task['task_config'], count, sep='\t')
PY
)
# Preflight all destinations before starting any task.
while IFS=$'\t' read -r task config count; do
  [[ ! -e "$OUTPUT_DIR/$POLICY/$task" && ! -L "$OUTPUT_DIR/$POLICY/$task" ]] || fail "task output exists: $OUTPUT_DIR/$POLICY/$task"
  if (( ! DRY_RUN )); then
    [[ -f "$ROBOTWIN_DIR/envs/$task.py" ]] || fail "task is not bridged: $task (see docs/branch-delivery.md)"
    [[ -f "$ROBOTWIN_DIR/task_config/$config.yml" ]] || fail "missing task config: $config (see docs/branch-delivery.md)"
    if [[ "$config" == demo_clean_arm_select_v2 || "$config" == demo_clean_arm_select_v3 ]]; then
      cmp -s "$REPO_ROOT/tasks/task_config/$config.yml" "$ROBOTWIN_DIR/task_config/$config.yml" || fail 'arm_select config differs from the delivered config'
    fi
  fi
done <<< "$TASK_ROWS"

worker=
cleanup() {
  if [[ -n "$worker" ]]; then
    kill -TERM -- "-$worker" 2>/dev/null || true
    for ((i=0; i<25; i++)); do
      kill -0 -- "-$worker" 2>/dev/null || break
      sleep 0.2
    done
    kill -KILL -- "-$worker" 2>/dev/null || true
    wait "$worker" 2>/dev/null || true
    worker=
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

gpu_check() {
  local rows
  rows=$(timeout 8 nvidia-smi --id="$SIM_GPU,$MODEL_GPU" \
    --query-gpu=index,memory.used,memory.total,temperature.gpu,utilization.gpu \
    --format=csv,noheader,nounits) || fail 'GPU query failed or timed out'
  "$SIM_PYTHON" -c '
import sys
rows = {int(r[0]): list(map(int, r[1:])) for r in (line.split(",") for line in sys.argv[1].splitlines())}
sim, model = int(sys.argv[2]), int(sys.argv[3])
if set(rows) != {sim, model}:
    raise SystemExit("Missing GPU")
for index, (used, total, temp, utilization) in rows.items():
    if temp >= 87 or used >= total * .96:
        raise SystemExit(("GPU pressure", index, rows[index]))
    if index == sim:
        if used >= 24576:
            raise SystemExit(("Simulator memory limit", used))
        if sys.argv[4] == "idle":
            if used >= 2048 or utilization >= 10:
                raise SystemExit(("Simulator GPU is not idle", rows[index]))
' "$rows" "$SIM_GPU" "$MODEL_GPU" "$1" || fail 'GPU safety check failed'
}
if (( ! DRY_RUN )); then
  command -v setsid >/dev/null
  command -v flock >/dev/null
  command -v timeout >/dev/null
  exec 9>"${TMPDIR:-/tmp}/robotwin-if-eval-${UID}-${SIM_GPU}.lock"
  flock -n 9 || fail "another eval.sh owns simulator GPU $SIM_GPU"
fi
# The Python bootstrap pins SAPIEN as well as CUDA; it adds no scheduling layer.
BOOTSTRAP='import importlib, sys
from tools.sim_device import pin_renderer
pin_renderer()
policy = sys.argv.pop(1)
sys.exit(importlib.import_module("policies." + policy + ".eval").main())'
while IFS=$'\t' read -r task config count; do
  destination="$OUTPUT_DIR/$POLICY/$task"
  command=("$SIM_PYTHON" -c "$BOOTSTRAP" "$POLICY" --task "$task" --task-config "$config"
    --seed-manifest "$MANIFEST_DIR/$task.json" --blocks "$BLOCKS" --instruction-type unseen
    --sim-gpu "$SIM_GPU" --robotwin-dir "$ROBOTWIN_DIR" --server-url "$SERVER_URL"
    --request-timeout 600 --output-dir "$destination")
  echo "$POLICY / $task: $BLOCKS blocks, $count episodes -> $destination"
  if (( DRY_RUN )); then
    printf 'CUDA_VISIBLE_DEVICES=%q ' "$SIM_GPU"
    printf '%q ' "${command[@]}"
    printf '\n'
    continue
  fi
  gpu_check idle
  CUDA_VISIBLE_DEVICES="$SIM_GPU" setsid "${command[@]}" &
  worker=$!
  while kill -0 "$worker" 2>/dev/null; do
    gpu_check running
    sleep 15
  done
  rc=0
  wait "$worker" || rc=$?
  cleanup
  (( rc == 0 || rc == 1 )) || fail "$task evaluator exited $rc; inspect its output"
  "$SIM_PYTHON" - "$destination" "$MANIFEST_DIR/$task.json" "$count" <<'PY'
import json, sys
from pathlib import Path
output = Path(sys.argv[1])
summary = json.loads((output / 'summary.json').read_text())
expected = json.loads(Path(sys.argv[2]).read_text())['seeds'][:int(sys.argv[3])]
records = [json.loads(line) for line in (output / 'results.jsonl').read_text().splitlines()]
if not summary['complete'] or summary['error'] is not None:
    raise SystemExit('Incomplete evaluation')
if not summary['expected_episodes'] == summary['recorded_episodes'] == len(expected):
    raise SystemExit('Episode counts differ from manifest')
if [r['seed'] for r in records] != expected:
    raise SystemExit('Seeds missing, reordered or substituted')
if not all(r['status'] in ('success', 'failure') and r['oracle_success'] for r in records):
    raise SystemExit('Episode error or failed oracle qualification')
print(f"COMPLETE: {summary['successes']}/{len(expected)} successes; failures retained")
PY
done <<< "$TASK_ROWS"
