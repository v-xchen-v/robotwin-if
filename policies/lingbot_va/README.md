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
conda run --no-capture-output -n robotwin-if-lingbot-va \
  python policies/lingbot_va/download_checkpoint.py \
  --output-dir /Data/robotwin-if/checkpoints/lingbot-va-posttrain-robotwin

conda run --no-capture-output -n robotwin-if-lingbot-va \
  python policies/lingbot_va/serve.py \
  --checkpoint-dir /Data/robotwin-if/checkpoints/lingbot-va-posttrain-robotwin \
  --gpu 1 --port 8011 --no-offload \
  --output-dir outputs/policy-eval/servers/lingbot-va-001
```

Downloading the public checkpoint does not require an HF token. The script supports resuming and stores `checkpoint.json` with the pinned identity. Use a fresh output directory for each server launch. The server binds `127.0.0.1` by default and supports one active client, preventing episodes from sharing mutable KV state. `/healthz` is available once the model is loaded.

The server uses one GPU, BF16, Torch attention, and CPU offload for VAE/text encoder by default. Upstream estimates about 24GB VRAM for offloaded RoboTwin inference. The example selects `--no-offload` for this machine's 48GB A6000: its Xeon 5118 lacks native BF16 support, and the first offloaded text reset took 143.64 seconds. Omit that flag to use CPU offload on smaller GPUs. `--cpu-threads` defaults to 8. The wrapper runs the upstream model without distributed sharding on this single GPU. `server.json` and the WebSocket handshake expose checkpoint identity, source diff, attention/offload settings and denoising parameters. Each reset seeds Python, NumPy and Torch using the exact episode seed; deterministic kernels are not enforced. The existing X-VLA server can remain on GPU 0.

## Validate raw → IF

```bash
# First: native task, exact seed, generated seen instruction as in upstream evaluation.
conda run --no-capture-output -n RoboTwin python policies/lingbot_va/eval.py \
  --task click_bell --seeds 2000 --sim-gpu 0 \
  --output-dir outputs/policy-eval/raw-smoke-001/lingbot_va/click_bell

# After a native success: the first complete left/right IF block.
conda run --no-capture-output -n RoboTwin python policies/lingbot_va/eval.py \
  --task arm_select --task-config demo_clean_arm_select_v3 \
  --seed-manifest seed-manifests/robotwin-if-arm-only-v2-20-per-mode/arm_select.json \
  --blocks 1 --sim-gpu 0 \
  --output-dir outputs/policy-eval/smoke-blocks1/lingbot_va/arm_select
```

Keep the server running while evaluating. Native defaults to generated `seen` instructions, IF to `unseen`. `--instruction-type` can explicitly choose another supported split; IF cannot use task-name text. `--server-url` defaults to `ws://127.0.0.1:8011`; reset/inference/cache calls have a bounded `--request-timeout` (600 seconds). Seeds are oracle-qualified, then the scene is recreated for policy execution. There is no seed replacement, retry selection, or success-based exclusion. Exit codes: 0 = complete with at least one success, 1 = complete/all failures, 2 = incomplete/error.

Outputs follow `outputs/policy-eval/<run>/lingbot_va/<task>/<task>_ep<seed>*`, matching the existing CogACT episode naming. Core files are `_summary.json`, `_status.json`, `_instruction.txt`, `_step0000.png`, `_timings.json`, `_action_logs.json`, `.log`, and `_1.mp4` / `_0.mp4`. Extra files include `_result.json`, `_oracle.json`, `_initial_observation.npz`, `_actions.npz`, `_requests.json` and `_diagnostics.json`. Video shows the three real camera views. Uncollected generic grasp/lift diagnostics are null; task `signals` are retained. Run metadata records source/config hashes and the server handshake.

## Policy contract

- Observation: head, left wrist and right wrist HWC RGB images, Agilex 14D joint/gripper state, and the actual language instruction. The server performs official image resizing and T-shaped latent composition. The model primarily consumes image/language; the client also sends the upstream joint-state field.
- Model representation: 30 internal channels; the server denormalizes and selects `[0:7, 28, 7:14, 29]`, returning `(16, 2, 16)` = left xyz/quaternion/gripper + right xyz/quaternion/gripper, two latent frames, 16 actions per frame.
- Execution: these poses are relative to the episode's initial EE poses. Match upstream `add_init_pose`: translations are added directly; quaternion composition is initial × predicted, using the upstream numeric SciPy xyzw convention before passing the numbers to RoboTwin wxyz. Grippers pass through unchanged. This is distinct from X-VLA's 20D rot6d/sigmoid codec.
- State: each episode sends an actual remote reset. The first chunk's conditioning frame is skipped (16 actions executed); later chunks execute 32. Capture a real observation every four actions. Before the next prediction, send four/eight keyframes and the complete raw predicted tensor to update KV cache. Stop immediately at success/action budget. Terminal or partial chunks do not update cache; the next episode resets all caches.
- Evidence: `_actions.npz` retains the raw `(chunks,16,2,16)` predictions, skipped-frame counts, absolute executed actions and measured EE poses. JSON action logs flatten each full chunk in frame-major order and add `ROT_QUAT`; rotation matrices/rot6d are derived diagnostics. Conditioning-frame zero quaternions have null derived rotations. Step timing charges cache update + prediction to the next chunk's first action; separate reset/cache/predict request timings are retained.

The initial implementation reuses existing X-VLA runner helpers for config, manifest/instruction selection and file naming. Full common-layer extraction remains a later step after validating both policies' behavior; the LingBot-specific state machine and codec stay separate.

## Checks and status

```bash
conda run --no-capture-output -n RoboTwin python tests/lingbot_va/test_client.py
```

Environment installation and CUDA/import checks passed on 2026-09-06. Seven codec/protocol tests cover parity with the pinned official client, first-frame skipping, cache keyframe sampling, reset isolation, invalid responses, action budgets and failure evidence. The required raw → IF smoke validation also passed:

| Task / mode | Exact seed | Result | Actions / chunks |
|---|---:|---|---:|
| raw `click_bell` | 2000 | success | 58 / 3 |
| IF `arm_select` / left | 100000 | success; arm match and lift passed | 80 / 3 |
| IF `arm_select` / right | 100001 | success; arm match and lift passed | 90 / 4 |

The IF run consumed the complete left/right block without skipping or replacing seeds. Both initial observations (three RGB views, 16D EE poses and 14D joint state) match exactly. All executed traces were checked against decoded predictions, and the videos have 59, 81 and 91 frames respectively. Output fields match the reference schema. These three episodes demonstrate initial integration, not benchmark performance.

Evidence: [raw result](../../outputs/policy-eval/raw-smoke-001/lingbot_va/click_bell/click_bell_ep2000_result.json), [IF summary](../../outputs/policy-eval/smoke-blocks1/lingbot_va/arm_select/summary.json), [validation notes](../../notes/2026-09-06-open-source-policy-inference/lingbot-va-validation.md). Raw ran with CPU offload; IF used the same checkpoint with offload disabled. Both configurations are recorded. The commands above reproduce the layout; choose new output directories when repeating the runs.
