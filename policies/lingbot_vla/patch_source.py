"""Use upstream's Torch eager vision backend instead of hardcoded FlashAttention."""

from pathlib import Path
import subprocess
import sys

REVISION = "4eb34b7693a0565c67433f8fac9c59a2e67eb60b"
MODEL = "lingbotvla/models/vla/pi0/modeling_lingbot_vla.py"
VISION = "lingbotvla/models/vla/pi0/qwenvl_in_vla.py"


def patch_source(source):
    source = Path(source).resolve()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()
    if git("rev-parse", "--show-toplevel") != str(source) or git("rev-parse", "HEAD") != REVISION:
        raise ValueError(f"Expected a standalone checkout at {REVISION}")
    replacements = {MODEL: {
        "vlm_config._attn_implementation = 'flash_attention_2'": "vlm_config._attn_implementation = 'eager'",
        "self.config.qwen_expert_config._attn_implementation = 'flash_attention_2'":
            "self.config.qwen_expert_config._attn_implementation = 'eager'",
        "._from_config(vlm_config, use_flash_attention_2=True)": "._from_config(vlm_config)",
        "._from_config(self.config.qwen_expert_config, use_flash_attention_2=True, eval=eval)":
            "._from_config(self.config.qwen_expert_config, eval=eval)",
    }, VISION: {
        "from transformers.processing_utils import Unpack":
            "from transformers.processing_utils import Unpack\n"
            "from transformers.models.qwen2_5_vl.modeling_qwen2_5_vl import rotate_half",
        "._from_config(config.vision_config, use_flash_attention_2=True)":
            "._from_config(config.vision_config, attn_implementation='eager')",
    }}
    if set(git("diff", "HEAD", "--name-only").splitlines()) - replacements.keys():
        raise ValueError("Refusing unrelated tracked source changes")
    changes = {}
    for filename, edits in replacements.items():
        original = subprocess.check_output(["git", "-C", str(source), "show", f"HEAD:{filename}"], text=True)
        patched = original
        for old, new in edits.items():
            if patched.count(old) != 1:
                raise ValueError(f"Upstream patch context changed: {old}")
            patched = patched.replace(old, new)
        target = source / filename
        if target.read_text() not in (original, patched):
            raise ValueError(f"Refusing unexpected changes in {filename}")
        if target.read_text() != patched:
            changes[target] = patched
    for target, patched in changes.items():
        target.write_text(patched)
    print(f"Pinned LingBot-VLA source ready: {source}")


if __name__ == "__main__":
    patch_source(sys.argv[1])
