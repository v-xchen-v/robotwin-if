"""Strictly load the released BF16 training structure, then transfer once to GPU."""
from pathlib import Path
import subprocess
import sys

REVISION = "af57e7507ec5964b52fdf6296741e553cbcd3288"
FILE = "robotwin_eval/policy_wrapper.py"
MODEL_FILE = "hy_vla/modeling_hy_vla.py"


def patch_source(source):
    source = Path(source).resolve()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()
    if git("rev-parse", "--show-toplevel") != str(source) or git("rev-parse", "HEAD") != REVISION:
        raise ValueError(f"Expected a standalone checkout at {REVISION}")
    if set(git("diff", "HEAD", "--name-only").splitlines()) - {FILE, MODEL_FILE}:
        raise ValueError("Refusing unrelated tracked source changes")
    original = subprocess.check_output(["git", "-C", str(source), "show", f"HEAD:{FILE}"], text=True)
    old = "ckpt_path, config=self.config, vlm_model_path=vlm_model_path,"
    new = "ckpt_path, config=self.config, vlm_model_path=vlm_model_path, strict=True,"
    if original.count(old) != 1:
        raise ValueError("Upstream strict-loading patch context changed")
    strict_only = original.replace(old, new)
    if original.count("self.policy.cuda()") != 1:
        raise ValueError("Upstream GPU transfer patch context changed")
    patched = strict_only.replace("self.policy.cuda()", "self.policy.to(device=\"cuda\", dtype=self.weight_dtype)")
    target = source / FILE
    if target.read_text() not in (original, strict_only, patched):
        raise ValueError(f"Refusing unexpected changes in {FILE}")
    model_original = subprocess.check_output(["git", "-C", str(source), "show", f"HEAD:{MODEL_FILE}"], text=True)
    load = "        _st.load_model(instance, model_file, strict=strict, device=map_location)"
    if model_original.count(load) != 1:
        raise ValueError("Upstream checkpoint-loading context changed")
    model_patched = model_original.replace(load, '''        # Match train.py: the action expert never uses a language output head.
        # The released checkpoint omits it and stores all parameters in BF16.
        # safetensors strict loading checks dtype as well as keys and shapes.
        del instance.model.dual_tower.expert.lm_head
        instance.to(dtype=torch.bfloat16)
''' + load)
    model_target = source / MODEL_FILE
    if model_target.read_text() not in (model_original, model_patched):
        raise ValueError(f"Refusing unexpected changes in {MODEL_FILE}")
    for path, content in ((target, patched), (model_target, model_patched)):
        if path.read_text() != content:
            path.write_text(content)
    return git("diff", "HEAD")


if __name__ == "__main__":
    print(patch_source(sys.argv[1]))
