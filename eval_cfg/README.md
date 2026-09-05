# Task manifests

`eval_cfg/if_tasks.yml` is the canonical machine-readable inventory of RoboTwin-IF tasks maintained by this repository. It contains exactly seven single-axis diagnostics:

| Axis | Task name | Values / contrast |
|---|---|---|
| Verb-Select | `bottle_verb` | pick / shake |
| Noun-Grounding | `pick_diverse_object` | noun-only target grounding |
| Attribute-Select | `attribute_select` | color / decal / shape / size |
| Arm-Select | `arm_select` | left / right |
| Sequence | `stack_sequence` | six bottom-to-top orders |
| Spatial-Direction | `place_relative` | left / right / front / back / on top |
| Grasp-Approach | `grasp_cube_approach` | top / side |

`eval_cfg/all_tasks_plus_if.yml` is a compatibility list for callers that want one loop over the locked RoboTwin native 50 followed by the maintained IF seven. Its final seven entries must exactly equal `if_tasks.yml`; `tests/test_task_manifests.py` enforces this relationship.

## Membership and readiness

A Python env or instruction JSON being present does not make a task active. Implementations retained for provenance or experiments—including `laptop_verb`, `operate_stapler`, `operate_tabletop`, `operate_mic_drawer`, and `smoke_click_bell`—are inactive because they are absent from `if_tasks.yml`.

Conversely, manifest membership describes the suite this repository maintains; it does not bypass task-specific release gates. `pick_diverse_object` is the maintained Noun-Grounding task, and its locked four-noun production Unseen pool is independently enforced by `tests/pick_diverse_object/test_pool.py` (currently 34/34).

## Runtime installation

The bridge inventory is contract-tested against this exact seven-task list; inactive source files are not installed. The locked nested runtime is the default:

```bash
bash scripts/bridge_tasks.sh --dry-run
bash scripts/bridge_tasks.sh
bash scripts/bridge_tasks.sh --check
```

For an external runtime, pass `--robotwin-dir PATH` or set `ROBOTWIN_DIR`. A non-locked/unknown target commit or locally modified compatibility-contract file is rejected by default and requires explicit `--allow-compatible-commit`; static RoboTwin API checks always remain mandatory. The target-side `.robotwin-if-bridge.json` owns the 18 env/helper/instruction links, records source/target dirty provenance plus an exact linked-source digest, and makes stale cleanup and unbridge independent of the current source inventory. A target-scoped operation lock serializes bridge/check/unbridge transactions.

## Using the task inventory

RoboTwin's locked collect/eval entry points are single-task. Bridge the task plugins, then loop over the selected task-name list:

```bash
bash scripts/bridge_tasks.sh
cd third_party/robotwin

for t in $(python3 -c "import yaml; print(' '.join(yaml.safe_load(open('../../eval_cfg/if_tasks.yml'))['tasks']))"); do
  bash collect_data.sh "$t" demo_clean 0
 done
```

For evaluation, pass each task name to the chosen policy's own `policy/<PolicyName>/eval.sh`; policy wrappers do not share one universal argument signature.

## Fixed eval budgets

The task-local `_if_eval.py` helper applies these limits only after RoboTwin initializes an eval-mode task; upstream `_eval_step_limit.yml` is not modified.

| Task | Policy action limit |
|---|---:|
| `bottle_verb` | 700 |
| `pick_diverse_object` | 400 |
| `attribute_select` | 400 |
| `arm_select` | 400 |
| `stack_sequence` | 1200 |
| `place_relative` | 400 |
| `grasp_cube_approach` | 400 |

These are analog-derived runtime budgets, not seed manifests or benchmark metrics. Oracle trajectory frame maxima support their relative ordering but do not measure policy calls; a future CogACT rollout must monitor truncation and update the central map plus its contract test if needed.

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
| `bottle_verb` | 2 | one pick/shake pair |
| `pick_diverse_object` | 2 | seen/unseen are independent scenes |
| `attribute_select` | 8 | four independent two-seed axis pairs |
| `arm_select` | 2 | one left/right pair |
| `stack_sequence` | 6 | one six-order scene |
| `place_relative` | 5 | one five-direction scene |
| `grasp_cube_approach` | 2 | one top/side pair |

Example pilot generation and independent validation:

```bash
python tools/generate_if_seed_manifest.py \
  --all --task-config demo_clean \
  --accepted-blocks 2 --max-candidate-blocks 20 \
  --output-dir notes/if-seed-pilot

python tools/validate_if_seed_manifest.py \
  --require-evidence notes/if-seed-pilot
```

The adjacent `.generation.json` file is audit evidence, not part of the evaluator input. It binds the accepted list by SHA-256 and records source/target commits, linked-source digest, exact task-config YAML SHA-256, and whole-block rejections. An external evaluator only loops over `seeds`; it must not sort, deduplicate, drop, increment, replace, or silently fall back when an explicit seed fails. Accepted blocks may have gaps because failed candidate blocks are omitted as a whole.

The 2026-09-03 non-production bounded pilot requested one accepted block with a two-candidate cap. Six tasks emitted and independently validated complete manifests; `pick_diverse_object` exhausted both blocks and correctly emitted evidence without a partial manifest. Exact seeds, timings, rejection reasons, and provenance caveats are recorded in `notes/2026-09-03-if-seed-manifest-pilot/README.md`. The sample does not set production block counts or rejection-rate expectations.

This seed pipeline does not yet implement policy-result `eval_signals()` consumption or per-mode/directional reporting. Those remain benchmark-layer responsibilities after the production manifest size is decided.
