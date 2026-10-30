# VLAct Qwen3OFT RoboTwin inference

Default checkpoint: [`StarVLA/VLAct_Qwen3OFT_Robotwin_all_Finetune`](https://huggingface.co/StarVLA/VLAct_Qwen3OFT_Robotwin_all_Finetune), revision `999b37d4d7c1bd0f5588f78d72a185f6f052bf83`. This is the **100K-step All / Data Scaling** checkpoint (`robotwin_all_wrap_32`), selected for the formal evaluation. [Official VLAct source](https://github.com/starVLA/VLAct/tree/621b01bb830e1a400f12f4c05262add55ae3003a) remains pinned to `621b01bb830e1a400f12f4c05262add55ae3003a`.

The previous **50K-step Base / Clean** checkpoint, `StarVLA/VLAct_Qwen3OFT_Robotwin_Finetune` at `dcf0f1d7239b28ae81a039c8d05bdfcd1d4792a5`, remains available with `download_checkpoint.py --variant clean`. Use separate checkpoint and result directories. The server selects the pinned variant from `checkpoint.json`, verifies its weights, and requires that variant's training mix; old Clean results cannot count toward an All rerun.

## Setup and serve

Run from this repository root:

```bash
export ROBOTWIN_IF_HOME="${ROBOTWIN_IF_HOME:-$HOME/.local/share/robotwin-if}"
bash policies/vlact/setup_env.sh
conda run --no-capture-output -n RoboTwin python -m pip install \
  -r policies/vlact/requirements-client.txt

conda run --no-capture-output -n robotwin-if-vlact \
  python policies/vlact/download_checkpoint.py \
  --variant all --output-dir "$ROBOTWIN_IF_HOME/checkpoints/VLAct_Qwen3OFT_Robotwin_all_Finetune"

conda run --no-capture-output -n robotwin-if-vlact \
  python policies/vlact/serve.py \
  --checkpoint-dir "$ROBOTWIN_IF_HOME/checkpoints/VLAct_Qwen3OFT_Robotwin_all_Finetune" \
  --gpu 1 --port 8013 \
  --output-dir outputs/policy-eval/servers/vlact-001
```

Setup creates the independent `robotwin-if-vlact` Conda environment: Python 3.10, Torch 2.6.0 / torchvision 0.21.0 CUDA 12.4, Transformers 4.57.0. These match upstream's inference versions. Transformers 4.57.0 is marked yanked on PyPI for packaging issues; it is explicitly pinned to reproduce upstream. Direct dependencies are pinned; transitive dependencies are recorded separately by `pip freeze`. Training and other framework dependencies are omitted. Setup accepts `--env-name` and `--source-dir`. Use a writable external `TMPDIR` for installation if the system disk is small.

The download needs about **20 GiB** for the fine-tuned state dict and base model. The base assets are `StarVLA/Qwen3-VL-4B-Instruct-Action` revision `c41500cf1d287cd79e9f6602f419937b05048bd8`, kept in a nested directory. The official constructor initially loads base weights; **all model parameters are then replaced by the fine-tuned checkpoint with `strict=True`**. The All `steps_100000_pytorch_model.pt` SHA-256 is checked against the published `beb2c0ec39c3bc7173a5bd90eb59ef99854b73ca1aa3bf50fb6ffc353f477c2a` during download and startup. Clean retains its separate 50K weight hash. The packaged config is preserved; only the in-memory base-model location and training resume path are overridden. Runtime uses local files with Hub offline mode.

[`patch_source.py`](patch_source.py) applies three checked, idempotent inference patches:

- Select Transformers' SDPA backend instead of hardcoded FlashAttention 2.
- Use the framework factory's explicit QwenOFT import, avoiding automatic imports of unrelated training/framework dependencies.
- Explicitly cast final predictions to FP32 for NumPy serialization. Model parameters use BF16, matching the official `--use_bf16` launcher and the published weights; upstream's BF16 VLM / FP32 head autocast contexts are retained. The cast also supports runtimes that return BF16 tensors, which NumPy cannot represent directly.

No weight shapes, prompt templates or model layers are changed. The source revision and full patch are saved in `server.json`. Despite the legacy `action_model_type: DiT-B` config field, official QwenOFT builds an **MLPResNet regression head** and predicts all 32 actions in one forward pass; no diffusion sampling is used.

The default endpoint is `ws://127.0.0.1:8013`, with `/healthz` available after model loading. The handshake records checkpoint identity, config/statistics hashes, precision, image buckets and action semantics. One client can connect at a time. Every connection must reset before predicting; each reset seeds Python, NumPy and Torch and binds the episode instruction. Full kernel determinism is not enforced. Choose a fresh server output directory on each launch.

## Input and action contract

- Input order: head, left wrist, right wrist HWC uint8 RGB. Resize each image using OpenCV `INTER_AREA` to the closest aspect-ratio bucket: 320×180 or 280×210, then use the official Qwen3 processor.
- The actual task instruction goes through the checkpoint's `CoT_prompt` and official 32-action token suffix. No substitute task-name prompt or extra control-frequency text is introduced during native/IF validation.
- QwenOFT **does not use measured robot state as model input**. The client records 14D measured joints/grippers for diagnostics only.
- Model order: `[left joints × 6, right joints × 6, left gripper, right gripper]`. RoboTwin execution order: `[left joints × 6, left gripper, right joints × 6, right gripper]`.
- Execute 32 absolute joint targets per chunk with `env.take_action(..., action_type="qpos")`, stopping immediately on success or the task action limit. No action ensemble is enabled.

### Why this checkpoint uses angular wrap

The packaged config selects `robotwin_all_wrap_32` (All) or `robotwin_wrap_32` (Clean). Both use wrap-aware absolute-joint actions and the same 32×14 action contract. Joint targets are radians wrapped to `[-π, π)`, without scaling to `[-1, 1]`. The stats mask selects the first 12 angular joints. Our decoder applies the **official RoboTwin wrap branch**, then reorders channels. Grippers are clipped to `[-1, 1]` as in that branch and are not binarized.

The model card's generic `q01/q99` description differs from this training configuration. Upstream's evaluation client selects wrap by checking whether the **checkpoint pathname contains `wrap`**, so renaming the published directory can silently choose the wrong decoder. This integration explicitly validates the training config and fixes wrap semantics independently of the path. Tests compare decoding and resized pixels directly with the pinned official implementation. No min/max or percentile rescaling is applied to this checkpoint's angular outputs.

## Run the benchmark

Keep the model server running, then use the RoboTwin environment from the repository root:

```bash
bash scripts/eval.sh --policy vlact --task press_lift_stapler --blocks 1 \
  --output-dir outputs/policy-eval/first-run
bash scripts/eval.sh --policy vlact --output-dir outputs/policy-eval/full-run
```

The full run uses 20 blocks per task and 460 exact-seed episodes. Choose fresh output directories.
See [evaluation](../../docs/formal-policy-evaluation.md) for options and scoring,
and [published results](../../result/README.md) for the frozen six-task benchmark.


## Checks

```bash
conda run --no-capture-output -n RoboTwin \
  python -m unittest discover -s tests/vlact -p 'test_*.py'
ruff check policies/vlact tests/vlact
```

Tests cover pinned All/Clean identities and rejection of mixed revisions or weight hashes, angular wrap, asymmetric arm/gripper ordering, official decoder/image/wire parity, fresh image observations without state input, episode reset, protocol errors, partial-chunk action limits and failure evidence.


Checkpoint identities and full inference evidence: [results](../../result/README.md) · [download](../../docs/download-results.md).
