# X-WAM RoboTwin inference

This adapter uses the [official X-WAM source](https://github.com/sharinka0715/X-WAM/tree/72cfb86b33fc5060963ef63412f16439fcfa472f)
and the `robotwin_sft/` release in
[`sharinka0715/X-WAM-checkpoints`](https://huggingface.co/sharinka0715/X-WAM-checkpoints/tree/bb6fd1643cfa8bdc751612a7ace0bd8062a8917a/robotwin_sft).
The checkpoint, configuration and shared Wan resources are pinned in
[`../wam/assets.json`](../wam/assets.json).
The coordinate codec adapts the official Apache-2.0 deployment; its source and
changes are identified in `client.py`, with the upstream license in
[`LICENSE.upstream`](LICENSE.upstream).

## Install and download

Run from the repository root:

```bash
export ROBOTWIN_IF_HOME="${ROBOTWIN_IF_HOME:-$HOME/.local/share/robotwin-if}"
bash policies/xwam/setup_env.sh
conda run --no-capture-output -n RoboTwin python -m pip install \
  -r policies/xwam/requirements-client.txt
conda run --no-capture-output -p "$ROBOTWIN_IF_HOME/envs/robotwin-if-xwam" \
  python policies/xwam/download_checkpoint.py \
  --output-dir "$ROBOTWIN_IF_HOME/checkpoints/wam"
```

Setup uses a dedicated Python 3.10 environment and accepts `--env-prefix` and
`--source-dir`. It pins Torch 2.7.1 / CUDA 12.8, Transformers 4.51.3, Diffusers
0.38.0, NumPy 1.25.2 and FlashAttention 2.7.4.post1. These are within the upstream
version requirements; upstream reports testing Torch 2.8.0 and FlashAttention 2.8.3.
The FlashAttention wheel targets Linux x86_64 / CPython 3.10 and the pinned Torch ABI.

The RoboTwin SFT checkpoint is about 38.9 GB. It supplies the complete model state,
including the depth branch; the separate pretrained and RoboCasa checkpoints are
not needed. The official constructor also loads Wan base weights, T5, tokenizer
and VAE before strict SFT loading. Existing Fast-WAM/Motus Wan downloads are reused.
Files are checked against immutable revisions and object hashes at startup.

The [training dataset](https://huggingface.co/datasets/sharinka0715/X-WAM-RoboTwin)
documents the observation/action schema. Its approximately 94 GB of training
episodes are not needed for inference: the published SFT config already includes
the required normalization quantiles. The downloader does not fetch training data.

## Serve and evaluate

```bash
conda run --no-capture-output -p "$ROBOTWIN_IF_HOME/envs/robotwin-if-xwam" \
  python policies/xwam/serve.py \
  --asset-dir "$ROBOTWIN_IF_HOME/checkpoints/wam" --gpu 1 --port 8018 \
  --output-dir outputs/policy-eval/servers/xwam-001

# In a second terminal with the RoboTwin environment active:
bash scripts/eval.sh --policy xwam --task press_lift_stapler --blocks 1 \
  --output-dir outputs/policy-eval/xwam-pilot

# Full six-task evaluation: exact manifest order, 20 blocks/task, 460 episodes.
bash scripts/eval.sh --policy xwam \
  --manifest-dir seed-manifests/20-blocks \
  --output-dir outputs/policy-eval/xwam-full
```

Use fresh server and evaluation output directories. The server exposes `/healthz`
after loading and accepts one active client. Model assets load offline. The SFT
checkpoint is memory-mapped on CPU and loaded strictly, preserving the official
parameter coverage without retaining another resident 39 GB copy. The model is
cast to BF16 before moving it to CUDA, reducing startup GPU memory without
changing the final inference dtype.

## Observation and action contract

The model consumes three 240×320 RGB views in head/left-wrist/right-wrist order.
Each is normalized to [-1, 1], resized to 256×320, center-cropped at ratio 0.95 and
resized back using the official helper. No depth camera input is required.

Each arm's native RoboTwin EE position, wxyz quaternion and gripper are transformed
using the official base and EE-axis changes. The resulting 16D state is normalized
with the SFT config's q01/q99 statistics. The actual benchmark instruction is sent
unchanged to the text encoder.

The official action inference uses a 50-step video schedule, 10 action denoising
steps, CFG 0, `early_stop=True`, and `run_depth=False`. This adapter uses eager BF16
inference; the upstream server's `torch.compile` call is not enabled here. The model
predicts 32 dual-arm 14D delta actions. For each arm, xyz, axis-angle rotation and
gripper deltas accumulate relative to the preceding predicted pose; rotation deltas
left-multiply the current orientation. Inverse coordinate transforms produce 32
absolute 16D RoboTwin EE actions, executed with `action_type="ee"`. No extra clipping
is applied. Success and action-budget checks can stop execution mid-chunk.

Every episode resets the service and seeds Python/NumPy/Torch. Noise uses the
upstream MD5 seed function with `(env_rank=0, rollout_id=manifest_seed,
step_id=executed_action_count)`, so results are independent of batch scheduling.
This explicitly replaces upstream's rollout ordinal with the benchmark seed.

Evidence includes full denormalized delta predictions, decoded absolute chunks,
executed actions, native and transformed initial EE states, measured joints/poses,
request timings, videos, source/asset identities, oracle qualification and terminal
verdicts. The shared summarizer and video viewer recognize `xwam` output directories.

## Validation

```bash
conda run --no-capture-output -n RoboTwin python -m unittest discover -s tests/xwam -v
bash scripts/eval.sh --policy xwam --output-dir /tmp/xwam-plan --dry-run
```

CPU checks cover noncommuting rotations, translations, cumulative grippers,
reset/seed isolation, protocol rejection and partial-chunk execution evidence.
Twenty randomized comparisons with the pinned official deployment code matched
state transforms exactly and decoded actions within 2.3e-16.

On 2026-11-04, the official SFT checkpoint loaded strictly on an RTX A6000 and
completed the first manifest block of `press_lift_stapler`: seed 110000 (Press)
failed at the 250-action budget; seed 110001 (Lift) succeeded at action 85. Both
passed oracle qualification, with no execution errors. All saved delta/absolute
action arrays and all 251/86 video frames were checked. Warm 32-action predictions
took a median 1.66 seconds; observed model GPU memory was about 27 GiB.

This two-episode pilot establishes a working integration and is not a full-suite
score. Local evidence is at `/Data/robotwin-if/evaluations/xwam-pilot-20261104/`.

The full six-task evaluation finished on 2026-11-05 using all 460 episodes from
`seed-manifests/20-blocks`. Overall is **42.33%**, the unweighted mean of the six
task scores. See the [benchmark results](../../README.md#policy-results).
Local records and the final audit are under `/Data/robotwin-if/evaluations/wam-full-20261104/`.
