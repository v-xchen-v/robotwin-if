#!/usr/bin/env bash
set -euo pipefail
POLICY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$POLICY_DIR/../.." && pwd -P)"
DM05_ENV_PREFIX="/Data/robotwin-if/envs/robotwin-if-dm05"
DM05_SOURCE_DIR="$REPO_ROOT/third_party/opendm"
DM05_REVISION="c4762fed95e430bf14e86beed73166b8dd18b094"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --env-prefix|--source-dir)
            [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || { echo "$1 requires a value" >&2; exit 1; }
            if [[ "$1" == --env-prefix ]]; then DM05_ENV_PREFIX="$2"; else DM05_SOURCE_DIR="$2"; fi
            shift 2 ;;
        -h|--help) echo 'Usage: bash policies/dm05/setup_env.sh [--env-prefix PATH] [--source-dir PATH]'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done
DM05_ENV_PREFIX="$(realpath -m -- "$DM05_ENV_PREFIX")"
DM05_SOURCE_DIR="$(realpath -m -- "$DM05_SOURCE_DIR")"
[[ "$(basename -- "$DM05_ENV_PREFIX")" == robotwin-if-dm05* ]] || { echo 'Use a dedicated robotwin-if-dm05 environment prefix' >&2; exit 1; }
if [[ ! -e "$DM05_SOURCE_DIR" ]]; then
    git init "$DM05_SOURCE_DIR"
    git -C "$DM05_SOURCE_DIR" remote add origin https://github.com/dexmal/opendm.git
    git -C "$DM05_SOURCE_DIR" fetch --depth 1 origin "$DM05_REVISION"
    git -C "$DM05_SOURCE_DIR" checkout --detach FETCH_HEAD
fi
[[ "$(git -C "$DM05_SOURCE_DIR" rev-parse --show-toplevel)" == "$DM05_SOURCE_DIR" ]]
[[ "$(git -C "$DM05_SOURCE_DIR" rev-parse HEAD)" == "$DM05_REVISION" ]]
[[ -z "$(git -C "$DM05_SOURCE_DIR" status --porcelain --untracked-files=no)" ]]
export PYTHONNOUSERSITE=1
export CONDA_PKGS_DIRS="${CONDA_PKGS_DIRS:-$(dirname -- "$DM05_ENV_PREFIX")/conda-pkgs}"
export TMPDIR="${TMPDIR:-$(dirname -- "$DM05_ENV_PREFIX")/tmp}"
mkdir -p "$CONDA_PKGS_DIRS" "$TMPDIR"
if [[ ! -e "$DM05_ENV_PREFIX" ]]; then
    conda create --yes --prefix "$DM05_ENV_PREFIX" python=3.10 pip
fi
conda run --no-capture-output -p "$DM05_ENV_PREFIX" python -c 'import sys; assert sys.version_info[:2] == (3, 10)'
conda run --no-capture-output -p "$DM05_ENV_PREFIX" python -m pip install --no-cache-dir torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
conda run --no-capture-output -p "$DM05_ENV_PREFIX" python -m pip install --no-cache-dir -r "$POLICY_DIR/requirements.txt"
# Source is imported directly: its full package dependencies include training/UI tools.
conda run --no-capture-output -p "$DM05_ENV_PREFIX" python -m pip check
conda run --no-capture-output -p "$DM05_ENV_PREFIX" python "$POLICY_DIR/check_env.py" --source-dir "$DM05_SOURCE_DIR"
