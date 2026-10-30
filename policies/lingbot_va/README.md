# LingBot-VA RoboTwin inference

Checkpoint: [`robbyant/lingbot-va-posttrain-robotwin`](https://huggingface.co/robbyant/lingbot-va-posttrain-robotwin), Apache-2.0, public/non-gated. ModelScope also hosts `Robbyant/lingbot-va-posttrain-robotwin`. This integration pins Hugging Face revision `8c9dea8abbc5c91cc9e18bc3264b8915083bbe70` and official [source](https://github.com/Robbyant/lingbot-va/tree/7c6ffa9bfc4b83582cafc860fab4c82cc7deeeeb) revision `7c6ffa9bfc4b83582cafc860fab4c82cc7deeeeb`.

## Setup

Run from the repository root:

```bash
bash policies/lingbot_va/setup_env.sh
conda run --no-capture-output -n RoboTwin python -m pip install \
  -r policies/lingbot_va/requirements-client.txt
```

The model gets a dedicated `robotwin-if-lingbot-va` Conda environment: Python 3.10, PyTorch 2.9.0 / torchvision 0.24.0 with CUDA 12.6, diffusers 0.36.0 and transformers 4.55.2. The simulator retains its environment, with only `websockets` and `msgpack` added. Direct inference dependencies are pinned; this is not a complete transitive lock. Training dependencies are omitted. Setup accepts `--env-name` and `--source-dir`.

Upstream unconditionally imports FlashAttention even when selecting its supported Torch SDPA backend. [`patch_source.py`](patch_source.py) makes just that import optional in the pinned checkout; requesting FlashAttention without installing it raises an explicit error. Other tracked edits are rejected. Model inference remains the upstream `VA_Server`; it explicitly loads `attn_mode="torch"`, overriding the checkpoint's training setting without editing weights/config files.

## Download and serve

The checkpoint is approximately **22.7 GiB**. Use a filesystem with at least 25 GiB available:

```bash
export ROBOTWIN_IF_HOME="${ROBOTWIN_IF_HOME:-$HOME/.local/share/robotwin-if}"
conda run --no-capture-output -n robotwin-if-lingbot-va \
  python policies/lingbot_va/download_checkpoint.py \
  --output-dir "$ROBOTWIN_IF_HOME/checkpoints/lingbot-va-posttrain-robotwin"

conda run --no-capture-output -n robotwin-if-lingbot-va \
  python policies/lingbot_va/serve.py \
  --checkpoint-dir "$ROBOTWIN_IF_HOME/checkpoints/lingbot-va-posttrain-robotwin" \
  --gpu 1 --port 8011 --no-offload \
  --output-dir outputs/policy-eval/servers/lingbot-va-001
```

Downloading the public checkpoint does not require an HF token. The script supports resuming and stores `checkpoint.json` with the pinned identity. Use a fresh output directory for each server launch. The server binds `127.0.0.1` by default and supports one active client, preventing episodes from sharing mutable KV state. `/healthz` is available once the model is loaded.

The server uses one GPU, BF16, Torch attention, and CPU offload for VAE/text encoder by default. Upstream estimates about 24GB VRAM for offloaded RoboTwin inference. The example selects `--no-offload` for this machine's 48GB A6000: its Xeon 5118 lacks native BF16 support, and the first offloaded text reset took 143.64 seconds. Omit that flag to use CPU offload on smaller GPUs. `--cpu-threads` defaults to 8. The wrapper runs the upstream model without distributed sharding on this single GPU. `server.json` and the WebSocket handshake expose checkpoint identity, source diff, attention/offload settings and denoising parameters. Each reset seeds Python, NumPy and Torch using the exact episode seed; deterministic kernels are not enforced. The simulator uses GPU 0 in the standard launcher.

## Run the benchmark

Keep the model server running, then use the RoboTwin environment from the repository root:

```bash
bash scripts/eval.sh --policy lingbot_va --task press_lift_stapler --blocks 1 \
  --output-dir outputs/policy-eval/first-run
bash scripts/eval.sh --policy lingbot_va --output-dir outputs/policy-eval/full-run
```

The full run uses 20 blocks per task and 460 exact-seed episodes. Choose fresh output directories.
See [evaluation](../../docs/formal-policy-evaluation.md) for options and scoring,
and [published results](../../result/README.md) for the frozen six-task benchmark.


## Policy contract

- Observation: head, left wrist and right wrist HWC RGB images, Agilex 14D joint/gripper state, and the actual language instruction. The server performs official image resizing and T-shaped latent composition. The model primarily consumes image/language; the client also sends the upstream joint-state field.
- Model representation: 30 internal channels; the server denormalizes and selects `[0:7, 28, 7:14, 29]`, returning `(16, 2, 16)` = left xyz/quaternion/gripper + right xyz/quaternion/gripper, two latent frames, 16 actions per frame.
- Execution: these poses are relative to the episode's initial EE poses. Match upstream `add_init_pose`: translations are added directly; quaternion composition is initial × predicted, using the upstream numeric SciPy xyzw convention before passing the numbers to RoboTwin wxyz. Grippers pass through unchanged. This is distinct from X-VLA's 20D rot6d/sigmoid codec.
- State: each episode sends an actual remote reset. The first chunk's conditioning frame is skipped (16 actions executed); later chunks execute 32. Capture a real observation every four actions. Before the next prediction, send four/eight keyframes and the complete raw predicted tensor to update KV cache. Stop immediately at success/action budget. Terminal or partial chunks do not update cache; the next episode resets all caches.
- Evidence: `_actions.npz` retains the raw `(chunks,16,2,16)` predictions, skipped-frame counts, absolute executed actions and measured EE poses. JSON action logs flatten each full chunk in frame-major order and add `ROT_QUAT`; rotation matrices/rot6d are derived diagnostics. Conditioning-frame zero quaternions have null derived rotations. Step timing charges cache update + prediction to the next chunk's first action; separate reset/cache/predict request timings are retained.

The adapter reuses shared seed/instruction and output utilities; its state machine and action codec remain policy-specific.

## Checks and status

```bash
conda run --no-capture-output -n RoboTwin python tests/lingbot_va/test_client.py
```


Checkpoint identities and full inference evidence: [results](../../result/README.md) · [download](../../docs/download-results.md).
