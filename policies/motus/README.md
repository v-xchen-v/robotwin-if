# Motus RoboTwin inference

This adapter uses the [official Motus RoboTwin implementation](https://github.com/thu-ml/Motus/tree/88f6fe30c62af033874b0a2e48ad1cbdaf12cfdf/inference/robotwin/Motus)
and [`motus-robotics/Motus_robotwin2`](https://huggingface.co/motus-robotics/Motus_robotwin2/tree/ab74bc214f7fc5952c85198e062c5f8bf1dc47a7).
Source and model revisions are pinned in [`../wam/serve.py`](../wam/serve.py)
and [`../wam/assets.json`](../wam/assets.json).

## Install and download

Run from the repository root with a storage root large enough for the models and
dedicated environment. Fast-WAM and Motus can share the same asset root.

```bash
export ROBOTWIN_IF_HOME="${ROBOTWIN_IF_HOME:-$HOME/.local/share/robotwin-if}"
bash policies/motus/setup_env.sh
conda run --no-capture-output -n RoboTwin python -m pip install \
  -r policies/motus/requirements-client.txt
conda run --no-capture-output -p "$ROBOTWIN_IF_HOME/envs/robotwin-if-motus" \
  python policies/motus/download_checkpoint.py \
  --output-dir "$ROBOTWIN_IF_HOME/checkpoints/wam"
```

The dedicated environment uses Python 3.10, Torch 2.7.1 / CUDA 12.8, Transformers
4.57.0 and FlashAttention 2.7.4.post1. Setup accepts `--env-prefix` and `--source-dir`.
The FlashAttention wheel is for Linux x86_64 / CPython 3.10 with the pinned Torch ABI.

Downloaded resources:

| Resource | Inference role |
| --- | --- |
| `motus-robotics/Motus_robotwin2` | Full Stage 3 RoboTwin model state |
| `motus-robotics/Motus_Wan2_2_5B_pretrain` | Requested Stage 1 VGM artifact; retained alongside the deployment assets |
| `Qwen/Qwen3-VL-2B-Instruct` | Official config and processor; finetuned VLM weights come from Stage 3 |
| `Wan-AI/Wan2.2-TI2V-5B` | Config, UMT5 text encoder/tokenizer and VAE |

The full Qwen and Wan releases are downloaded as requested, although some base
weights are superseded by Stage 3 at inference. The official wrapper sets
`load_pretrained_backbones=False`; it does not reload Stage 1 over the finetuned model.
All files are downloaded at immutable revisions and verified against LFS SHA-256 or
Git blob hashes. Automatic downloads are disabled when serving.

## Serve and evaluate

```bash
conda run --no-capture-output -p "$ROBOTWIN_IF_HOME/envs/robotwin-if-motus" \
  python policies/motus/serve.py \
  --asset-dir "$ROBOTWIN_IF_HOME/checkpoints/wam" --gpu 1 --port 8017 \
  --output-dir outputs/policy-eval/servers/motus-001

# In a second terminal with the RoboTwin environment active:
bash scripts/eval.sh --policy motus --task press_lift_stapler --blocks 1 \
  --output-dir outputs/policy-eval/motus-pilot
```

Upstream estimates about 41 GB VRAM when encoding T5 instructions online.
The server runs one model on one GPU and accepts one active client. `/healthz`
becomes available after loading. Each episode resets upstream caches and seeds
Python, NumPy and Torch using the benchmark's exact seed; deterministic kernels
are not enforced. Use fresh output directories for each service/run.

The official wrapper takes a 240×320 head image and two wrists resized to 120×160,
then pads/resizes their composite to 384×320. It supplies both T5 and Qwen with the
actual task instruction. The active upstream inference method uses joint video/action
prediction with 10 Euler denoising steps and returns 16 absolute 14D joint actions.
The adapter preserves the upstream raw state/action convention and video prediction.
Predicted-frame PNG grids are disabled, and the unused upstream action queue is
cleared after returning its chunk to avoid accumulating already-executed actions.

All 16 actions are eligible for execution, subject to the task's success and action-budget
checks after every action. Shared evidence includes full predictions, executed actions,
measured states, initial images, request timings, video and terminal verdicts.
No extra action normalization, joint wrapping or gripper clipping is applied.

The default six-task benchmark has 460 exact-seed episodes. Omit `--task` and `--blocks`
to run it in full. See [policy evaluation](../README.md) for task, seed and scoring rules.
The results summarizer recognizes `motus` directories; existing published results do
not include Motus until a validated run is delivered.

## Validation

```bash
conda run --no-capture-output -n RoboTwin python -m unittest discover -s tests/wam -v
bash scripts/eval.sh --policy motus --output-dir /tmp/motus-plan --dry-run
```

CPU tests cover protocol/reset isolation, action budgets, terminal verdicts, output
identity and asset integrity.

On 2026-11-04, the official Stage 3 checkpoint completed the first balanced
`press_lift_stapler` block (seeds 110000/110001) on an RTX A6000: Press succeeded
after 29 actions and Lift after 26. Both passed exact-seed oracle qualification.
All checkpoint keys and shapes matched the inference model. Saved evidence includes
16-action predictions, executed actions and 30/27-frame videos. Subsequent chunks
took about 3.2 seconds; observed model GPU usage was about 41 GiB. This two-episode
pilot verifies the integration and is not the full 460-episode benchmark. Detailed
evidence is tracked in the feature's project notes.
