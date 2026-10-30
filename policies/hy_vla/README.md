# Hy-Embodied-0.5-VLA RoboTwin inference

Checkpoint: [`tencent/Hy-Embodied-0.5-VLA-RoboTwin`](https://huggingface.co/tencent/Hy-Embodied-0.5-VLA-RoboTwin), revision `bd7bba6f5934ad62293a2a34f74760c6a3ef2ff8`. [Official source](https://github.com/Tencent-Hunyuan/Hy-Embodied-0.5-VLA/tree/af57e7507ec5964b52fdf6296741e553cbcd3288) is pinned to `af57e7507ec5964b52fdf6296741e553cbcd3288`. The full checkpoint contains about 4.53B BF16 parameters, including the MoT backbone, action expert and MEM video encoder.

## Install and start

Run from the repository root:

```bash
export ROBOTWIN_IF_HOME="${ROBOTWIN_IF_HOME:-$HOME/.local/share/robotwin-if}"
bash policies/hy_vla/setup_env.sh
conda run --no-capture-output -n RoboTwin python -m pip install \
  -r policies/hy_vla/requirements-client.txt

conda run --no-capture-output -p "$ROBOTWIN_IF_HOME/envs/robotwin-if-hy-vla" \
  python policies/hy_vla/download_checkpoint.py \
  --output-dir "$ROBOTWIN_IF_HOME/checkpoints/Hy-Embodied-0.5-VLA-RoboTwin"

conda run --no-capture-output -p "$ROBOTWIN_IF_HOME/envs/robotwin-if-hy-vla" \
  python policies/hy_vla/serve.py \
  --checkpoint-dir "$ROBOTWIN_IF_HOME/checkpoints/Hy-Embodied-0.5-VLA-RoboTwin" \
  --gpu 1 --port 8015 \
  --output-dir outputs/policy-eval/servers/hy-vla-002
```

Setup creates a dedicated Python 3.10 environment under `$ROBOTWIN_IF_HOME/envs` (default storage root: `$HOME/.local/share/robotwin-if`). Torch 2.7.1 / torchvision 0.22.1 CUDA 12.8, Transformers 4.57.0, timm 1.0.21 and FlashAttention 2.7.4.post1 follow the official `uv.lock`. FlashAttention uses the upstream prebuilt Linux/Python 3.10/CUDA 12/Torch 2.7/CXX11-ABI wheel; the import check also runs its CUDA kernel. Transformers 4.57.0 is yanked on PyPI, but explicitly pinned to match upstream. Only inference dependencies are installed. Direct versions are pinned and `pip freeze` records the resolved environment.

Use `ROBOTWIN_IF_HOME` to select a writable storage root, or `--env-prefix` and `--source-dir` to override individual locations. The prefix must be dedicated to `robotwin-if-hy-vla`; use that same prefix in every `conda run -p` command. Conda package cache and temporary downloads default to the environment's parent directory. Weights require about 8.5 GiB. The RoboTwin simulator runs in its existing separate environment. For an existing `/Data/robotwin-if` installation, set `ROBOTWIN_IF_HOME=/Data/robotwin-if` to reuse it; no automatic migration is performed. See the [Quickstart](../../docs/quickstart.md) for simulator setup and the six-task evaluation entry point.

The downloader and server verify `model.safetensors` against the pinned LFS SHA-256 `3bd6c16225f905a298340489d519498d4e5ecf5bcdd28a5c1df63e29894fef60`, and verify `norm_stats.pkl` against `ce81158fb16dfcb16caa80ba33dd277d07b81e40de96d959616447d614feae41` **before reading the pickle**. Config/tokenizer assets are hashed as well. All runtime assets are local; Hub offline mode is enabled.

[`patch_source.py`](patch_source.py) applies checked, idempotent source changes to require `strict=True`, remove the unused expert language output head exactly as official `train.py` does, and cast to the released BF16 precision before safetensors validates parameter keys, shapes and dtypes. It also combines GPU transfer with the BF16 cast. Every remaining parameter must load; no random missing weights are accepted. The patch and source revision are saved in server metadata. Action decoding, history selection and attention follow the official implementation. The service's `RecordedWrapper` subclass records the original model tokens and full decoded targets while calling the official decoder.

## Per-step protocol and action semantics

The default endpoint is `ws://127.0.0.1:8015`; HTTP `/healthz` is available after model initialization. The handshake reports checkpoint identity, source patch, precision, action layout and history/caching settings. One client can connect at a time. Each connection must reset before predicting; resets and disconnects clear action queues and all camera history. A failed request invalidates the episode and requires another reset. Each reset seeds Python, NumPy and Torch; full kernel determinism is not enforced.

`HyVLAClient.reset(instruction, seed)` binds the actual task instruction. `predict(observation)` must be called **once before every environment action**, including cached steps, and returns one native RoboTwin 16D absolute EE action. This preserves upstream's history timing. The next request must have the next consecutive step index. Raw uint8 RGB arrays and state are transported losslessly with the repository's existing NumPy/MessagePack envelope.

- Input cameras are head, left wrist and right wrist, in that order. The wrapper stores each pre-action observation. Every model call uses six frames at offsets `[-25, -20, -15, -10, -5, 0]` in executed-action steps. Slots before episode start are filled with zero-valued RGB pixels. They become black (`-1`) after the official image normalization.
- Official image processing converts RGB to `[0, 1]`, resizes with padding to 224×224, then maps to `[-1, 1]`. The MEM encoder consumes `(B, 6, C, H, W)` for each camera. Camera history continues to update during cached actions.
- State layout is `[left xyz, left quaternion wxyz, left gripper, right xyz, right quaternion wxyz, right gripper]`. It uses measured `endpose`, converts wxyz to xyzw, encodes the first two **rows** of each rotation matrix, and applies the checkpoint's 20D mean/std normalization. The model pads to 32D.
- Language follows official `prepare_language`: normalize whitespace/underscores, append `<｜hy_Assistant｜>` if absent, and tokenize to a maximum length of 64. No replacement task-name prompt is used in validation.
- The checkpoint config has `chunk_size=n_action_steps=40`. Those **40×20 model tokens comprise 20 relative and 20 absolute predictions**, with per-horizon mean/std statistics. Relative poses are composed in each arm's current local EE frame. The official `rel_abs` decoder blends relative and absolute positions/grippers 1:1 and quaternions with SLERP at 0.5, producing **20×16 absolute EE targets**.
- Use the official `exc_action_size=7`: execute the first seven targets, then replan. No extra 3× interpolation is added; the card's 3× downsampling describes training data. UMI coordinate/gripper conversion is disabled as in `deploy_policy.yml`. Continuous grippers are passed through without binarization.
- Execute with `env.take_action(action, action_type="ee")`, stopping on success or the task action limit. The model uses its official FlashAttention vision/MEM path and eager dual-tower attention, with 10 flow-matching denoising steps.

## Run the benchmark

Keep the model server running, then use the RoboTwin environment from the repository root:

```bash
bash scripts/eval.sh --policy hy_vla --task press_lift_stapler --blocks 1 \
  --output-dir outputs/policy-eval/first-run
bash scripts/eval.sh --policy hy_vla --output-dir outputs/policy-eval/full-run
```

The full run uses 20 blocks per task and 460 exact-seed episodes. Choose fresh output directories.
See [evaluation](../../docs/formal-policy-evaluation.md) for options and scoring,
and [published results](../../result/README.md) for the frozen six-task benchmark.


## Checks and preflight

```bash
conda run --no-capture-output -n RoboTwin \
  python -m unittest discover -s tests/hy_vla -p 'test_client.py'
conda run --no-capture-output -p "${ROBOTWIN_IF_HOME:-$HOME/.local/share/robotwin-if}/envs/robotwin-if-hy-vla" \
  python -m unittest discover -s tests/hy_vla -p 'test_runtime.py'
ruff check policies/hy_vla tests/hy_vla
```

Ten tests cover native quaternion/gripper order, fresh images during cached steps, reset/protocol errors, action budgets and retained failures, official local-frame rel+abs geometry, and official six-frame history assembly/reset, and strict loading that rejects missing inference weights. Runtime tests use the real wrapper and decoder with synthetic outputs, without loading model weights.

`preflight.py --observation <npz> --instruction <text> --output-dir <new-directory>` uses a saved real observation containing native 16D `proprio`. It repeats eight steps with the same observation and seed, records both model calls in each repeat, compares reset reproducibility, and checks reset-required/single-client/invalid-reset behavior. This is a protocol diagnostic; task success requires the actual closed-loop evaluations above.


Checkpoint identities and full inference evidence: [results](../../result/README.md) · [download](../../docs/download-results.md).
