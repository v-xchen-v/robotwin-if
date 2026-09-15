# VLAct Qwen3OFT RoboTwin inference

Default checkpoint: [`StarVLA/VLAct_Qwen3OFT_Robotwin_all_Finetune`](https://huggingface.co/StarVLA/VLAct_Qwen3OFT_Robotwin_all_Finetune), revision `999b37d4d7c1bd0f5588f78d72a185f6f052bf83`. This is the **100K-step All / Data Scaling** checkpoint (`robotwin_all_wrap_32`), selected for the formal evaluation. [Official VLAct source](https://github.com/starVLA/VLAct/tree/621b01bb830e1a400f12f4c05262add55ae3003a) remains pinned to `621b01bb830e1a400f12f4c05262add55ae3003a`.

The previous **50K-step Base / Clean** checkpoint, `StarVLA/VLAct_Qwen3OFT_Robotwin_Finetune` at `dcf0f1d7239b28ae81a039c8d05bdfcd1d4792a5`, remains available with `download_checkpoint.py --variant clean`. Use separate checkpoint and result directories. The server selects the pinned variant from `checkpoint.json`, verifies its weights, and requires that variant's training mix; old Clean results cannot count toward an All rerun.

## Setup and serve

Run from this repository root:

```bash
bash policies/vlact/setup_env.sh
conda run --no-capture-output -n RoboTwin python -m pip install \
  -r policies/vlact/requirements-client.txt

conda run --no-capture-output -n robotwin-if-vlact \
  python policies/vlact/download_checkpoint.py \
  --variant all --output-dir /Data/robotwin-if/checkpoints/VLAct_Qwen3OFT_Robotwin_all_Finetune

conda run --no-capture-output -n robotwin-if-vlact \
  python policies/vlact/serve.py \
  --checkpoint-dir /Data/robotwin-if/checkpoints/VLAct_Qwen3OFT_Robotwin_all_Finetune \
  --gpu 0 --port 8013 \
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

## Raw → IF validation

```bash
conda run --no-capture-output -n RoboTwin python policies/vlact/eval.py \
  --task click_bell --seeds 2000 --sim-gpu 0 \
  --output-dir outputs/policy-eval/raw-smoke-001/vlact/click_bell

# Run after a successful raw episode: the complete first left/right IF block.
conda run --no-capture-output -n RoboTwin python policies/vlact/eval.py \
  --task arm_select \
  --seed-manifest seed-manifests/if-ext-v1-100-per-mode/arm_select.json \
  --blocks 1 --sim-gpu 0 \
  --output-dir outputs/policy-eval/smoke-blocks1/vlact/arm_select
```

Use `--server-url` and `--request-timeout` for endpoint/timeout overrides. Native instructions default to generated `seen`; IF uses `unseen`. Every exact seed is oracle-qualified and recreated before policy execution. No failed seeds are replaced or excluded. The initial IF entry point supports `arm_select`. Exit codes: 0 = complete with at least one success, 1 = complete/all failures, 2 = incomplete/error.

Outputs follow `outputs/policy-eval/<run>/vlact/<task>/<task>_ep<seed>*`, using the same episode files as the other policies: summary/status, instruction, initial image, three-camera video, timings, action logs, oracle, requests and diagnostics. `_actions.npz` contains original `model_actions`, complete decoded `raw_actions`, the actually executed prefix, and measured joints/EE poses. EE prediction fields and uncollected grasp diagnostics are null; task-specific signals are retained. The runner reuses X-VLA's seed/task/instruction/output utilities and the existing NumPy WebSocket envelope.

## Checks

```bash
conda run --no-capture-output -n RoboTwin \
  python -m unittest discover -s tests/vlact -p 'test_*.py'
ruff check policies/vlact tests/vlact
```

Tests cover pinned All/Clean identities and rejection of mixed revisions or weight hashes, angular wrap, asymmetric arm/gripper ordering, official decoder/image/wire parity, fresh image observations without state input, episode reset, protocol errors, partial-chunk action limits and failure evidence.

## Validation results (2026-09-07)

These are historical results from the **Clean 50K** checkpoint, not results from the All rerun.

Environment installation, `pip check`, the full official QwenOFT import path, CUDA SDPA, eight client/runner/codec tests and Ruff passed. The pinned checkpoint loaded with strict parameter checking on an RTX A6000. A saved real observation returned finite `(32, 14)` predictions; repeated reset with seed 2000 produced bitwise-identical actions. First prediction took 2.52 seconds and the warmed prediction 0.12 seconds. Live checks also verified that inference requires reset, a second client is rejected, and an invalid reset invalidates the episode.

| Task / mode | Exact seed | Result | Actions / chunks |
|---|---:|---|---:|
| raw `click_bell` | 2000 | success | 59 / 2 |
| IF `arm_select` / left | 100000 | action limit; no lift, arm match false | 400 / 13 |
| IF `arm_select` / right | 100001 | success; lifted, arm match true | 99 / 4 |

The raw → IF sequence completed: raw **1/1**, complete balanced IF block **1/2**. The left-arm failure is retained; no seeds were skipped or replaced. These are initial integration smoke outcomes under the recorded SDPA/precision configuration, not benchmark success-rate estimates.

All **558 executed actions** exactly match the decoded model-prediction prefixes. Videos contain 60, 401 and 100 frames respectively. The two IF episodes have identical initial RGB views and joint states. The server remains on GPU 0 at port 8013, using about 9.2 GiB of GPU memory when idle.

Evidence: [server metadata](../../outputs/policy-eval/servers/vlact-001/server.json), [real-observation preflight](../../outputs/policy-eval/servers/vlact-001/preflight.json), [live protocol checks](../../outputs/policy-eval/servers/vlact-001/live_protocol.json), [raw summary](../../outputs/policy-eval/raw-smoke-001/vlact/click_bell/summary.json), [raw trace validation](../../outputs/policy-eval/raw-smoke-001/vlact/click_bell/validation.json), [IF summary](../../outputs/policy-eval/smoke-blocks1/vlact/arm_select/summary.json), [IF trace validation](../../outputs/policy-eval/smoke-blocks1/vlact/arm_select/validation.json). Setup/download logs and both environments' package versions are saved beside the server metadata. Checkpoints, third-party source and evaluation outputs are not committed.
