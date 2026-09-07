"""Pin VLAct and select SDPA / explicit framework imports for inference."""

import argparse
from pathlib import Path
import subprocess

REVISION = "621b01bb830e1a400f12f4c05262add55ae3003a"


def patch_source(source):
    source = Path(source).resolve()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args], text=True)

    if git("rev-parse", "HEAD").strip() != REVISION:
        raise ValueError(f"VLAct source must be pinned to {REVISION}")
    files = ["starVLA/model/modules/vlm/QWen3.py", "starVLA/model/framework/__init__.py",
             "starVLA/model/framework/QwenOFT.py"]
    changed = set(git("diff", "HEAD", "--name-only").splitlines())
    if changed - set(files):
        raise ValueError(f"Unexpected tracked source changes: {changed - set(files)}")
    pending = []
    for name in files:
        original = git("show", f"HEAD:{name}")
        if name.endswith("QWen3.py"):
            if original.count('attn_implementation="flash_attention_2"') != 1:
                raise ValueError("Unexpected Qwen attention constructor")
            patched = original.replace('attn_implementation="flash_attention_2"', 'attn_implementation="sdpa"')
        elif name.endswith("QwenOFT.py"):
            # The official launcher selects BF16; NumPy cannot represent BF16.
            old = "pred_actions.detach().cpu().numpy()"
            if original.count(old) != 1:
                raise ValueError("Unexpected OFT output conversion")
            patched = original.replace(old, "pred_actions.detach().float().cpu().numpy()")
        else:
            start = original.index("# Auto-import all framework submodules")
            end = original.index("def build_framework", start)
            patched = original[:start] + "# Inference: the factory explicitly imports QwenOFT on demand.\n" + original[end:]
        path = source / name
        if path.read_text() not in (original, patched):
            raise ValueError(f"Unexpected edits in {path}")
        pending.append((path, patched))
    for path, patched in pending:
        path.write_text(patched)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    patch_source(parser.parse_args().source)
