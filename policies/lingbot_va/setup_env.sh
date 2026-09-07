#!/usr/bin/env bash
set -euo pipefail

POLICY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$POLICY_DIR/../.." && pwd -P)"
LINGBOT_ENV_NAME="robotwin-if-lingbot-va"
LINGBOT_SOURCE_DIR="$REPO_ROOT/third_party/lingbot-va"
LINGBOT_REVISION="7c6ffa9bfc4b83582cafc860fab4c82cc7deeeeb"

usage() {
    cat <<'EOF'
Usage: bash policies/lingbot_va/setup_env.sh [--env-name NAME] [--source-dir PATH]

Create/reuse a dedicated Python 3.10 environment, fetch pinned official source,
enable its Torch attention backend without requiring FlashAttention, install
CUDA 12.6 inference dependencies and check imports. No weights are downloaded.
The existing RoboTwin and other model environments are not modified.
EOF
}
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
while [[ $# -gt 0 ]]; do
    case "$1" in
        --env-name|--source-dir)
            [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || fail "$1 requires a value"
            if [[ "$1" == --env-name ]]; then LINGBOT_ENV_NAME="$2"; else LINGBOT_SOURCE_DIR="$2"; fi
            shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown option: $1" ;;
    esac
done
[[ "$LINGBOT_ENV_NAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || fail "Use an environment name, not a path"
case "${LINGBOT_ENV_NAME,,}" in
    base|root|robotwin|xvla|robotwin-if-xvla) fail "Use a dedicated LingBot-VA environment" ;;
esac
for executable in conda git python3; do command -v "$executable" >/dev/null || fail "$executable is required"; done
LINGBOT_SOURCE_DIR="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$LINGBOT_SOURCE_DIR")"

if [[ ! -e "$LINGBOT_SOURCE_DIR" ]]; then
    mkdir -p -- "$(dirname -- "$LINGBOT_SOURCE_DIR")"
    git init "$LINGBOT_SOURCE_DIR"
    git -C "$LINGBOT_SOURCE_DIR" remote add origin https://github.com/Robbyant/lingbot-va.git
    git -C "$LINGBOT_SOURCE_DIR" fetch --depth 1 origin "$LINGBOT_REVISION"
    git -C "$LINGBOT_SOURCE_DIR" checkout --detach FETCH_HEAD
fi
[[ "$(git -C "$LINGBOT_SOURCE_DIR" rev-parse --show-toplevel)" == "$LINGBOT_SOURCE_DIR" ]] || fail "Source must be its own checkout"
python3 "$POLICY_DIR/patch_source.py" "$LINGBOT_SOURCE_DIR"

env_prefix="$(conda env list --json | python3 -c '
import json, pathlib, sys
matches = [p for p in json.load(sys.stdin)["envs"] if pathlib.Path(p).name == sys.argv[1]]
if len(matches) > 1: raise SystemExit("Ambiguous environment name")
print(matches[0] if matches else "")
' "$LINGBOT_ENV_NAME")"
if [[ -n "$env_prefix" ]]; then
    conda run --no-capture-output -n "$LINGBOT_ENV_NAME" python -c 'import sys; assert sys.version_info[:2] == (3, 10), "Python 3.10 required"'
else
    conda create --yes --name "$LINGBOT_ENV_NAME" python=3.10.16 pip
fi
export PYTHONNOUSERSITE=1
conda run --no-capture-output -n "$LINGBOT_ENV_NAME" python -m pip install --no-cache-dir -r "$POLICY_DIR/requirements.txt"
conda run --no-capture-output -n "$LINGBOT_ENV_NAME" python -m pip check
conda run --no-capture-output -n "$LINGBOT_ENV_NAME" python "$POLICY_DIR/check_env.py" --source-dir "$LINGBOT_SOURCE_DIR"
printf '\nLingBot-VA environment ready: %s\nSource: %s\n' "$LINGBOT_ENV_NAME" "$LINGBOT_SOURCE_DIR"
