# Fast-WAM RoboTwin inference

This adapter uses the [official FastWAM source](https://github.com/yuantianyuan01/FastWAM/tree/7faa71108368fbb3b6885649f112af607427a2d4)
and the released `robotwin_uncond_3cam_384.pt` and matching dataset statistics from
[`yuanty/fastwam`](https://huggingface.co/yuanty/fastwam/tree/8eaceeb24c3cc92ff2a9c9a9d266a4941b836705).
The upstream source revision and all model files are pinned in
[`../wam/serve.py`](../wam/serve.py) and [`../wam/assets.json`](../wam/assets.json).

## Install and download

Run from the repository root. Choose a storage root with space for model environments
and assets. The two WAMs share Wan resources when using the same asset directory.

```bash
export ROBOTWIN_IF_HOME="${ROBOTWIN_IF_HOME:-$HOME/.local/share/robotwin-if}"
bash policies/fastwam/setup_env.sh
conda run --no-capture-output -n RoboTwin python -m pip install \
  -r policies/fastwam/requirements-client.txt
conda run --no-capture-output -p "$ROBOTWIN_IF_HOME/envs/robotwin-if-fastwam" \
  python policies/fastwam/download_checkpoint.py \
  --output-dir "$ROBOTWIN_IF_HOME/checkpoints/wam"
```

The setup uses a dedicated Python 3.10 environment with Torch 2.7.1 / CUDA 12.8.
It accepts `--env-prefix` and `--source-dir`. Downloads resume and verify the pinned
Hugging Face LFS SHA-256 or Git blob hash for each file. The download includes the
official Wan2.2 distribution, whose T5, tokenizer and VAE are used at inference;
the finetuned Fast-WAM checkpoint supplies the video/action experts.

The [LeRobot-format release](https://huggingface.co/lerobot/fastwam_robotwin_uncond_3cam_384)
is another distribution supplied by the user. This adapter loads the original
PyTorch release and its official processor; it does not load LeRobot `model.safetensors`.
That format requires its corresponding LeRobot policy/processor and independent validation.

## Serve and evaluate

```bash
conda run --no-capture-output -p "$ROBOTWIN_IF_HOME/envs/robotwin-if-fastwam" \
  python policies/fastwam/serve.py \
  --asset-dir "$ROBOTWIN_IF_HOME/checkpoints/wam" --gpu 1 --port 8016 \
  --output-dir outputs/policy-eval/servers/fastwam-001

# In a second terminal with the RoboTwin environment active:
bash scripts/eval.sh --policy fastwam --task press_lift_stapler --blocks 1 \
  --output-dir outputs/policy-eval/fastwam-pilot
```

The server accepts one active client and exposes `/healthz` after loading. Use fresh
output directories. Every episode performs a remote reset and seeds Python, NumPy
and Torch from the exact benchmark episode seed; full kernel determinism is not enforced.
Models and dependencies load from verified local assets, with automatic downloads disabled.

The official adapter composes head RGB at 256×320 above two 128×160 wrist images,
normalizes measured 14D joint state with the published z-score statistics, and supplies
the actual task instruction through the official prompt template. It predicts 32
absolute 14D joint/gripper actions and executes the first 24 before replanning.
Inference uses 10 denoising steps, sigma shift 5, BF16, and no compilation.
The model's action-only inference path retains the official visual conditioning.

The simulator stops on success or the task action budget, including mid-chunk stops.
Evidence retains complete 32-action predictions, 24-action replan prefixes, executed
actions, measured state, initial images, request timings, video and the terminal verdict.
No additional joint wrapping or gripper clipping is applied by the adapter.

The default six-task benchmark has 460 exact-seed episodes. Omit `--task` and `--blocks`
for the full run. See [policy evaluation](../README.md) for the shared scoring contract.
New outputs can be summarized with `tools/summarize_formal_policy_results.py`.
Existing published results do not include Fast-WAM until a validated run is delivered.

## Validation

```bash
conda run --no-capture-output -n RoboTwin python -m unittest discover -s tests/wam -v
bash scripts/eval.sh --policy fastwam --output-dir /tmp/fastwam-plan --dry-run
```

CPU tests verify the transport, episode resets, action-prefix execution, terminal
verdicts, output identity and file integrity. They do not establish model accuracy.

On 2026-11-04, the official checkpoint completed the first balanced `press_lift_stapler`
block (seeds 110000/110001) on an RTX A6000: Press succeeded after 58 actions and
Lift after 79. Both passed exact-seed oracle qualification. Saved evidence includes
full 32-action predictions, executed prefixes and 59/80-frame videos. Subsequent
chunks took about 0.7 seconds in this pilot; cold startup and the first prediction
were slower. This two-episode check verifies the integration and is not the full
460-episode benchmark. Detailed evidence is tracked in the feature's project notes.
