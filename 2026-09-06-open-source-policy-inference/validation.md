# X-VLA raw → IF smoke validation

Date: 2026-09-06

The client connected to the user's existing X-VLA service at `http://127.0.0.1:8010`. Simulation ran in the `RoboTwin` Conda environment on CUDA GPU 1, independently of the model environment. No new server or checkpoint download was started by this validation.

| Task | Seed | Instruction | Result | Actions / limit |
|---|---:|---|---|---:|
| raw `click_bell` | 2000 | `click bell` | success | 56 / 400 |
| IF `arm_select`, left | 100000 | `Have the left arm take the block.` | success | 101 / 400 |
| IF `arm_select`, right | 100001 | `Use the right arm to retrieve the block.` | failure at action limit | 400 / 400 |

The native task passed first. Then the IF runner consumed the first complete left/right block from `seed-manifests/if-ext-v1-100-per-mode/arm_select.json`. All three exact seeds passed oracle qualification, were reset for policy control, and produced policy outcomes. No seeds were skipped or replaced. IF inference used generated `unseen` instructions; native inference used the upstream client's task-name instruction convention.

The IF pair's initial head/left/right RGB images and 20D proprioception are byte-identical. Left finished with `lifted=true`, `arm_match=true`, and lift delta about 0.0500 m. Right finished with both signals false and lift delta about 0.00264 m. Right's failure is retained; one episode per mode cannot establish a systematic policy bias or success-rate estimate.

## Evidence

- [Raw summary](../../outputs/policy-eval/raw-smoke-001/xvla/click_bell/summary.json), [raw episode result](../../outputs/policy-eval/raw-smoke-001/xvla/click_bell/click_bell_ep2000_result.json), [raw video](../../outputs/policy-eval/raw-smoke-001/xvla/click_bell/click_bell_ep2000_1.mp4).
- [IF summary](../../outputs/policy-eval/smoke-blocks1/xvla/arm_select/summary.json), [left result](../../outputs/policy-eval/smoke-blocks1/xvla/arm_select/arm_select_ep100000_result.json), [left video](../../outputs/policy-eval/smoke-blocks1/xvla/arm_select/arm_select_ep100000_1.mp4), [right result](../../outputs/policy-eval/smoke-blocks1/xvla/arm_select/arm_select_ep100001_result.json), [right video](../../outputs/policy-eval/smoke-blocks1/xvla/arm_select/arm_select_ep100001_0.mp4).
- Each task directory also has `run.json`, `resolved_config.json`, `console.log`, and `results.jsonl`. Episode files use the flat `<task>_ep<seed>` prefix, matching `smoke-blocks1/cogact/arm_select`: `_summary.json`, `_status.json`, `_timings.json`, `_action_logs.json`, `_instruction.txt`, `_step0000.png`, `.log`, and `_1.mp4` / `_0.mp4`. Additional `_result.json`, `_oracle.json`, `_initial_observation.npz`, `_actions.npz`, and `_diagnostics.json` preserve X-VLA-specific evidence.
- Raw inference returned two 30-action model chunks; 56 decoded actions were executed. Left used four chunks and 101 executed actions; right used fourteen chunks and 400 executed actions. Chunk tails were stopped at task success or the action budget.

The new directories are offline exports of `xvla-click-bell-001` and `xvla-arm-select-001`, not new rollouts. Original directories and the CogACT reference are unchanged. Each `conversion.json` records source file hashes and conversion provenance; copied `run.json` files retain the original launch metadata and paths. Old per-step environment/total timings were not captured and are explicitly null. Request latencies are charged to the first action of each chunk. Uncollected generic grasp/lift summary fields are null; task-specific final signals remain available. Legacy videos retain their original head-only frames; initial PNGs show the saved head/left/right views. Future evaluations record per-step timing and three-view video directly.

Output validation: all three exports match the reference summary keys and action-log structure. Their detailed results, NPZ traces and video bytes match the originals; video counts remain 57, 102 and 401. Source and CogACT reference hashes are unchanged. The expanded 11-test client/runner suite covers success/failure/error artifacts, timing allocation, chunk tails, offline conversion and refusal to overwrite. Ruff and whitespace checks passed. No GPU/model rerun was needed for this format change.

## Implementation findings

`policies/xvla/client.py` preserves the released checkpoint's training/client EE6D convention. RoboTwin exposes wxyz, while upstream feeds the raw four numbers through SciPy's default codec and inversely decodes them before control. The adapter deliberately matches that numeric mapping. Gripper mapping and commanded-pose feedback also follow the upstream client; each episode resets client feedback.

`arm_select` previously initialized `_init_box_z` only in `play_once`. A fresh policy scene therefore had no lift baseline and could never pass `check_success()`. The task now captures the settled initial box height in `setup_demo`, without changing thresholds, mode routing, geometry, or the oracle trajectory. Tests show a policy can pass without calling the oracle, wrong-arm lifts still fail, and a new episode clears the previous success state. Bridge metadata was refreshed with no link additions/removals; its 18 owned links pass `--check` with the existing compatible-runtime opt-in.

Validation: 9 client/runner tests, 3 policy-success tests, and 18 existing eval-step-limit tests passed (30 total). Ruff and whitespace checks passed. Saved raw/left action traces and video metadata were independently read back; right evidence was retained through normal episode finalization.

## Reproduction and limits

Commands and argument meanings are in [the policy README](../../policies/xvla/README.md). Use a new output directory for each run. The runs use `demo_clean`, `feedback=commanded`, gripper threshold 0.7, and 10 denoising steps.

This is integration smoke, not a production benchmark. The HTTP API cannot attest checkpoint identity or control server RNG; checkpoint labels are user-declared. Local runtime/config dirty state and hashes are recorded, and the IF initialization fix changes the task-source digest relative to the published seed release. The exact IF seeds were requalified in this runtime, but the original release is not rewritten or represented as a new formal benchmark release. Client code hashes in each run describe the file versions at launch; subsequent mode guards and additional provenance reporting are covered by unit tests.
