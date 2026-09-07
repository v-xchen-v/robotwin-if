# LingBot-VA integration and validation

Date: 2026-09-06

Source: `Robbyant/lingbot-va`, revision `7c6ffa9bfc4b83582cafc860fab4c82cc7deeeeb`.
Checkpoint: `robbyant/lingbot-va-posttrain-robotwin`, revision `8c9dea8abbc5c91cc9e18bc3264b8915083bbe70`, downloaded to `/Data/robotwin-if/checkpoints/lingbot-va-posttrain-robotwin` (22.7 GiB). No HF token was needed. Most shards downloaded over HTTP; the last VAE shard completed using the new environment's Xet downloader after resuming.

The separate `robotwin-if-lingbot-va` Conda environment uses Python 3.10.16, torch 2.9.0+cu126, torchvision 0.24.0+cu126, diffusers 0.36.0 and transformers 4.55.2. Dependency, import and CUDA tensor checks passed. The existing RoboTwin environment received only websockets 15.0.1 and msgpack 1.1.1 for transport. The X-VLA environment/server remains available.

## Implementation

[`policies/lingbot_va`](../../policies/lingbot_va/README.md) contains setup, pinned dependencies, download, server, client, evaluator and output code. The official `VA_Server` model runs directly on one GPU without distributed sharding. Its supported Torch attention backend is selected by the upstream loader. One narrowly scoped source patch makes the otherwise unconditional FlashAttention import optional; model math and weights are unchanged. Source diff and inference settings are saved in server/run metadata. Loading reports unused legacy `patch_embedding` weights (the current architecture uses `patch_embedding_mlp`) and an ignored VAE `clip_output` config field; the upstream loader warnings remain in server logs.

The adapter preserves official initial-pose-relative 16D EE actions, numeric SciPy quaternion composition, first conditioning-frame skipping and four real keyframes per generated latent frame. KV state is updated only after complete executed chunks and cleared by a remote reset at each episode. The server permits one client at a time and seeds Python/NumPy/Torch per reset. Generic config, manifest/instruction and filename helpers are temporarily reused from the X-VLA integration; full common-layer extraction remains pending.

## Raw gate

- Task `click_bell`, exact seed 2000, `demo_clean`, generated seen instruction: `Press the center top of the flat-topped bell.`
- Oracle qualified, scene recreated, policy **succeeded in 58 / 400 actions**, 3 predicted chunks, 263.67 seconds total.
- [Episode result](../../outputs/policy-eval/raw-smoke-001/lingbot_va/click_bell/click_bell_ep2000_result.json), [video](../../outputs/policy-eval/raw-smoke-001/lingbot_va/click_bell/click_bell_ep2000_1.mp4), [run metadata](../../outputs/policy-eval/raw-smoke-001/lingbot_va/click_bell/run.json).
- Server `lingbot-va-001` ran on GPU 1 with CPU offload. Reset text encoding took 143.64 seconds on the Xeon Gold 5118, which lacks native BF16 support. The raw episode completed normally before this owned server was stopped. The server was then restarted as `lingbot-va-002` with `--no-offload` for IF validation; the checkpoint, guidance and denoising steps are unchanged. See the [server transition record](../../outputs/policy-eval/raw-smoke-001/lingbot_va/click_bell/server_transition.json).

## IF gate

Completed `arm_select`, the first complete block `[100000, 100001]` from `seed-manifests/if-ext-v1-100-per-mode/arm_select.json`, generated unseen instructions, no skips or substitutions: **2/2 success**.

| Mode | Seed | Instruction | Result | Actions / chunks | Elapsed |
|---|---:|---|---|---:|---:|
| left | 100000 | `Have the left arm take the block.` | success | 80 / 3 | 93.13 s |
| right | 100001 | `Use the right arm to retrieve the block.` | success | 90 / 4 | 63.54 s |

Both episodes passed oracle qualification before fresh policy setup. Final `arm_match` and `lifted` signals are true for both; lift deltas are 0.050095 m and 0.050021 m. Initial head/left/right RGB images, EE proprioception and joint state match exactly between modes. Each episode reset the remote caches. Left's full-GPU reset took 0.568 s; individual RPC timing is saved rather than inferred from total wall time.

Evidence: [run summary](../../outputs/policy-eval/smoke-blocks1/lingbot_va/arm_select/summary.json), [left result](../../outputs/policy-eval/smoke-blocks1/lingbot_va/arm_select/arm_select_ep100000_result.json), [left video](../../outputs/policy-eval/smoke-blocks1/lingbot_va/arm_select/arm_select_ep100000_1.mp4), [right result](../../outputs/policy-eval/smoke-blocks1/lingbot_va/arm_select/arm_select_ep100001_result.json), [right video](../../outputs/policy-eval/smoke-blocks1/lingbot_va/arm_select/arm_select_ep100001_1.mp4). The same checkpoint served from GPU 1 in full-GPU mode; simulation used GPU 0. The owned server remains available at `ws://127.0.0.1:8011` after validation.

## Checks

Seven simulator-free tests passed, including a direct codec comparison against the pinned official client's functions. Ruff, shell syntax and whitespace checks passed. All three saved action traces were re-decoded from the original predicted tensors and initial poses: all 58 / 80 / 90 executed actions match. Videos decode with 59 / 81 / 91 frames at 960×240; summary keys cover the CogACT reference schema. Both evaluators exited 0, and all expected seeds were recorded. Generic uncollected grasp/lift diagnostics are null, while task-specific signals and original predicted/actual executed actions are retained.

These are integration smoke runs, not a benchmark performance estimate. Runtime and task/config source hashes are recorded; CPU-offload differs between raw and IF and is explicitly recorded. Full-suite evaluation, common-layer refactoring and external policy bridging remain separate work.
