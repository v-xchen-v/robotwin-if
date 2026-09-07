#!/usr/bin/env bash
set -euo pipefail
POLICY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$POLICY_DIR/../.." && pwd -P)"
HYVLA_ENV_PREFIX="/Data/robotwin-if/envs/robotwin-if-hy-vla"
HYVLA_SOURCE_DIR="$REPO_ROOT/third_party/hy-vla"
HYVLA_REVISION="af57e7507ec5964b52fdf6296741e553cbcd3288"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --env-prefix|--source-dir)
            [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || { echo "$1 requires a value" >&2; exit 1; }
            if [[ "$1" == --env-prefix ]]; then HYVLA_ENV_PREFIX="$2"; else HYVLA_SOURCE_DIR="$2"; fi
            shift 2 ;;
        -h|--help) echo 'Usage: bash policies/hy_vla/setup_env.sh [--env-prefix PATH] [--source-dir PATH]'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done
HYVLA_ENV_PREFIX="$(realpath -m -- "$HYVLA_ENV_PREFIX")"
HYVLA_SOURCE_DIR="$(realpath -m -- "$HYVLA_SOURCE_DIR")"
[[ "$(basename -- "$HYVLA_ENV_PREFIX")" == robotwin-if-hy-vla* ]] || { echo 'Use a dedicated robotwin-if-hy-vla environment prefix' >&2; exit 1; }
if [[ ! -e "$HYVLA_SOURCE_DIR" ]]; then
    git init "$HYVLA_SOURCE_DIR"
    git -C "$HYVLA_SOURCE_DIR" remote add origin https://github.com/Tencent-Hunyuan/Hy-Embodied-0.5-VLA.git
    git -C "$HYVLA_SOURCE_DIR" fetch --depth 1 origin "$HYVLA_REVISION"
    git -C "$HYVLA_SOURCE_DIR" checkout --detach FETCH_HEAD
fi
[[ "$(git -C "$HYVLA_SOURCE_DIR" rev-parse --show-toplevel)" == "$HYVLA_SOURCE_DIR" ]]
[[ "$(git -C "$HYVLA_SOURCE_DIR" rev-parse HEAD)" == "$HYVLA_REVISION" ]]
python3 "$POLICY_DIR/patch_source.py" "$HYVLA_SOURCE_DIR"
export PYTHONNOUSERSITE=1
export CONDA_PKGS_DIRS="${CONDA_PKGS_DIRS:-$(dirname -- "$HYVLA_ENV_PREFIX")/conda-pkgs}"
export TMPDIR="${TMPDIR:-$(dirname -- "$HYVLA_ENV_PREFIX")/tmp}"
mkdir -p "$CONDA_PKGS_DIRS" "$TMPDIR"
if [[ ! -e "$HYVLA_ENV_PREFIX" ]]; then
    conda create --yes --prefix "$HYVLA_ENV_PREFIX" python=3.10 pip
fi
conda run --no-capture-output -p "$HYVLA_ENV_PREFIX" python -c 'import sys; assert sys.version_info[:2] == (3, 10)'
conda run --no-capture-output -p "$HYVLA_ENV_PREFIX" python -m pip install --no-cache-dir torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128
conda run --no-capture-output -p "$HYVLA_ENV_PREFIX" python -m pip install --no-cache-dir -r "$POLICY_DIR/requirements.txt"
# Source is imported directly: its full package dependencies include training/UI tools.
conda run --no-capture-output -p "$HYVLA_ENV_PREFIX" python -m pip check
conda run --no-capture-output -p "$HYVLA_ENV_PREFIX" python "$POLICY_DIR/check_env.py" --source-dir "$HYVLA_SOURCE_DIR"
