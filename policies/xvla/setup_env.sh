#!/usr/bin/env bash
set -euo pipefail

POLICY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$POLICY_DIR/../.." && pwd -P)"
XVLA_ENV_NAME="robotwin-if-xvla"
XVLA_SOURCE_DIR="$REPO_ROOT/third_party/xvla"
XVLA_REVISION="6bc2513f5f1cbec715cc668b414392a6cae5c671"
XVLA_REPOSITORY="https://github.com/2toinf/X-VLA.git"

usage() {
    cat <<'EOF'
Usage: bash policies/xvla/setup_env.sh [options]

Create/reuse a dedicated Python 3.10 Conda environment, fetch pinned X-VLA
source, install CUDA 12.1 inference dependencies, and check imports.

Options:
  --env-name NAME    Conda environment name (default: robotwin-if-xvla)
  --source-dir PATH  X-VLA checkout (default: <repo>/third_party/xvla)
  -h, --help        Show this help

Existing source must be at the pinned revision with no tracked changes.
Reusing an environment reinstalls the declared dependency versions.
This script does not download weights, launch a server, or run RoboTwin.
EOF
}

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --env-name|--source-dir)
            [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || fail "$1 requires a value"
            if [[ "$1" == --env-name ]]; then
                XVLA_ENV_NAME="$2"
            else
                XVLA_SOURCE_DIR="$2"
            fi
            shift 2
            ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown option: $1 (use --help)" ;;
    esac
done

[[ "$XVLA_ENV_NAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || fail "Use a Conda environment name, not a path"
case "${XVLA_ENV_NAME,,}" in
    base|root|robotwin) fail "Use a dedicated inference environment, not $XVLA_ENV_NAME" ;;
esac

for executable in conda git python3; do
    command -v "$executable" >/dev/null || fail "$executable is required on PATH"
done

XVLA_SOURCE_DIR="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$XVLA_SOURCE_DIR")"

# Preflight an existing checkout before changing any environment or source.
if [[ -e "$XVLA_SOURCE_DIR" ]]; then
    source_root="$(git -C "$XVLA_SOURCE_DIR" rev-parse --show-toplevel)" || fail "Source directory is not a Git checkout"
    [[ "$source_root" == "$XVLA_SOURCE_DIR" ]] || fail "Source directory must be the root of its own checkout"
    source_revision="$(git -C "$XVLA_SOURCE_DIR" rev-parse HEAD)"
    [[ "$source_revision" == "$XVLA_REVISION" ]] || fail "Existing source is not at $XVLA_REVISION; use another --source-dir"
    git -C "$XVLA_SOURCE_DIR" diff --quiet HEAD -- || fail "Existing X-VLA source has tracked changes"
fi

env_prefix="$(conda env list --json | python3 -c '
import json, pathlib, sys
matches = [p for p in json.load(sys.stdin)["envs"] if pathlib.Path(p).name == sys.argv[1]]
if len(matches) > 1:
    raise SystemExit("Multiple Conda environments match this name; choose a unique --env-name")
print(matches[0] if matches else "")
' "$XVLA_ENV_NAME")"

if [[ -n "$env_prefix" ]]; then
    printf 'Reusing Conda environment: %s\n' "$env_prefix"
    conda run --no-capture-output -n "$XVLA_ENV_NAME" python -c '
import sys
if sys.version_info[:2] != (3, 10):
    raise SystemExit("Existing environment must use Python 3.10; choose another --env-name")
'
else
    conda create --yes --name "$XVLA_ENV_NAME" python=3.10 pip
fi

if [[ ! -e "$XVLA_SOURCE_DIR" ]]; then
    mkdir -p -- "$(dirname -- "$XVLA_SOURCE_DIR")"
    git init "$XVLA_SOURCE_DIR"
    git -C "$XVLA_SOURCE_DIR" remote add origin "$XVLA_REPOSITORY"
    git -C "$XVLA_SOURCE_DIR" fetch --depth 1 origin "$XVLA_REVISION"
    git -C "$XVLA_SOURCE_DIR" checkout --detach FETCH_HEAD
fi

# Avoid importing packages from the user's site-packages into this environment.
export PYTHONNOUSERSITE=1
conda run --no-capture-output -n "$XVLA_ENV_NAME" python -m pip install -r "$POLICY_DIR/requirements.txt"
conda run --no-capture-output -n "$XVLA_ENV_NAME" python -m pip check

(
    cd -- "$XVLA_SOURCE_DIR"
    conda run --no-capture-output -n "$XVLA_ENV_NAME" python -c '
import cv2, json_numpy, torch, torchvision, transformers
from models.modeling_xvla import XVLA
from models.processing_xvla import XVLAProcessor
from models.action_hub import build_action_space
assert build_action_space("ee6d").dim_action == 20
print("X-VLA inference imports passed.")
print(f"torch={torch.__version__}; CUDA build={torch.version.cuda}; GPU available={torch.cuda.is_available()}")
'
)

printf '\nEnvironment setup complete. Source revision: %s\n' "$XVLA_REVISION"
printf 'To launch the checkpoint server:\n  conda activate %q\n  cd %q\n' "$XVLA_ENV_NAME" "$XVLA_SOURCE_DIR"
printf '  python -m deploy --model_path 2toINF/X-VLA-RoboTwin2 --host 127.0.0.1 --port 8010 --disable_slurm --output_dir ./logs/run-001\n'
printf 'Use a new --output_dir for each server launch.\n'
