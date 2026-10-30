# DM05 RoboTwin2 inference

Checkpoint: [`Dexmal/DM05-robotwin2`](https://huggingface.co/Dexmal/DM05-robotwin2), revision `bef09062f8d9744b7691d0a5db4e23834e46071e`. [Official OpenDM source](https://github.com/dexmal/opendm/tree/c4762fed95e430bf14e86beed73166b8dd18b094) is pinned to `c4762fed95e430bf14e86beed73166b8dd18b094`. This is the full Gemma3 VLM and action-expert checkpoint, with about 5.83B parameters.

## Install and start

Run from the repository root:

```bash
export ROBOTWIN_IF_HOME="${ROBOTWIN_IF_HOME:-$HOME/.local/share/robotwin-if}"
bash policies/dm05/setup_env.sh
conda run --no-capture-output -n RoboTwin python -m pip install \
  -r policies/dm05/requirements-client.txt

conda run --no-capture-output -p "$ROBOTWIN_IF_HOME/envs/robotwin-if-dm05" \
  python policies/dm05/download_checkpoint.py \
  --output-dir "$ROBOTWIN_IF_HOME/checkpoints/DM05-robotwin2"

conda run --no-capture-output -p "$ROBOTWIN_IF_HOME/envs/robotwin-if-dm05" \
  python policies/dm05/serve.py \
  --checkpoint-dir "$ROBOTWIN_IF_HOME/checkpoints/DM05-robotwin2" \
  --gpu 1 --port 8014 \
  --output-dir outputs/policy-eval/servers/dm05-002
```

The dedicated environment uses Python 3.10, Torch 2.11.0 / torchvision 0.26.0 CUDA 12.8, Transformers 5.3.0, and NumPy 1.26.4. Setup installs the official inference import dependencies; training/UI dependencies are omitted. Use `ROBOTWIN_IF_HOME` to select a writable storage root (default: `$HOME/.local/share/robotwin-if`), or `--env-prefix` and `--source-dir` to override individual locations. Conda package cache and temporary downloads default to the environment's parent directory. If you override the environment prefix, use that same path in every `conda run -p` command. Weights require about 11 GiB. Setup does not modify the RoboTwin or other policy environments. For an existing `/Data/robotwin-if` installation, set `ROBOTWIN_IF_HOME=/Data/robotwin-if` to reuse it; no automatic migration is performed. See the [Quickstart](../../docs/quickstart.md) for simulator setup and the six-task evaluation entry point.

The download and every server startup verify the weights' SHA-256 against the pinned Hugging Face LFS object `74e8dbb475148080e35ede3f6823322eb6a0b061c8f843a932a4c4ce879bd282`. The download records processor/config/statistics hashes, which are checked again at startup. Inference uses local files with Hub offline mode, rejects missing/unexpected/mismatched model keys, and requires a clean pinned OpenDM checkout. No OpenDM source patch is needed.

Runtime uses BF16 mixed precision, the official default-inference **eager LLM** backend, SDPA vision/action attention, and no Liger kernels. Attention selection is set in memory before constructing the model so the saved training FlashAttention settings do not require a separate extension. OpenDM attempts automatic action-expert CUDA Graph capture; per-request metadata records active/disabled profile counts. On this pinned source, capture fails because `_build_adarms_cond` is called with an extra argument. Upstream catches the error and falls back to ordinary PyTorch execution with SDPA; this fallback is the validated runtime. Graph replay acceleration is therefore unavailable. Full kernel determinism is not enforced.

## HTTP and action contract

The default service is `http://127.0.0.1:8014`. `/healthz` becomes available after model initialization; `/metadata` reports checkpoint identity, precision, normalization and action semantics. Flask runs a single request at a time to serialize sampling and GPU work. Bind `--host` explicitly if remote access is needed. Choose a fresh output directory on every launch.

`POST /v1/infer` uses the official JSON format:

```json
{
  "observation": {
    "prompt": "the actual task instruction",
    "state": [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1],
    "images": {"1": "base64 PNG", "2": "base64 PNG", "3": "base64 PNG"},
    "robot_type": "Aloha RoboTwin2"
  },
  "sampling": {"num_steps": 10, "seed": 2000}
}
```

The response contains `actions` with shape `(50, 14)` and `metadata` with model/API timings. Input errors return HTTP 400; inference failures return HTTP 500. This adapter requires an explicit uint32 sampling seed and exactly 10 diffusion steps.

- Camera slots are head, left wrist, right wrist, encoded from HWC uint8 RGB as lossless PNG. Official `NoAugmentationPipeline` pads to square and resizes to 448×448 before the checkpoint's Gemma3 processor.
- State and actions share RoboTwin ordering: **left 6 joints, left gripper, right 6 joints, right gripper**. The state is the current measured `joint_action.vector`.
- Official transforms quantile-normalize/clamp state, include it in the chat prompt using 256 bins, and process the actual instruction with a maximum length of 1024 tokens. No history is used.
- The expert samples 50×32 padded actions with a mask selecting the first 14 dimensions. Official checkpoint `norm_stats.json` denormalizes those dimensions to **absolute joint targets**. `use_absolute_action=False` disables the upstream relative-to-absolute conversion; no current state is added to these already absolute predictions.
- Execute all 50 actions per chunk, stopping immediately on task success or the action limit. Grippers remain continuous and are not binarized. No ensemble or action interpolation is introduced by the adapter.
- Inference is stateless. `/v1/reset` acknowledges reset; every subsequent request independently supplies prompt, observations and seed. The client requires `reset(instruction, episode_seed)` and uses `(episode_seed + chunk_index) % 2**32` for successive predictions. Invalid client reset clears the local episode. The environment variable `DM05_INFERENCE_SEED` is rejected because it overrides request seeds in upstream.

These settings follow [OpenDM's RoboTwin2 guide](https://github.com/dexmal/opendm/blob/c4762fed95e430bf14e86beed73166b8dd18b094/docs/en/dm05_robotwin2.md): three cameras, absolute actions and horizon 50.

## Run the benchmark

Keep the model server running, then use the RoboTwin environment from the repository root:

```bash
bash scripts/eval.sh --policy dm05 --task press_lift_stapler --blocks 1 \
  --output-dir outputs/policy-eval/first-run
bash scripts/eval.sh --policy dm05 --output-dir outputs/policy-eval/full-run
```

The full run uses 20 blocks per task and 460 exact-seed episodes. Choose fresh output directories.
See [evaluation](../../docs/formal-policy-evaluation.md) for options and scoring,
and [published results](../../result/README.md) for the frozen six-task benchmark.


## Checks

```bash
conda run --no-capture-output -n RoboTwin \
  python -m unittest discover -s tests/dm05 -p 'test_client.py'
conda run --no-capture-output -p "${ROBOTWIN_IF_HOME:-$HOME/.local/share/robotwin-if}/envs/robotwin-if-dm05" \
  python -m unittest discover -s tests/dm05 -p 'test_service.py'
ruff check policies/dm05 tests/dm05
```

The client/runner checks cover lossless camera order, measured state, absolute actions, seed reset/wraparound, HTTP failures and partial-chunk execution/evidence. Service checks exercise input rejection, error recovery and the real upstream image parsing/absolute output transform with an asymmetric synthetic normalization profile.


Checkpoint identities and full inference evidence: [results](../../result/README.md) · [download](../../docs/download-results.md).
