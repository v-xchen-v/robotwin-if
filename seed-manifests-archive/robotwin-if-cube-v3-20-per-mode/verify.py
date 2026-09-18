from pathlib import Path
import sys
ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'if_benchmark').is_dir())
sys.path.insert(0, str(ROOT))
from tools.release_arm_select_cube_v3 import verify
verify(Path(__file__).resolve().parent)
