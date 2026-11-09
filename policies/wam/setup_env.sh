#!/usr/bin/env bash
# Called by the model-specific setup scripts; no simulator packages are modified.
set -euo pipefail
WAM_POLICY=$1
shift
WAM_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
WAM_ENV_PREFIX="${ROBOTWIN_IF_HOME:-$HOME/.local/share/robotwin-if}/envs/robotwin-if-$WAM_POLICY"
WAM_SOURCE_DIR="$WAM_ROOT/third_party/$WAM_POLICY"
case "$WAM_POLICY" in
  fastwam) WAM_URL=https://github.com/yuantianyuan01/FastWAM.git; WAM_REVISION=7faa71108368fbb3b6885649f112af607427a2d4 ;;
  motus) WAM_URL=https://github.com/thu-ml/Motus.git; WAM_REVISION=88f6fe30c62af033874b0a2e48ad1cbdaf12cfdf ;;
  xwam) WAM_URL=https://github.com/sharinka0715/X-WAM.git; WAM_REVISION=72cfb86b33fc5060963ef63412f16439fcfa472f ;;
  *) exit 2 ;;
esac
while (($#)); do
  case "$1" in
    --env-prefix|--source-dir)
      [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || { echo "$1 requires a value" >&2; exit 2; }
      if [[ "$1" == --env-prefix ]]; then WAM_ENV_PREFIX=$2; else WAM_SOURCE_DIR=$2; fi
      shift 2 ;;
    -h|--help)
      echo "Usage: bash policies/$WAM_POLICY/setup_env.sh [--env-prefix PATH] [--source-dir PATH]"
      exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
WAM_ENV_PREFIX=$(realpath -m -- "$WAM_ENV_PREFIX")
WAM_SOURCE_DIR=$(realpath -m -- "$WAM_SOURCE_DIR")
[[ $(basename -- "$WAM_ENV_PREFIX") == "robotwin-if-$WAM_POLICY"* ]] || { echo 'Use a dedicated model environment' >&2; exit 2; }
if [[ ! -e "$WAM_SOURCE_DIR" ]]; then
  git init "$WAM_SOURCE_DIR"
  git -C "$WAM_SOURCE_DIR" remote add origin "$WAM_URL"
  git -C "$WAM_SOURCE_DIR" fetch --depth 1 origin "$WAM_REVISION"
  git -C "$WAM_SOURCE_DIR" checkout --detach FETCH_HEAD
fi
[[ $(git -C "$WAM_SOURCE_DIR" rev-parse --show-toplevel) == "$WAM_SOURCE_DIR" ]]
[[ $(git -C "$WAM_SOURCE_DIR" rev-parse HEAD) == "$WAM_REVISION" ]]
[[ -z $(git -C "$WAM_SOURCE_DIR" status --porcelain --untracked-files=no) ]]
export PYTHONNOUSERSITE=1
export CONDA_PKGS_DIRS="${CONDA_PKGS_DIRS:-$(dirname -- "$WAM_ENV_PREFIX")/conda-pkgs}"
export TMPDIR="${TMPDIR:-$(dirname -- "$WAM_ENV_PREFIX")/tmp}"
mkdir -p "$CONDA_PKGS_DIRS" "$TMPDIR"
if [[ ! -e "$WAM_ENV_PREFIX" ]]; then
  conda create --yes --prefix "$WAM_ENV_PREFIX" python=3.10 pip
fi
conda run --no-capture-output -p "$WAM_ENV_PREFIX" python -c 'import sys; assert sys.version_info[:2] == (3, 10)'
conda run --no-capture-output -p "$WAM_ENV_PREFIX" python -m pip install --no-cache-dir \
  torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128
conda run --no-capture-output -p "$WAM_ENV_PREFIX" python -m pip install --no-cache-dir \
  -r "$WAM_ROOT/policies/$WAM_POLICY/requirements.txt"
conda run --no-capture-output -p "$WAM_ENV_PREFIX" python -m pip check
PYTHONPATH="$WAM_ROOT${PYTHONPATH:+:$PYTHONPATH}" conda run --no-capture-output -p "$WAM_ENV_PREFIX" \
  python -m policies.wam.check_env --policy "$WAM_POLICY" --source-dir "$WAM_SOURCE_DIR"
printf '\nEnvironment ready: %s\nSource: %s\n' "$WAM_ENV_PREFIX" "$WAM_SOURCE_DIR"
