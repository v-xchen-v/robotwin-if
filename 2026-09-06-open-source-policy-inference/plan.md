# Open-source policy inference plan

Date: 2026-09-06

Branch: `feat/open-source-policy-inference`

Status: In progress. Both initial policies completed raw → IF smoke validation on 2026-09-06. X-VLA: click_bell 1/1, arm_select 1/2 (left success, right action-limit failure); see [X-VLA evidence](validation.md). LingBot-VA: click_bell 1/1, arm_select 2/2 (both arms); see [LingBot-VA evidence](lingbot-va-validation.md). Both have separate environments, clients and the unified episode output format. Shared-layer extraction and external policy bridging remain pending.

Implement inference for one or two open-source policies on RoboTwin-IF tasks, refactor the working integrations into a common layer, add more policies incrementally, then bridge the same implementation into a raw RoboTwin repository so native tasks can use it too.

**Required validation order for every policy: one raw RoboTwin task → one selected RoboTwin-IF task.** Apply this order to the initial adapters, every later policy, and validation after the shared-layer refactor. Full-suite evaluation follows these two gates.

Output convention: use `outputs/policy-eval/<run>/<policy>/<task>/` and the flat `<task>_ep<seed>` artifacts from `smoke-blocks1/cogact/arm_select`. Additional policy diagnostics are allowed; unavailable measurements must be marked explicitly. X-VLA now emits this format, and its existing smoke evidence has been exported without rerunning inference; see [output documentation](../../policies/xvla/README.md#输出格式).

## Starting point

- The maintained IF suite contains seven tasks in [`eval_cfg/if_tasks.yml`](../../eval_cfg/if_tasks.yml).
- RoboTwin already loads policies through `get_model(usr_args)`, `eval(TASK_ENV, model, observation)`, and `reset_model(model)`. See its [`Your_Policy` template](../../third_party/robotwin/policy/Your_Policy/deploy_policy.py) and [`evaluation harness`](../../third_party/robotwin/script/eval_policy.py).
- [`scripts/bridge_tasks.sh`](../../scripts/bridge_tasks.sh) exposes IF tasks to nested or external RoboTwin checkouts. It currently installs task files only; policy installation is future work.
- [`seed-manifests/if-ext-v1-100-per-mode/`](../../seed-manifests/if-ext-v1-100-per-mode/README.md) contains seven fixed manifests covering 27 modes and 2,700 episodes per policy. Reuse these assets after checking runtime, task-source, and config provenance. Their generation used a compatible RoboTwin revision different from the default bridge lock.
- Native evaluation dynamically skips invalid candidate seeds. Formal IF evaluation needs an explicit manifest replay path and per-mode results; policy discovery alone does not provide these.
- Earlier documentation places inference in an external CogACT/X-VLA integration. This plan expands this repository to maintain inference adapters and shared integration code. Training and fine-tuning remain outside scope, and IF evaluation episodes must remain excluded from training data.
- Policy integrations live under [`policies/<policy_name>/`](../../policies/README.md). X-VLA has [`setup_env.sh`](../../policies/xvla/setup_env.sh), pinned inference requirements, [`client.py`](../../policies/xvla/client.py), [`eval.py`](../../policies/xvla/eval.py), and setup/server/evaluation documentation. The separate `robotwin-if-xvla` environment passed local checks with Python 3.10.21, torch 2.1.2+cu121, torchvision 0.16.2+cu121, Transformers 4.51.3, model/processor imports, 20D EE6D, and a CUDA tensor operation on RTX A6000. The user then started the official server; the RoboTwin client completed the raw and selected IF smoke runs recorded below.

## Phase 1 — Run one or two policies end to end

Start with the official **`2toINF/X-VLA-RoboTwin2`** checkpoint. The user nominated **`robbyant/lingbot-va-posttrain-robotwin`** (ModelScope: `Robbyant/lingbot-va-posttrain-robotwin`) as the second policy, now being integrated under [`policies/lingbot_va`](../../policies/lingbot_va/README.md). Use the second implementation to exercise real differences in dependencies, inputs, actions, and serving before extracting the common layer. Existing RoboTwin adapters such as `pi0`, `pi05`, and `openvla-oft`, plus CogACT, remain later candidates.

### First policy: X-VLA-RoboTwin2

| Item | Selected baseline |
|---|---|
| Checkpoint | [`2toINF/X-VLA-RoboTwin2`](https://huggingface.co/2toINF/X-VLA-RoboTwin2) |
| Implementation | [`2toinf/X-VLA`](https://github.com/2toinf/X-VLA) |
| Embodiment | Agilex, dual arm |
| Training | RoboTwin2 coordinated manipulation; 50 demonstrations per task, per upstream README |
| Foundation | X-VLA-Pt, as described in the upstream model-family documentation |
| License | Apache-2.0 for upstream code and the checkpoint model card |
| Reported native benchmark results | Easy **70.0%**, Hard **39.0%**, per the RoboTwin2 evaluation guide |
| Model action representation | `ee6d`, 20 dimensions: left arm 10D + right arm 10D |
| Prediction horizon | Checkpoint config declares `num_actions: 30`; validate the server response shape |
| Deployment | Official HTTP inference server in an isolated X-VLA environment; RoboTwin client in its simulator environment |

The reported success rates describe the upstream native-task evaluation settings, not IF success rates or an acceptance threshold for this integration. Any comparison with another policy must align checkpoint, task set, and evaluation settings; this plan makes no causal claim about leaderboard differences.

Follow [`evaluation/robotwin-2.0/README.md`](https://github.com/2toinf/X-VLA/blob/6bc2513f5f1cbec715cc668b414392a6cae5c671/evaluation/robotwin-2.0/README.md). The documented server command, run from the X-VLA checkout in its environment, is:

```bash
python -m deploy --model_path 2toINF/X-VLA-RoboTwin2
```

Pin the X-VLA source and HF checkpoint revisions before collecting evidence. Documentation/code inspection on 2026-09-06 used source revision `6bc2513f5f1cbec715cc668b414392a6cae5c671`; the HF checkpoint revision still needs to be pinned. The HF model card contains generic WidowX/BridgeData examples, so use the RoboTwin-specific guide, client, and checkpoint config for this integration.

### X-VLA observation and action contract

The official RoboTwin client sends `domain_id: 6`, the language instruction, head/left/right camera RGB images as `image0`/`image1`/`image2`, and 20D end-effector proprioception to `POST /act`. Its additional `front_camera` read is for local video recording and is not part of the model request; it should not become a required model input. Verify camera availability, pose frames, and processing against our runtime/config.

The dual-arm layout, for both pose input and predicted action, is:

| Slice | Meaning |
|---|---|
| `0:3` | Left EE position |
| `3:9` | Left rotation in 6D representation |
| `9` | Left gripper channel |
| `10:13` | Right EE position |
| `13:19` | Right rotation in 6D representation |
| `19` | Right gripper channel |

Each arm contributes `3 + 6 + 1 = 10` dimensions. In a single-arm embodiment, the unused 10D block is zero-padded. **For Agilex dual-arm evaluation, both blocks carry real actions.** A single-arm task on the dual-arm Agilex robot still uses the dual-arm representation.

The reference client treats predictions as absolute EE targets and converts 20D EE6D into the 16D layout accepted by `take_action(..., action_type='ee')`: `[left_xyz, left_quaternion, left_gripper, right_xyz, right_quaternion, right_gripper]`. Do not pass 20D model output directly into RoboTwin or treat it as joint positions.

Before the first rollout, validate these implementation details against recorded observations and the locked runtime:

- **Rotation:** verified against the training handler and client. Both feed RoboTwin's raw `wxyz` numbers directly into SciPy's default `xyzw` codec. Preserve this checkpoint-specific numeric convention and inverse decode; swapping components only at inference would change the learned input space. First-two-column interleaving, asymmetric quaternion roundtrips, and arm ordering are tested.
- **Gripper:** the reference transforms observed values with `1 - 2*g` and maps predicted probabilities with `1 - 2*(p > 0.7)`. The official EE6D action hub masks proprio gripper channels and applies sigmoid to predicted gripper logits. Confirm the pinned server behavior and the runtime's open/close range; apply each transformation exactly once and test both states. These settings belong to the X-VLA adapter, not every policy.
- **Feedback:** initial runs use the reference's commanded-pose feedback, with current images and gripper observations. The adapter exposes an explicitly recorded `measured` alternative for later diagnosis; no comparison or claim of necessity has been made yet.
- **Chunk execution:** preserve the checkpoint's prediction horizon, but use the selected task's action-call budget and check termination between executed actions. Use native task limits for the raw-task gate and IF limits for the IF gate; the reference's fixed ten-chunk rollout limit must not silently replace them.
- **Transport:** make the server address, request timeout, and inference settings explicit; reset local episode state and clear pending chunks between episodes. Server errors must produce an incomplete/error result for the exact seed rather than synthetic fallback actions.

Use the official client for model-specific preprocessing and postprocessing, while retaining our exact-seed replay and instruction-selection requirements. Keep the generic layer capable of other declared action representations; X-VLA's 20D EE6D is the first adapter's format, not a mandatory format for every future policy.

References: [upstream model table](https://github.com/2toinf/X-VLA/blob/6bc2513f5f1cbec715cc668b414392a6cae5c671/README.md), [RoboTwin client](https://github.com/2toinf/X-VLA/blob/6bc2513f5f1cbec715cc668b414392a6cae5c671/evaluation/robotwin-2.0/client.py), [action hub](https://github.com/2toinf/X-VLA/blob/6bc2513f5f1cbec715cc668b414392a6cae5c671/models/action_hub.py), [checkpoint config](https://huggingface.co/2toINF/X-VLA-RoboTwin2/blob/main/config.json).

### Implementation and validation

Every policy must pass the following gates in sequence:

| Gate | Task and purpose | Required evidence |
|---|---|---|
| 1. Raw RoboTwin | Choose one native task supported by the checkpoint, using the original task implementation and a compatible embodiment/config. Provisional X-VLA choice: `click_bell`. Validate model loading, observations, language, action conversion, and closed-loop execution. | A complete policy-driven rollout with the task's success check passing, plus command/config, checkpoint identity, seed, logs, and video. Record all attempted episodes and failures. |
| 2. RoboTwin-IF | After gate 1 passes, select one maintained IF task. Provisional X-VLA choice: `arm_select`, replaying one complete left/right balance block from its fixed manifest. Reuse the same checkpoint and inference adapter. | Complete results for the selected block, at least one successful policy-driven episode on the selected task, recorded instructions/modes, logs, and video. Preserve failed episodes and report both modes separately. |

Here, “runs successfully” requires actual task completion by the policy, as well as a working inference loop. A server response, a moving robot, or an episode ending without an exception is useful debugging evidence but does not pass the task gate. This is a small integration check, not a claim about benchmark success rate or a requirement for 100% success across IF modes. If a gate has no successful episode, retain its failed/pending status and investigate the adapter or checkpoint's capabilities before declaring the policy validated.

Choose and record the task/config/seed set before each validation attempt. If diagnosis requires a change, record the change and preserve previous outcomes. Later policies may use a different suitable raw/IF task pair, but the two-gate order is mandatory. First rerun evidence should also exercise episode reset.

The raw-task gate can run a native task in the existing nested RoboTwin runtime through the policy's client/entrypoint, without depending on IF task installation. It is required during initial policy development. Phase 4 separately packages installation and reuse in an external raw RoboTwin checkout; it does not postpone native-task validation until then.

For each initial policy:

1. Record the upstream repository/revision, code and checkpoint licenses, checkpoint source, normalization statistics, required hardware, and exact environment setup. Check that the checkpoint supports the relevant robot and behavior repertoire.
2. Implement a concrete adapter: model loading, camera/state/instruction preprocessing, prediction, action conversion, episode reset, and cleanup. Reuse upstream inference code where suitable.
3. Keep dependencies isolated per policy where needed. Start X-VLA with its official separate inference server; choose local or server execution independently for subsequent policies, without requiring a universal serving protocol at this stage.
4. Add a repeatable evaluation entrypoint and explicit configuration for checkpoint, task, task config, instruction split, device, inference settings, seed manifest, and output directory.
5. Pass the raw-task gate first, then the selected IF-task gate. Expand to the seven maintained IF tasks only after both pass. Label smoke subsets separately from full benchmark runs and retain complete IF balance blocks.
6. Save per-episode results and rollout videos for both gates. Distinguish integration errors from unsuccessful policy behavior, preserving all outcomes and the evidence supporting each gate's status.

**Exit criterion:** each policy included in the initial milestone passes the raw-task gate followed by the selected IF-task gate, with correct instruction/observation/action handling, clean episode resets, and reproducible evidence. Start with X-VLA; prefer two validated integrations before settling the common interface. If only one is feasible initially, keep the interface provisional and validate it with the next policy before wider expansion.

## Phase 2 — Extract the common inference layer

Refactor the proven implementations, using their actual overlap to define the abstraction. Preserve their observed behavior with the same checkpoint, inputs, and inference settings; use suitable tolerances for stochastic models.

| Component | Responsibility |
|---|---|
| Policy adapter | Model-specific dependencies, loading, input transforms, normalization, prediction, and model state |
| Common policy contract | Load/configure, reset for an episode, predict an action or action chunk, and close resources |
| RoboTwin runtime adapter | Read observations/instructions, map declared actions to RoboTwin, execute chunks, and respect success/step limits |
| IF evaluation runner | Replay exact seeds, select reproducible instructions, apply IF contracts, and record per-episode/per-mode results |
| Configuration and discovery | Select a policy and validate its required settings without importing every policy's dependencies |

Define the input/output contract explicitly: required camera names, image layout/color/range, robot-state ordering and units, instruction text, action shape, arm/gripper ordering, absolute versus delta semantics, coordinate frames, and chunk length. Keep model-specific normalization in the adapter. Reject unsupported combinations before rollout.

The runtime adapter owns action execution and checks termination between actions in a chunk. Episode reset clears observation history, queued actions, and model/server state. IF task labels, oracle metadata, and success signals belong to the evaluator and must not become policy inputs.

The reusable policy/runtime code must not depend on the IF task inventory, seed contracts, or diagnostic signals. This boundary enables native RoboTwin reuse later. The first version only needs the capabilities exercised by the initial policies; add further capabilities when an integration requires them.

**Exit criterion:** the initial policies use the shared path with no duplicated rollout/action-execution logic, retain equivalent behavior after refactoring, and can be imported/configured without installing unrelated model packages. Rerun each policy's raw-task gate, then its selected IF-task gate through the shared implementation, retaining both sets of evidence.

## Phase 3 — Add more policies incrementally

- Prioritize additional policies by available checkpoints, relevant behavior coverage, and inference cost.
- Add each policy as an adapter with its own config, dependency instructions, and a reproducible smoke command.
- Validate that policy on one raw RoboTwin task first, then one selected IF task, before marking the adapter supported or expanding its evaluation coverage.
- Reuse the common runner and result format. Extend the contract only for a demonstrated requirement and rerun the existing adapters' relevant checks when doing so.
- Maintain a support table listing tested revisions/checkpoints, embodiment, required observations, action type, execution mode, and separate raw/IF gate statuses with task names and evidence links.

**Exit criterion:** an additional policy integrates mainly through its adapter and configuration, without another evaluation loop or policy-specific branches throughout the common runner, and passes its raw-task → IF-task validation sequence.

## Phase 4 — Bridge policies into raw RoboTwin

Expose the same adapters and common runtime layer to a separate compatible RoboTwin checkout. Keep the implementation maintained here; the target checkout receives thin integration entrypoints.

1. Provide a RoboTwin policy package exporting `get_model`, `eval`, and `reset_model`, delegating to the shared implementation. Supply deploy configuration and an invocation example using the native evaluator.
2. Add an explicit policy bridge/unbridge workflow, following the task bridge's target selection, compatibility checks, dry-run/check, collision preflight, ownership tracking, and safe removal behavior. Choose separate policy ownership state or a versioned extension during implementation; policy installation must not disturb task ownership.
3. Expose shared Python code through a documented package installation or owned link arrangement. Verify imports from the target checkout without depending on the developer's working directory.
4. Install under a distinct policy namespace so existing RoboTwin policy packages remain intact. Leave upstream tracked files unchanged.
5. For each policy exposed by the bridge, repeat its raw-task gate using the native evaluator with no IF task installation. After that passes, install the task bridge and repeat its selected IF-task gate in the same target using the manifest-aware runner. This verifies deployment of the already validated adapter.
6. Document installation, evaluation, checks, upgrades, and removal for both the nested runtime and an external raw checkout. Keep native dynamic evaluation available; formal IF runs still use the manifest-aware runner.

**Exit criterion:** a raw RoboTwin checkout passes the native-task → selected IF-task gates with the same policy implementation, and the bridge can be checked, rerun, and removed without changing upstream tracked files or leaving owned installation artifacts behind.

## Evaluation requirements across phases

- Validate each policy in order: raw-task success, then selected IF-task success. Store separate gate statuses; completing only the first gate does not mark IF support as validated.
- Formal runs preserve the exact manifest order and seeds. Never skip, replace, increment, or silently fall back from an explicitly supplied seed. A task failure or action-budget exhaustion stays in the denominator; an infrastructure failure marks the run incomplete.
- Select instruction text reproducibly, independently of policy RNG, and record the actual instruction and split. Default formal IF evaluation to `unseen`; keep `seen` sanity runs separately labeled.
- Record policy/checkpoint identity, source/runtime revisions and dirty provenance, config and manifest hashes, task, mode, episode seed, instruction, success/failure/error status, executed action count, timing, and artifact paths. Where stochastic inference is used, record its seed and settings.
- Report exact per-mode success counts and denominators with completion status. More detailed IF signals or gap metrics require an explicit supported signal contract; do not infer them from missing fields.
- Validate action conversion and chunk stopping with controlled observations/actions, test reset across episodes, and test exact-seed/error handling with a lightweight fake environment. Use real simulator rollouts to validate integration and checkpoint compatibility.
- For refactoring, compare the original and shared inference paths using fixed recorded inputs and controlled randomness, then rerun the raw-task → IF-task gates. For the bridge, test collisions, repeated installation, checks, and removal, and repeat those gates in a clean target.

## Suggested delivery order

1. X-VLA-RoboTwin2 adapter, official-server environment/config documentation, EE6D conversion validation, successful raw-task rollout, then minimal IF replay runner and successful selected IF-task validation.
2. Second policy adapter when feasible, with the same raw-task → IF-task evidence, exposing differences the shared contract must accommodate.
3. Shared inference/runtime refactor, stable result/config contracts, focused regression checks, and both task gates rerun for each initial policy.
4. Additional adapters, one at a time, each passing both gates before its support-table entry is marked validated.
5. Raw RoboTwin policy bridge, both task gates verified in the external checkout, and usage documentation.

X-VLA's initial implementation and smoke sequence are complete: native success followed by a complete IF block with one successful episode and one preserved failure. Next planned work is the second policy integration or additional X-VLA diagnosis/coverage. Do not infer full-suite readiness from these three episodes; formal checkpoint provenance, broader evaluation, common-layer extraction, and external policy bridging remain future milestones.
