#!/bin/bash
set -euo pipefail

##############################################
# Bridge robotwin-if task files into the RoboTwin submodule.
#
# We keep our task files under tasks/ in this repo and symlink them into the
# submodule at the 3 name-aligned injection points RoboTwin discovers by
# `task_name` (see docs/design.md):
#   1. tasks/envs/<task>.py               -> third_party/robotwin/envs/
#   2. tasks/task_instruction/<task>.json -> third_party/robotwin/description/task_instruction/
#   3. tasks/objects_description/<dir>/   -> third_party/robotwin/description/objects_description/
#
# Idempotent: re-running just refreshes the symlinks (ln -srf).
##############################################

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
RT="$REPO_ROOT/third_party/robotwin"

if [ ! -d "$RT" ] || [ -z "$(ls -A "$RT" 2>/dev/null)" ]; then
    echo "Error: RoboTwin submodule not populated at $RT. Run setup_robotwin.sh first." >&2
    exit 1
fi

link_glob() {
    # $1 src dir, $2 dst dir, $3 glob pattern
    local src_dir="$1" dst_dir="$2" pattern="$3"
    [ -d "$src_dir" ] || return 0
    mkdir -p "$dst_dir"
    shopt -s nullglob
    local f
    for f in "$src_dir"/$pattern; do
        ln -srf "$f" "$dst_dir/$(basename "$f")"
        echo "  linked $(basename "$f") -> ${dst_dir#$REPO_ROOT/}"
    done
}

echo "Bridging robotwin-if tasks into submodule..."
link_glob "$REPO_ROOT/tasks/envs"                "$RT/envs"                              "*.py"
link_glob "$REPO_ROOT/tasks/task_instruction"    "$RT/description/task_instruction"      "*.json"
link_glob "$REPO_ROOT/tasks/objects_description" "$RT/description/objects_description"    "*"
echo "Done."
