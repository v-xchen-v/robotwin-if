# Task manifests

`eval_cfg/if_tasks.yml` is the default six-task inventory; each versioned seed release has its own suite.yml. It contains exactly six single-axis diagnostics:

| Axis | Task name | Values / contrast |
|---|---|---|
| Verb-Select | `press_lift_stapler` | press / lift |
| Noun-Grounding | `pick_diverse_object` | noun-only target grounding |
| Attribute-Select | `attribute_select` | color / decal / shape / size |
| Arm-Select | `arm_select` | left / right |
| Sequence | `stack_sequence` | six bottom-to-top orders |
| Spatial-Direction | `place_relative` | left / right / on top |

`eval_cfg/all_tasks_plus_if.yml` is a compatibility list for callers that want one loop over the locked RoboTwin native 50 followed by the maintained IF six. Its final six entries must exactly equal `if_tasks.yml`; `tests/test_task_manifests.py` enforces this relationship.

The current task inventory is the six tasks above. Retired task names and Spatial front/back modes are rejected by the evaluator.
`pick_diverse_object` uses a locked four-noun production Unseen pool, covered by `tests/pick_diverse_object/test_pool.py`.

## Runtime installation

The bridge installs the current six tasks, six shared helpers and six instruction files. The locked nested runtime is the default:

```bash
bash scripts/bridge_tasks.sh --dry-run
bash scripts/bridge_tasks.sh
bash scripts/bridge_tasks.sh --check
```

For an external runtime, pass `--robotwin-dir PATH` or set `ROBOTWIN_DIR`. A non-locked/unknown target commit or locally modified compatibility-contract file is rejected by default and requires explicit `--allow-compatible-commit`; static RoboTwin API checks always remain mandatory. The target-side `.robotwin-if-bridge.json` owns the 19 task/helper/instruction/config links, records source/target dirty provenance plus an exact linked-source digest, and makes stale cleanup and unbridge independent of the current source inventory. A target-scoped operation lock serializes bridge/check/unbridge transactions.

## Using the task inventory

Use `bash scripts/collect.sh` for expert previews and `bash scripts/eval.sh` for fixed-seed policy evaluation.
The launchers select the correct task config, including the Arm-specific config. See [Quickstart](../docs/quickstart.md).

## Fixed eval budgets

Task-local setup (including `_if_eval.py` for the existing tasks) applies these limits only after RoboTwin initializes an eval-mode task; upstream `_eval_step_limit.yml` is not modified.

| Task | Policy action limit |
|---|---:|
| `press_lift_stapler` | 250 |
| `pick_diverse_object` | 400 |
| `attribute_select` | 400 |
| `arm_select` | 400 |
| `stack_sequence` | 1200 |
| `place_relative` | 400 |

These are analog-derived runtime budgets, not seed manifests or benchmark metrics. Oracle trajectory frame maxima support their relative ordering but do not measure policy calls; published evaluations use these fixed action budgets.

## Episode seed manifests

The user-facing generation, validation, resume, and evaluator-consumption guide is [`docs/seed-manifest-usage.md`](../docs/seed-manifest-usage.md).

The YAML files in this directory are **task inventories**. A generated seed manifest is a separate, flat JSON file selecting exact episodes for one task:

```json
{
  "schema_version": 1,
  "task": "arm_select",
  "task_config": "demo_clean",
  "seeds": [100000, 100001, 100002, 100003]
}
```

The native evaluator increments candidate episode seeds and silently skips seeds whose oracle check fails until it accumulates the requested number of accepted episodes. That remains unchanged and is useful for raw tasks or development smoke tests, but it can change one IF mode's denominator more than another.

Formal IF results instead replay one precomputed list shared by every policy. `tools/generate_if_seed_manifest.py` probes every exact seed once and accepts/rejects complete balance blocks; `tools/validate_if_seed_manifest.py` checks the flat list without importing RoboTwin or SAPIEN. The canonical contracts are:

| Task | Balance block | Same-scene structure |
|---|---:|---|
| `press_lift_stapler` | 2 | one press/lift pair; all initial RGB/state arrays identical |
| `pick_diverse_object` | 2 | seen/unseen are independent scenes |
| `attribute_select` | 8 | four independent two-seed axis pairs |
| `arm_select` | 2 | one left/right pair |
| `stack_sequence` | 6 | one six-order scene |
| `place_relative` | 3 | offsets 0, 1, 4 in one five-slot scene seed |

Example pilot generation and independent validation:

```bash
python tools/generate_if_seed_manifest.py \
  --all --task-config demo_clean \
  --accepted-blocks 2 --max-candidate-blocks 20 \
  --output-dir outputs/seed-candidates

python tools/validate_if_seed_manifest.py \
  --require-evidence outputs/seed-candidates
```

The adjacent `.generation.json` file is audit evidence, not part of the evaluator input. It binds the accepted list by SHA-256 and records source/target commits, linked-source digest, exact task-config YAML SHA-256, and whole-block rejections. An external evaluator only loops over `seeds`; it must not sort, deduplicate, drop, increment, replace, or silently fall back when an explicit seed fails. Accepted blocks may have gaps because failed candidate blocks are omitted as a whole.
