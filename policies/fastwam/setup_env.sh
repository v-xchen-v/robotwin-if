#!/usr/bin/env bash
set -euo pipefail
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/../wam/setup_env.sh" fastwam "$@"
