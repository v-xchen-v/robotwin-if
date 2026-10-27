#!/usr/bin/env bash
# Collect complete expert blocks for human review; no policy server required.
set -euo pipefail
REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export PYTHONUTF8=1 PYTHONNOUSERSITE=1
exec "${SIM_PYTHON:-python3}" "$REPO_ROOT/tools/collect_if_expert.py" "$@"
