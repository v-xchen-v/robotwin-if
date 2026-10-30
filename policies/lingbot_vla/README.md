# LingBot-VLA 4B RoboTwin inference

Checkpoint: [`robbyant/lingbot-vla-4b-posttrain-robotwin`](https://huggingface.co/robbyant/lingbot-vla-4b-posttrain-robotwin), revision `fb71a2c9749ccfedbb7290c2c3f0e5e7c7305c9e`. Official [source](https://github.com/Robbyant/lingbot-vla/tree/4eb34b7693a0565c67433f8fac9c59a2e67eb60b) is pinned to `4eb34b7693a0565c67433f8fac9c59a2e67eb60b`. This is the **depth-free LingBot-VLA**, a separate architecture and policy from LingBot-VA.

## Setup

From the repository root:

```bash
bash policies/lingbot_vla/setup_env.sh
conda run --no-capture-output -n RoboTwin python -m pip install \
  -r policies/lingbot_vla/requirements-client.txt
```

Setup creates the dedicated `robotwin-if-lingbot-vla` environment (Python 3.12, PyTorch 2.7.1 / torchvision 0.22.1, CUDA 12.8, Transformers 4.51.3, LeRobot 0.4.2). PyTorch 2.7.1 satisfies LeRobot's declared `<2.8` dependency constraint; upstream's installation instructions request 2.8.0. NumPy 2.2.6 satisfies LeRobot's rerun-sdk dependency; the simulator retains its own NumPy version. Direct dependencies are pinned, not all transitive dependencies. LeRobot's declared support dependencies are installed; depth submodules and weights are unnecessary for this checkpoint. Setup accepts `--env-name` and `--source-dir`, checks imports and runs `pip check`.

[`patch_source.py`](patch_source.py) replaces five hardcoded FlashAttention constructor settings with the model's existing eager backend and imports its missing `rotate_half` helper from Transformers. This avoids compiling FlashAttention. The official deployment already uses eager attention for the combined VLM/action expert; this patch also selects eager attention for the vision tower. It changes no model parameters or action codec. Setup rejects other tracked source changes and supports idempotent reruns. Server metadata records the full patch; `check_env.py` exercises vision attention and verifies that separate image/window segments cannot attend to each other.

## Download and serve

The checkpoint is about **15.6 GiB** (FP32 on disk). Allocate at least 18 GiB for the weights and processor assets:

```bash
export ROBOTWIN_IF_HOME="${ROBOTWIN_IF_HOME:-$HOME/.local/share/robotwin-if}"
conda run --no-capture-output -n robotwin-if-lingbot-vla \
  python policies/lingbot_vla/download_checkpoint.py \
  --output-dir "$ROBOTWIN_IF_HOME/checkpoints/lingbot-vla-4b-posttrain-robotwin"

conda run --no-capture-output -n robotwin-if-lingbot-vla \
  python policies/lingbot_vla/serve.py \
  --checkpoint-dir "$ROBOTWIN_IF_HOME/checkpoints/lingbot-vla-4b-posttrain-robotwin" \
  --gpu 1 --port 8012 \
  --output-dir outputs/policy-eval/servers/lingbot-vla-002
```

Downloads resume and write `checkpoint.json`. Only the configuration/tokenizer/processor files from `Qwen/Qwen2.5-VL-3B-Instruct` revision `66285546d2b821cf421d4f5eb2576359d3770cd3` are downloaded into `qwen_processor/`; the VLA checkpoint contains the complete model weights. Runtime uses these local assets with Hub offline mode. The server loads the official `LingbotVLAServer` with strict state-dict checking, BF16, 50 actions per chunk and 10 denoising steps. `--use-length` accepts 1–50, `--denoising-steps` changes sampling, and `--use-compile` enables upstream's optional Torch compilation (disabled by default).

The service defaults to `ws://127.0.0.1:8012`; `/healthz` responds after model loading. Use a new `--output-dir` for each launch. The handshake and `server.json` record checkpoint identity, normalization/config hashes, source patch, GPU, precision and sampling settings. One client may connect at a time. Every new connection must reset before prediction; each episode reset seeds Python, NumPy and Torch. Full kernel determinism is not enforced.

## Run the benchmark

Keep the model server running, then use the RoboTwin environment from the repository root:

```bash
bash scripts/eval.sh --policy lingbot_vla --task press_lift_stapler --blocks 1 \
  --output-dir outputs/policy-eval/first-run
bash scripts/eval.sh --policy lingbot_vla --output-dir outputs/policy-eval/full-run
```

The full run uses 20 blocks per task and 460 exact-seed episodes. Choose fresh output directories.
See [evaluation](../../docs/formal-policy-evaluation.md) for options and scoring,
and [published results](../../result/README.md) for the frozen six-task benchmark.


## Action and output contract

- Input: head/left wrist/right wrist HWC uint8 RGB, the measured 14D `joint_action.vector`, and the actual instruction under `task`. A fresh observation is sent for every chunk.
- Official server processing: bilinear resize to 224², `FeatureTransform` using `configs/robot_configs/robotwin.yaml`, `assets/norm_stats/robotwin_50.json` and `bounds_99` normalization. Internal state/action padding is handled by the official model.
- Output: `(use_length, 14)` absolute joint positions, ordered `[left joints × 6, left gripper, right joints × 6, right gripper]`. Execute directly through `env.take_action(..., action_type="qpos")`. Grippers are continuous values passed unchanged to RoboTwin. No EE/quaternion conversion, sigmoid, relative-pose addition or VA cache update.
- Execution stops immediately at success or the task action limit, including in the middle of a chunk. The remaining predicted actions stay in the evidence but are not executed.

Outputs use `outputs/policy-eval/<run>/lingbot_vla/<task>/<task>_ep<seed>*`. Core files match existing policies: `_summary.json`, `_status.json`, `_instruction.txt`, `_step0000.png`, `_timings.json`, `_action_logs.json`, `.log` and `_1.mp4` / `_0.mp4`. Videos show all three camera views. Additional files include `_result.json`, `_oracle.json`, `_initial_observation.npz`, `_actions.npz`, `_requests.json` and `_diagnostics.json`.

Action logs add `ROBOT_LEFT/RIGHT_JOINT_POS`; EE translation/rotation fields are `null` because predictions are joint targets. `_actions.npz` keeps complete raw chunks, the actually executed actions, measured joints and measured EE poses. Uncollected generic grasp/lift diagnostics are explicitly null; task `signals` are retained. Prediction latency is charged only to each chunk's first executed action. Reset and individual RPC timings are separate. The runner reuses existing X-VLA seed/instruction/output helpers and the shared NumPy WebSocket envelope from LingBot-VA.

## Checks

```bash
conda run --no-capture-output -n RoboTwin python tests/lingbot_vla/test_client.py
ruff check policies/lingbot_vla tests/lingbot_vla
```

Six tests cover absolute joint/gripper semantics, official wire-format parity, fresh observations, reset/protocol validation, bounded execution and failure evidence.


Checkpoint identities and full inference evidence: [results](../../result/README.md) · [download](../../docs/download-results.md).
