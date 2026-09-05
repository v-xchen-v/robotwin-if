#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  scripts/generate_if_100_per_mode.sh OUTPUT_DIR [--resume|--overwrite]

Generates 100 oracle-qualified complete balance blocks for every maintained IF
task. Because each block contains every task mode exactly once, every mode gets
100 policy-evaluation episodes.

Optional environment variables:
  ROBOTWIN_CONDA_ENV             Conda environment (default: RoboTwin)
  IF_TASK_CONFIG                 RoboTwin task config (default: demo_clean)
  IF_MAX_CANDIDATE_BLOCKS        Per-task scan cap (default: 500)
  IF_CANDIDATE_FLOOR             First candidate seed floor (default: 100000)
  IF_ALLOW_COMPATIBLE_COMMIT=1   Pass the reviewed compatibility override
  ROBOTWIN_DIR                   Select an external RoboTwin checkout

Examples:
  scripts/generate_if_100_per_mode.sh outputs/if-seeds-v1
  scripts/generate_if_100_per_mode.sh outputs/if-seeds-v1 --resume
EOF
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage >&2
  exit 2
fi

OUTPUT_DIR="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve())' "$1")"
RUN_MODE="${2:-}"
case "$RUN_MODE" in
  "") MODE_ARGS=() ;;
  --resume|--overwrite) MODE_ARGS=("$RUN_MODE") ;;
  *)
    echo "error: second argument must be --resume or --overwrite" >&2
    usage >&2
    exit 2
    ;;
esac

CONDA_ENV="${ROBOTWIN_CONDA_ENV:-RoboTwin}"
TASK_CONFIG="${IF_TASK_CONFIG:-demo_clean}"
MAX_CANDIDATE_BLOCKS="${IF_MAX_CANDIDATE_BLOCKS:-500}"
CANDIDATE_FLOOR="${IF_CANDIDATE_FLOOR:-100000}"

if ! [[ "$MAX_CANDIDATE_BLOCKS" =~ ^[1-9][0-9]*$ ]]; then
  echo "error: IF_MAX_CANDIDATE_BLOCKS must be a positive integer" >&2
  exit 2
fi
if ! [[ "$CANDIDATE_FLOOR" =~ ^[0-9]+$ ]]; then
  echo "error: IF_CANDIDATE_FLOOR must be a non-negative integer" >&2
  exit 2
fi

COMPAT_ARGS=()
if [[ "${IF_ALLOW_COMPATIBLE_COMMIT:-0}" == "1" ]]; then
  COMPAT_ARGS=(--allow-compatible-commit)
elif [[ "${IF_ALLOW_COMPATIBLE_COMMIT:-0}" != "0" ]]; then
  echo "error: IF_ALLOW_COMPATIBLE_COMMIT must be 0 or 1" >&2
  exit 2
fi

mapfile -t TASKS < <(
  PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -c \
    'from if_benchmark.seed_contracts import IF_SEED_CONTRACTS; print(*IF_SEED_CONTRACTS, sep="\n")'
)
if [[ ${#TASKS[@]} -ne 7 ]]; then
  echo "error: expected exactly seven maintained IF tasks, got ${#TASKS[@]}" >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR"

bash "$REPO_ROOT/scripts/bridge_tasks.sh" --check "${COMPAT_ARGS[@]}"

printf 'Output: %s\n' "$OUTPUT_DIR"
printf 'Task config: %s\n' "$TASK_CONFIG"
printf 'Target: 100 accepted blocks = 100 episodes per mode\n'
printf 'Candidate cap: %s blocks per task\n\n' "$MAX_CANDIDATE_BLOCKS"

failed=()
for task in "${TASKS[@]}"; do
  echo "===== $task ====="
  if conda run --no-capture-output -n "$CONDA_ENV" \
    python "$REPO_ROOT/tools/generate_if_seed_manifest.py" \
    --task "$task" \
    --task-config "$TASK_CONFIG" \
    --accepted-blocks 100 \
    --max-candidate-blocks "$MAX_CANDIDATE_BLOCKS" \
    --candidate-floor "$CANDIDATE_FLOOR" \
    --output-dir "$OUTPUT_DIR" \
    "${COMPAT_ARGS[@]}" \
    "${MODE_ARGS[@]}"; then
    if ! python3 "$REPO_ROOT/tools/validate_if_seed_manifest.py" \
      --require-evidence "$OUTPUT_DIR/$task.json"; then
      failed+=("$task:validation")
    fi
  else
    failed+=("$task:generation")
  fi
  echo
done

if [[ ${#failed[@]} -ne 0 ]]; then
  printf 'FAILED: %s\n' "${failed[*]}" >&2
  echo "Checkpoints remain in $OUTPUT_DIR." >&2
  echo "Use --resume only for an interrupted run with identical parameters/provenance." >&2
  echo "For bounded exhaustion, choose a new output directory or deliberately restart with a larger cap and --overwrite." >&2
  exit 1
fi

echo "All seven manifests generated and independently validated: $OUTPUT_DIR"
