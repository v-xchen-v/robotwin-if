#!/bin/bash
set -euo pipefail

##############################################
# Un-bridge: remove the symlinks that bridge_tasks.sh injected into the RoboTwin
# submodule, restoring it to a pristine (submodule-only) state.
#
# Mirrors bridge_tasks.sh's 3 injection points:
#   1. third_party/robotwin/envs/<task>.py
#   2. third_party/robotwin/description/task_instruction/<task>.json
#   3. third_party/robotwin/description/objects_description/<dir>/
#
# SAFETY: only removes an entry if it is a SYMLINK whose target resolves to our
# source file under tasks/. Native regular files/dirs are never touched. Idempotent.
#
# Use when detaching our task files from the submodule — e.g. before mounting
# robotwin-if itself as a submodule elsewhere, or to get a clean `git status` in
# third_party/robotwin.
##############################################

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RT="$REPO_ROOT/third_party/robotwin"

if [ ! -d "$RT" ] || [ -z "$(ls -A "$RT" 2>/dev/null)" ]; then
    echo "RoboTwin submodule not populated at $RT — nothing to unbridge."
    exit 0
fi

removed=0
skipped=0

unlink_glob() {
    # $1 src dir, $2 dst dir, $3 glob pattern
    local src_dir="$1" dst_dir="$2" pattern="$3"
    [ -d "$src_dir" ] || return 0
    [ -d "$dst_dir" ] || return 0
    shopt -s nullglob
    local f dst
    for f in "$src_dir"/$pattern; do
        dst="$dst_dir/$(basename "$f")"
        if [ -L "$dst" ] && [ "$(readlink -f "$dst")" = "$(readlink -f "$f")" ]; then
            rm -f "$dst"
            echo "  unlinked $(basename "$f") <- ${dst_dir#$REPO_ROOT/}"
            removed=$((removed + 1))
        elif [ -e "$dst" ] && [ ! -L "$dst" ]; then
            echo "  SKIP $(basename "$f"): ${dst#$REPO_ROOT/} is a real file, not our symlink" >&2
            skipped=$((skipped + 1))
        fi
    done
}

echo "Un-bridging robotwin-if tasks from submodule..."
unlink_glob "$REPO_ROOT/tasks/envs"                "$RT/envs"                            "*.py"
unlink_glob "$REPO_ROOT/tasks/task_instruction"    "$RT/description/task_instruction"    "*.json"
unlink_glob "$REPO_ROOT/tasks/objects_description" "$RT/description/objects_description"  "*"
echo "Done. removed=$removed skipped=$skipped"
