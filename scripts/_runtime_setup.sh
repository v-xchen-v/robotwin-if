# Source-checkout helpers for setup_robotwin.sh; no environment installation here.

runtime_fail() { printf 'error: %s\n' "$*" >&2; return 1; }

load_runtime_pins() {
    local values
    local -a revisions
    values=$(python3 - "$1/scripts/runtime_pins.json" <<'PY'
import json, re, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    pins = json.load(stream)
for name in ("robotwin", "curobo"):
    value = pins[name]
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise SystemExit(f"Invalid {name} commit in {sys.argv[1]}")
    print(value)
PY
    ) || return
    mapfile -t revisions <<< "$values"
    ROBOTWIN_REVISION=${revisions[0]}
    CUROBO_REVISION=${revisions[1]}
}

check_checkout_revision() {
    local directory=$1 revision=$2 name=$3 actual_root expected_root actual_revision
    expected_root=$(cd -- "$directory" && pwd -P) || return
    actual_root=$(git -C "$directory" rev-parse --show-toplevel 2>/dev/null) || {
        runtime_fail "$name directory is not a Git checkout: $directory"; return 1;
    }
    [[ "$actual_root" == "$expected_root" ]] || {
        runtime_fail "$name directory belongs to another Git checkout: $directory"; return 1;
    }
    actual_revision=$(git -C "$directory" rev-parse HEAD) || return
    [[ "$actual_revision" == "$revision" ]] || {
        runtime_fail "$name revision is $actual_revision; expected $revision. Existing files were preserved. Align this checkout explicitly before rerunning setup."; return 1;
    }
}

ensure_robotwin_source() {
    local root=$1 revision=$2 directory="$1/third_party/robotwin" recorded
    recorded=$(git -C "$root" ls-files --stage -- third_party/robotwin | awk '$1 == "160000" && $3 == "0" {print $2}')
    [[ "$recorded" == "$revision" ]] || {
        runtime_fail "RoboTwin submodule gitlink ($recorded) differs from runtime_pins.json ($revision). Fix the version definitions before installing."; return 1;
    }
    # Init a missing submodule; never force an existing checkout to another revision.
    if [[ ! -e "$directory/.git" ]]; then
        git -C "$root" submodule update --init -- third_party/robotwin || return
    fi
    check_checkout_revision "$directory" "$revision" RoboTwin || return
    printf 'Using RoboTwin %s at %s\n' "$revision" "$directory"
}

ensure_curobo_source() {
    local directory=$1 repository=$2 revision=$3
    if [[ -e "$directory" || -L "$directory" ]]; then
        check_checkout_revision "$directory" "$revision" CuRobo || return
        git -C "$directory" diff --quiet HEAD -- || {
            runtime_fail "CuRobo has uncommitted source changes: $directory. Existing files were preserved."; return 1;
        }
        printf 'Reusing CuRobo %s at %s\n' "$revision" "$directory"
        return
    fi
    # Fetch into a sibling directory, so a failed/interrupted download leaves no
    # half-initialized CuRobo checkout at the final path.
    (
        local pending
        mkdir -p -- "$(dirname -- "$directory")" || exit
        pending=$(mktemp -d "${directory}.install-XXXXXX") || exit
        trap 'rm -rf -- "$pending"' EXIT
        git init -q "$pending" || exit
        git -C "$pending" remote add origin "$repository" || exit
        git -C "$pending" fetch --depth=1 origin "$revision" || exit
        git -C "$pending" checkout --detach FETCH_HEAD || exit
        [[ ! -e "$directory" && ! -L "$directory" ]] || {
            runtime_fail "CuRobo destination appeared during download: $directory"; exit 1;
        }
        mv -T -- "$pending" "$directory"
    )
}
