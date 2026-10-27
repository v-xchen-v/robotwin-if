#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROBOTWIN_DIR="$REPO_ROOT/third_party/robotwin"
source "$REPO_ROOT/scripts/_runtime_setup.sh"

usage() {
    cat <<'HELP'
Usage: bash setup_robotwin.sh [--assets-cache PATH] [--sources-only]

Prepare the pinned RoboTwin/CuRobo sources, then install the RoboTwin environment.
  --assets-cache PATH  Reuse an existing asset directory (--assets_cache also works)
  --sources-only       Prepare/check Git sources only; no apt, Conda, pip or assets
  -h, --help           Show this help

Versions come from scripts/runtime_pins.json and must match the submodule gitlink.
Existing source checkouts are never deleted or switched to another revision.
HELP
}

# Parse arguments
ASSETS_CACHE=""
SOURCES_ONLY=0
while [[ $# -gt 0 ]]; do
    case $1 in
        --assets_cache|--assets-cache)
            [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || { runtime_fail "$1 requires a path"; exit 2; }
            ASSETS_CACHE="$2"
            shift 2
            ;;
        --sources-only) SOURCES_ONLY=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *)
            runtime_fail "Unknown option: $1 (see --help)"
            exit 2
            ;;
    esac
done

echo "====== Setting up RoboTwin-2.0 Environment ======"

# Validate source revisions before changing system packages or Conda environments.
load_runtime_pins "$REPO_ROOT"
ensure_robotwin_source "$REPO_ROOT" "$ROBOTWIN_REVISION"
CUROBO_DIR="$ROBOTWIN_DIR/envs/curobo"
ensure_curobo_source "$CUROBO_DIR" https://github.com/NVlabs/curobo.git "$CUROBO_REVISION"
if (( SOURCES_ONLY )); then
    echo "Pinned source checkouts are ready."
    exit 0
fi

# 1. Install Vulkan dependencies (required for MuJoCo/SAPIEN rendering)
echo "Installing Vulkan and rendering dependencies..."
sudo apt-get update -qq && sudo apt-get install -y -qq \
    libvulkan1 mesa-vulkan-drivers vulkan-tools \
    libegl1-mesa-dev libgl1-mesa-dev libgles2-mesa-dev \
    libglfw3-dev libglew-dev \
    ffmpeg \
    unzip \
    2>/dev/null || echo "Warning: some system packages may need manual installation."

# 2. Create conda environment for RoboTwin
eval "$(conda shell.bash hook)"

if conda env list | grep -q "^RoboTwin "; then
    echo "Conda env 'RoboTwin' already exists, skipping creation."
else
    echo "Creating conda environment 'RoboTwin' with Python 3.10..."
    conda create -n RoboTwin python=3.10 -y
fi

conda activate RoboTwin

# 4. Install dependencies (manual steps instead of _install.sh to avoid
#    interactive prompts and pytorch3d build-from-source failures)
echo "Installing RoboTwin dependencies..."
cd "$ROBOTWIN_DIR"

# 4a. Install script/requirements.txt (includes torch, sapien, mplib, huggingface_hub, etc.)
if [ -f "script/requirements.txt" ]; then
    pip install -r script/requirements.txt
fi

# 4b. Install pytorch3d (optional, not needed for evaluation without 3D data)
#     Try prebuilt wheel from fbaipublicfiles first (fast), then build from source.
echo "Installing pytorch3d..."
PT3D_INSTALLED=false

# Try prebuilt wheel: auto-detect python/torch/cuda versions to construct URL
PT3D_VERSION_STR=$(python -c "
import sys, torch
pyt_ver = torch.__version__.split('+')[0].replace('.', '')
cuda_ver = torch.version.cuda.replace('.', '')
print(f'py3{sys.version_info.minor}_cu{cuda_ver}_pyt{pyt_ver}')
" 2>/dev/null || echo "")

if [ -n "$PT3D_VERSION_STR" ]; then
    PT3D_URL="https://dl.fbaipublicfiles.com/pytorch3d/packaging/wheels/${PT3D_VERSION_STR}/download.html"
    echo "Trying prebuilt wheel: $PT3D_URL"
    if pip install --no-index --no-cache-dir pytorch3d -f "$PT3D_URL" 2>&1; then
        echo "pytorch3d installed via prebuilt wheel."
        PT3D_INSTALLED=true
    fi
fi

# Fallback: build from source with --no-build-isolation (avoids missing torch in isolated env)
if [ "$PT3D_INSTALLED" = false ]; then
    echo "Prebuilt wheel not available, building from source..."
    if pip install "git+https://github.com/facebookresearch/pytorch3d.git@stable" --no-build-isolation 2>&1; then
        echo "pytorch3d installed from source."
        PT3D_INSTALLED=true
    fi
fi

if [ "$PT3D_INSTALLED" = false ]; then
    echo "Warning: pytorch3d install failed (optional for evaluation, will not affect core functionality)."
fi

# 4c. Patch SAPIEN urdf_loader.py to add encoding="utf-8" (same as _install.sh)
echo "Patching SAPIEN urdf_loader..."
SAPIEN_LOCATION=$(pip show sapien 2>/dev/null | grep 'Location' | awk '{print $2}')
if [ -n "$SAPIEN_LOCATION" ] && [ -f "$SAPIEN_LOCATION/sapien/wrapper/urdf_loader.py" ]; then
    URDF_LOADER="$SAPIEN_LOCATION/sapien/wrapper/urdf_loader.py"
    sed -i -E 's/("r")(\))( as)/\1, encoding="utf-8") as/g' "$URDF_LOADER"
    echo "SAPIEN urdf_loader patched."
else
    echo "SAPIEN not found or urdf_loader.py missing, skipping patch."
fi

# 4d. Patch mplib planner.py (remove collision check in screw plan, same as _install.sh)
echo "Patching mplib planner..."
MPLIB_LOCATION=$(pip show mplib 2>/dev/null | grep 'Location' | awk '{print $2}')
if [ -n "$MPLIB_LOCATION" ] && [ -f "$MPLIB_LOCATION/mplib/planner.py" ]; then
    PLANNER="$MPLIB_LOCATION/mplib/planner.py"
    sed -i -E 's/(if np.linalg.norm\(delta_twist\) < 1e-4 )(or collide )(or not within_joint_limit:)/\1\3/g' "$PLANNER"
    echo "mplib patched successfully."
else
    echo "mplib not found, skipping patch."
fi

# 4e. Install the checked CuRobo source into this environment.
echo "Setting up CuRobo..."
pip install -e "$CUROBO_DIR" --no-build-isolation

cd "$ROBOTWIN_DIR"

# 5. Download assets (objects, textures, embodiments)
#    Run _download.py and unzip manually instead of _download_assets.sh
#    to avoid the interactive prompt in update_embodiment_config_path.py
echo "Downloading RoboTwin assets..."
cd "$ROBOTWIN_DIR"
if [ -n "$ASSETS_CACHE" ] && [ -d "$ASSETS_CACHE" ] && [ -n "$(ls -A "$ASSETS_CACHE" 2>/dev/null)" ]; then
    echo "Using cached assets from: $ASSETS_CACHE"
    # Only remove if it's already a symlink or doesn't exist; refuse to delete a real directory
    if [ -L "$ROBOTWIN_DIR/assets" ]; then
        rm -f "$ROBOTWIN_DIR/assets"
    elif [ -d "$ROBOTWIN_DIR/assets" ]; then
        echo "Warning: $ROBOTWIN_DIR/assets is a real directory, renaming to assets.bak"
        mv "$ROBOTWIN_DIR/assets" "$ROBOTWIN_DIR/assets.bak.$(date +%s)"
    fi
    ln -sf "$ASSETS_CACHE" "$ROBOTWIN_DIR/assets"
    echo "Symlinked assets -> $ASSETS_CACHE"
else
    echo "Downloading RoboTwin assets..."
    if [ -d "assets" ]; then
        cd assets
        if [ -f "_download.py" ]; then
            python _download.py || echo "Warning: asset download may have failed."
        fi
        # Unzip assets if zip files exist
        for zipfile in background_texture.zip embodiments.zip objects.zip; do
            if [ -f "$zipfile" ]; then
                unzip -o "$zipfile" && rm -f "$zipfile"
            fi
        done
        cd "$ROBOTWIN_DIR"
    fi
fi

# 6. Configure embodiment paths (non-interactive)
#    update_embodiment_config_path.py auto-detects assets/ when cwd is RoboTwin root
echo "Configuring embodiment paths..."
cd "$ROBOTWIN_DIR"
if [ -d "assets/embodiments" ] && [ -f "script/update_embodiment_config_path.py" ]; then
    python script/update_embodiment_config_path.py < /dev/null || {
        # If auto-detection fails, manually set ASSETS_PATH and run template replacement
        echo "Auto-detection failed, running manual template replacement..."
        ASSETS_PATH="$ROBOTWIN_DIR/assets"
        export ASSETS_PATH
        python -c "
import glob, os
assets_path = os.environ['ASSETS_PATH']
templates = glob.glob(os.path.join(assets_path, 'embodiments', '**', '*_tmp.yml'), recursive=True)
for tmpl in templates:
    with open(tmpl, 'r') as f:
        content = f.read()
    content = content.replace('\${ASSETS_PATH}', assets_path).replace('\$ASSETS_PATH', assets_path)
    out_path = tmpl.replace('_tmp.yml', '.yml')
    with open(out_path, 'w') as f:
        f.write(content)
print(f'Processed {len(templates)} template files with ASSETS_PATH={assets_path}')
"
    }
else
    echo "Warning: assets/embodiments not found, skipping path configuration."
fi

# 7. Install additional dependencies needed by client_robotwin.py
pip install json_numpy requests imageio scipy pyyaml opencv-python tqdm matplotlib
pip install einops flask omegaconf pillow 
pip install transformers
pip install timm
pip install peft

pip install warp-lang==1.12.1

pip install --force-reinstall "setuptools<70"

echo "====== RoboTwin-2.0 Environment Setup Complete ======"
echo "RoboTwin installed at: $ROBOTWIN_DIR"
echo "-----------------------"
ls $ROBOTWIN_DIR
ls $ROBOTWIN_DIR/assets
echo "-----------------------"
