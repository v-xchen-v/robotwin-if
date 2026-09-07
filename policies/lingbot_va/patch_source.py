"""Make upstream FlashAttention optional for its supported Torch SDPA backend.

Only the pinned file or this exact patched version is accepted. No model math,
weights, input preprocessing, normalization, or cache behavior is changed.
"""

import argparse
from pathlib import Path
import subprocess

REVISION = "7c6ffa9bfc4b83582cafc860fab4c82cc7deeeeb"
FILE = "wan_va/modules/model.py"
BEFORE = """try:
    from flash_attn_interface import flash_attn_func
except:
    from flash_attn import flash_attn_func
"""
AFTER = """try:
    from flash_attn_interface import flash_attn_func
except ImportError:
    try:
        from flash_attn import flash_attn_func
    except ImportError:
        def flash_attn_func(*args, **kwargs):
            raise RuntimeError("FlashAttention is not installed; use attn_mode='torch'")
"""


def patch_source(source):
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise ValueError(f"Expected source revision {REVISION}, found {revision}")
    original = subprocess.check_output(["git", "-C", str(source), "show", f"HEAD:{FILE}"], text=True)
    if original.count(BEFORE) != 1:
        raise ValueError("Pinned source import block does not match")
    patched = original.replace(BEFORE, AFTER)
    current = (source / FILE).read_text()
    changed = subprocess.check_output(["git", "-C", str(source), "diff", "--name-only", "HEAD"], text=True).splitlines()
    if current not in (original, patched) or any(name != FILE for name in changed):
        raise ValueError("Source contains other tracked edits; choose a separate --source-dir")
    if current != patched:
        (source / FILE).write_text(patched)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    patch_source(parser.parse_args().source.resolve())
