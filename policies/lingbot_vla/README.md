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
conda run --no-capture-output -n robotwin-if-lingbot-vla \
  python policies/lingbot_vla/download_checkpoint.py \
  --output-dir /Data/robotwin-if/checkpoints/lingbot-vla-4b-posttrain-robotwin

conda run --no-capture-output -n robotwin-if-lingbot-vla \
  python policies/lingbot_vla/serve.py \
  --checkpoint-dir /Data/robotwin-if/checkpoints/lingbot-vla-4b-posttrain-robotwin \
  --gpu 0 --port 8012 \
  --output-dir outputs/policy-eval/servers/lingbot-vla-002
```

Downloads resume and write `checkpoint.json`. Only the configuration/tokenizer/processor files from `Qwen/Qwen2.5-VL-3B-Instruct` revision `66285546d2b821cf421d4f5eb2576359d3770cd3` are downloaded into `qwen_processor/`; the VLA checkpoint contains the complete model weights. Runtime uses these local assets with Hub offline mode. The server loads the official `LingbotVLAServer` with strict state-dict checking, BF16, 50 actions per chunk and 10 denoising steps. `--use-length` accepts 1–50, `--denoising-steps` changes sampling, and `--use-compile` enables upstream's optional Torch compilation (disabled by default).

The service defaults to `ws://127.0.0.1:8012`; `/healthz` responds after model loading. Use a new `--output-dir` for each launch. The handshake and `server.json` record checkpoint identity, normalization/config hashes, source patch, GPU, precision and sampling settings. One client may connect at a time. Every new connection must reset before prediction; each episode reset seeds Python, NumPy and Torch. Full kernel determinism is not enforced.

## Raw → IF validation

Keep the server running and use the simulator environment:

```bash
# Native task first; generated seen instruction, exact seed.
conda run --no-capture-output -n RoboTwin python policies/lingbot_vla/eval.py \
  --task click_bell --seeds 2000 --sim-gpu 0 \
  --output-dir outputs/policy-eval/raw-smoke-002/lingbot_vla/click_bell

# After native success: the complete first left/right IF block.
conda run --no-capture-output -n RoboTwin python policies/lingbot_vla/eval.py \
  --task arm_select \
  --seed-manifest seed-manifests/if-ext-v1-100-per-mode/arm_select.json \
  --blocks 1 --sim-gpu 0 \
  --output-dir outputs/policy-eval/smoke-blocks1/lingbot_vla/arm_select
```

Use `--server-url` for a different server and `--request-timeout` for a bounded RPC timeout (default 600 seconds). Native instructions default to `seen`; IF uses `unseen` and cannot substitute task-name text. Seeds are oracle-qualified, the scene is recreated, and then the actual generated instruction goes to the policy. No seed replacement or success-based exclusion. The initial IF entry point supports `arm_select`. Exit codes: 0 = complete with at least one success, 1 = complete/all failures, 2 = incomplete/error.

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

## Validation results (2026-09-07)

Environment installation, `pip check`, official imports, CUDA arithmetic, eager vision forward/mask checks, six client/runner tests and Ruff passed. The complete checkpoint loaded with strict state-dict checking on an RTX A6000. A real saved initial observation returned finite `(50, 14)` actions; two resets with seed 2000 produced exactly identical predictions. Preflight latency was 1.82 seconds initially and 1.13 seconds after warming up. The server remains on GPU 0, port 8012, with metadata at [`servers/lingbot-vla-002`](../../outputs/policy-eval/servers/lingbot-vla-002/server.json).

| Task / mode | Exact seed | Result | Actions / chunks |
|---|---:|---|---:|
| raw `click_bell` | 2000 | success | 59 / 2 |
| IF `arm_select` / left | 100000 | action limit; no lift, arm match false | 400 / 8 |
| IF `arm_select` / right | 100001 | action limit; no lift, arm match false | 400 / 8 |

Raw inference has a successful closed-loop episode. **The IF success gate is not met**: the complete first left/right block finished with 0/2 successes and no infrastructure errors. No seeds were skipped or replaced. These are initial smoke outcomes under the recorded eager/BF16 configuration, not benchmark success-rate estimates.

All 859 executed actions match their raw predicted prefixes exactly. The videos contain 60, 401 and 401 frames respectively. The paired IF initial RGB views and joint states are identical. Evidence: [raw summary](../../outputs/policy-eval/raw-smoke-002/lingbot_vla/click_bell/summary.json), [raw trace validation](../../outputs/policy-eval/raw-smoke-002/lingbot_vla/click_bell/validation.json), [IF summary](../../outputs/policy-eval/smoke-blocks1/lingbot_vla/arm_select/summary.json), [IF trace validation](../../outputs/policy-eval/smoke-blocks1/lingbot_vla/arm_select/validation.json), and [real-observation preflight](../../outputs/policy-eval/servers/lingbot-vla-002/preflight.json).

The first raw attempt found the upstream eager branch's missing `rotate_half` import before executing any action. That [error record](../../outputs/policy-eval/raw-smoke-001/lingbot_vla/click_bell/click_bell_ep2000_result.json) and the original server metadata remain available. After fixing the import, the same seed was rerun in `raw-smoke-002`; all initial observation arrays match the first attempt exactly. Choose fresh server/evaluation output directories when repeating these commands.
