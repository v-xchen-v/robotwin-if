#!/usr/bin/env bash
set -euo pipefail

POLICY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$POLICY_DIR/../.." && pwd -P)"
VLACT_ENV_NAME="robotwin-if-vlact"
VLACT_SOURCE_DIR="$REPO_ROOT/third_party/vlact"
VLACT_REVISION="621b01bb830e1a400f12f4c05262add55ae3003a"

usage() {
    cat <<'EOF'
Usage: bash policies/vlact/setup_env.sh [--env-name NAME] [--source-dir PATH]

Create/reuse a dedicated Python 3.10 environment, fetch pinned official source,
enable its Torch attention backend without requiring FlashAttention, install
CUDA 12.4 inference dependencies and check imports. No weights are downloaded.
The existing RoboTwin and other model environments are not modified.
EOF
}
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
while [[ $# -gt 0 ]]; do
    case "$1" in
        --env-name|--source-dir)
            [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || fail "$1 requires a value"
            if [[ "$1" == --env-name ]]; then VLACT_ENV_NAME="$2"; else VLACT_SOURCE_DIR="$2"; fi
            shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown option: $1" ;;
    esac
done
[[ "$VLACT_ENV_NAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || fail "Use an environment name, not a path"
case "${VLACT_ENV_NAME,,}" in
    base|root|robotwin|xvla|robotwin-if-xvla|robotwin-if-lingbot-va|robotwin-if-lingbot-vla) fail "Use a dedicated VLAct environment" ;;
esac
for executable in conda git python3; do command -v "$executable" >/dev/null || fail "$executable is required"; done
VLACT_SOURCE_DIR="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$VLACT_SOURCE_DIR")"

if [[ ! -e "$VLACT_SOURCE_DIR" ]]; then
    mkdir -p -- "$(dirname -- "$VLACT_SOURCE_DIR")"
    git init "$VLACT_SOURCE_DIR"
    git -C "$VLACT_SOURCE_DIR" remote add origin https://github.com/starVLA/VLAct.git
    git -C "$VLACT_SOURCE_DIR" fetch --depth 1 origin "$VLACT_REVISION"
    git -C "$VLACT_SOURCE_DIR" checkout --detach FETCH_HEAD
fi
[[ "$(git -C "$VLACT_SOURCE_DIR" rev-parse --show-toplevel)" == "$VLACT_SOURCE_DIR" ]] || fail "Source must be its own checkout"
python3 "$POLICY_DIR/patch_source.py" "$VLACT_SOURCE_DIR"

env_prefix="$(conda env list --json | python3 -c '
import json, pathlib, sys
matches = [p for p in json.load(sys.stdin)["envs"] if pathlib.Path(p).name == sys.argv[1]]
if len(matches) > 1: raise SystemExit("Ambiguous environment name")
print(matches[0] if matches else "")
' "$VLACT_ENV_NAME")"
if [[ -n "$env_prefix" ]]; then
    conda run --no-capture-output -n "$VLACT_ENV_NAME" python -c 'import sys; assert sys.version_info[:2] == (3, 10), "Python 3.10 required"'
else
    conda create --yes --name "$VLACT_ENV_NAME" python=3.10 pip
fi
export PYTHONNOUSERSITE=1
conda run --no-capture-output -n "$VLACT_ENV_NAME" python -m pip install --no-cache-dir -r "$POLICY_DIR/requirements.txt"
conda run --no-capture-output -n "$VLACT_ENV_NAME" python -m pip check
conda run --no-capture-output -n "$VLACT_ENV_NAME" python "$POLICY_DIR/check_env.py" --source-dir "$VLACT_SOURCE_DIR"
printf '\nVLAct environment ready: %s\nSource: %s\n' "$VLACT_ENV_NAME" "$VLACT_SOURCE_DIR"
