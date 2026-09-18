# DM05 RoboTwin2 inference

Checkpoint: [`Dexmal/DM05-robotwin2`](https://huggingface.co/Dexmal/DM05-robotwin2), revision `bef09062f8d9744b7691d0a5db4e23834e46071e`. [Official OpenDM source](https://github.com/dexmal/opendm/tree/c4762fed95e430bf14e86beed73166b8dd18b094) is pinned to `c4762fed95e430bf14e86beed73166b8dd18b094`. This is the full Gemma3 VLM and action-expert checkpoint, with about 5.83B parameters.

## Install and start

Run from the repository root:

```bash
bash policies/dm05/setup_env.sh
conda run --no-capture-output -n RoboTwin python -m pip install \
  -r policies/dm05/requirements-client.txt

conda run --no-capture-output -p /Data/robotwin-if/envs/robotwin-if-dm05 \
  python policies/dm05/download_checkpoint.py \
  --output-dir /Data/robotwin-if/checkpoints/DM05-robotwin2

conda run --no-capture-output -p /Data/robotwin-if/envs/robotwin-if-dm05 \
  python policies/dm05/serve.py \
  --checkpoint-dir /Data/robotwin-if/checkpoints/DM05-robotwin2 \
  --gpu 0 --port 8014 \
  --output-dir outputs/policy-eval/servers/dm05-002
```

The dedicated environment uses Python 3.10, Torch 2.11.0 / torchvision 0.26.0 CUDA 12.8, Transformers 5.3.0, and NumPy 1.26.4. Setup installs the official inference import dependencies; training/UI dependencies are omitted. Use `--env-prefix` and `--source-dir` to override locations. The environment, temporary downloads and Conda package cache default to external storage under `/Data`, since this CUDA stack is large. Weights require about 11 GiB. Setup does not modify the RoboTwin or other policy environments.

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

## Raw → IF validation

```bash
conda run --no-capture-output -n RoboTwin python policies/dm05/eval.py \
  --task click_bell --seeds 2000 --sim-gpu 0 \
  --output-dir outputs/policy-eval/raw-smoke-001/dm05/click_bell

# After a successful raw episode, run the complete first balanced IF block.
conda run --no-capture-output -n RoboTwin python policies/dm05/eval.py \
  --task arm_select --task-config demo_clean_arm_select_v3 \
  --seed-manifest seed-manifests/robotwin-if-arm-only-v2-20-per-mode/arm_select.json \
  --blocks 1 --sim-gpu 0 \
  --output-dir outputs/policy-eval/smoke-blocks1/dm05/arm_select
```

Use `--server-url` and `--request-timeout` to override connection settings. Native tasks default to generated `seen` instructions; IF uses `unseen`. Each exact seed is oracle-qualified and recreated before policy execution. Failed seeds are retained without replacements. The initial IF entry point supports `arm_select`. Exit codes: 0 = complete with at least one success, 1 = complete/all failures, 2 = incomplete/error.

Outputs follow `outputs/policy-eval/<run>/dm05/<task>/<task>_ep<seed>*`: summary/status, instruction, initial observation/image, three-camera video, timings, action logs, oracle, requests and diagnostics. `_actions.npz` stores complete denormalized `raw_actions` chunks, the actually executed prefix, and measured joints/EE poses. EE prediction fields and uncollected grasp diagnostics are null. Per-request sampling seeds and server graph/timing metadata are retained. Seed/task/instruction/output utilities are reused from the existing X-VLA runner.

A saved real observation can also be checked using `preflight.py --observation <npz> --instruction <text> --output-dir <new-directory>`. This repeats the first prediction three times with the same seed and records numerical differences and graph/fallback status.

## Checks

```bash
conda run --no-capture-output -n RoboTwin \
  python -m unittest discover -s tests/dm05 -p 'test_client.py'
conda run --no-capture-output -p /Data/robotwin-if/envs/robotwin-if-dm05 \
  python -m unittest discover -s tests/dm05 -p 'test_service.py'
ruff check policies/dm05 tests/dm05
```

The client/runner checks cover lossless camera order, measured state, absolute actions, seed reset/wraparound, HTTP failures and partial-chunk execution/evidence. Service checks exercise input rejection, error recovery and the real upstream image parsing/absolute output transform with an asymmetric synthetic normalization profile.

## Validation results (2026-09-07)

Environment setup, `pip check`, the full official inference import path, CUDA SDPA, all **9 client/runner/service tests**, Ruff and shell syntax checks passed. The real checkpoint loaded with zero missing, unexpected or mismatched keys on an RTX A6000. A saved real observation returned finite `(50, 14)` predictions; three requests reset to seed 2000 produced bitwise-identical actions. First prediction took 1.80 seconds; warmed requests took 0.91–0.93 seconds including image encoding and HTTP transport. CUDA Graph capture fell back to ordinary SDPA as described above; no graph replay was used.

| Task / mode | Exact seed | Result | Actions / chunks |
|---|---:|---|---:|
| raw `click_bell` | 2000 | success | 54 / 2 |
| IF `arm_select` / left | 100000 | success; lifted, arm match true | 85 / 2 |
| IF `arm_select` / right | 100001 | success; lifted, arm match true | 80 / 2 |

The raw → IF sequence passed: raw **1/1**, complete balanced IF block **2/2**. Both IF modes use identical initial RGB images and joint states, with their respective actual left/right instructions. All **219 executed actions** exactly match the recorded prediction prefixes, and all per-chunk seeds match the declared schedule. Videos contain 55, 86 and 81 frames respectively. No seeds were skipped or replaced. These are initial integration smoke results, not estimates of benchmark success rates.

The server remains on GPU 0 at `http://127.0.0.1:8014`, using about **11.5 GiB** of GPU memory. Its PID and console log are beside the server output directory. Other policy services remain running.

Evidence: [server metadata](../../outputs/policy-eval/servers/dm05-002/server.json), [launch command](../../outputs/policy-eval/servers/dm05-002/launch.json), [real-observation preflight](../../outputs/policy-eval/servers/dm05-002/preflight/preflight.json), [raw summary](../../outputs/policy-eval/raw-smoke-001/dm05/click_bell/summary.json), [raw trace validation](../../outputs/policy-eval/raw-smoke-001/dm05/click_bell/validation.json), [IF summary](../../outputs/policy-eval/smoke-blocks1/dm05/arm_select/summary.json), [IF trace validation](../../outputs/policy-eval/smoke-blocks1/dm05/arm_select/validation.json). Setup/download/test logs, both environments' package versions and the trace/frame validation script are saved beside server metadata. Weights, environments, third-party source and evaluation outputs are excluded from Git.
