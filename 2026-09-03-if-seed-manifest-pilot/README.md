# IF seed-manifest bounded pilot

Date: 2026-09-03

## Status

This directory is **non-production pilot evidence**. It does not freeze the benchmark episode set or choose the eventual number of accepted blocks.

The bounded run requested one accepted balance block per maintained IF task and allowed at most two candidate blocks. Six of seven tasks reached that target. `pick_diverse_object` exhausted both candidates, so the generator correctly emitted only its `.generation.json` rejection evidence and no partial flat manifest.

## Command

```bash
conda run --no-capture-output -n RoboTwin \
  python tools/generate_if_seed_manifest.py \
  --all \
  --task-config demo_clean \
  --accepted-blocks 1 \
  --max-candidate-blocks 2 \
  --output-dir notes/2026-09-03-if-seed-manifest-pilot
```

The aggregate process exited nonzero because one requested task was exhausted. It continued through all later tasks rather than stopping after the first task failure.

## Bound provenance

All seven sidecars record the same runtime inputs:

- robotwin-if commit: `ef9a1992bf03230a1550c81b0c65ea9e5f969503` (`source_dirty: true`);
- linked-source digest: `40c78757dbe349d9d55594291f6d12c4ed63e978fb6e3f28d6fccd2d5b564da9`;
- RoboTwin commit: `0aeea2d669c0f8516f4d5785f0aa33ba812c14b4`;
- RoboTwin compatibility-contract dirty: `false`;
- task config: `task_config/demo_clean.yml`;
- exact task-config SHA-256: `ae893a209ed2425d1a4d2cd7046187d60a566fc715aa88447901335ea2900f82`.

The task config was a pre-existing local modification in the nested RoboTwin checkout, so the YAML hash—not the config name or target commit alone—is required to identify this pilot.

## Results

| Task | Status | Candidates | Accepted block / exact seeds | Rejected blocks | Oracle time |
|---|---|---:|---|---|---:|
| `bottle_verb` | complete | 2 | 50001 / 100002–100003 | 50000 | 116.9 s |
| `pick_diverse_object` | exhausted | 2 | none; no manifest | 50000, 50001 | 32.4 s |
| `attribute_select` | complete | 1 | 12500 / 100000–100007 | none | 128.4 s |
| `arm_select` | complete | 1 | 50000 / 100000–100001 | none | 24.5 s |
| `stack_sequence` | complete | 2 | 16668 / 100008–100013 | 16667 | 96.1 s |
| `place_relative` | complete | 1 | 20000 / 100000–100004 | none | 31.6 s |
| `grasp_cube_approach` | complete | 1 | 50000 / 100000–100001 | none | 24.4 s |

Total recorded oracle time was approximately 454.3 seconds (7 minutes 34 seconds).

### Exact rejection evidence

- `bottle_verb`, block 50000:
  - seed 100000, expected/observed `pick`: setup and plan passed; `check_success()` was false;
  - seed 100001, expected/observed `shake`: setup and plan passed; `check_success()` was false.
- `pick_diverse_object`, block 50000:
  - seed 100000 passed individually;
  - seed 100001, expected/observed `unseen`: setup passed; `plan_success` was false;
  - the entire seen/unseen block was rejected.
- `pick_diverse_object`, block 50001:
  - seed 100002, expected `seen`: setup raised `UnStableError` because `001_bottle` was unstable;
  - seed 100003 passed individually;
  - the entire seen/unseen block was rejected.
- `stack_sequence`, block 16667:
  - seed 100003, expected/observed `red>blue>green`: setup passed; `plan_success` was false;
  - the other five members passed individually, but the entire six-order block was rejected.

No failed member was replaced, incremented, or silently omitted. Accepted block IDs may therefore contain gaps.

## Independent validation

The base-environment validator verified all six emitted manifests and their adjacent evidence:

- `bottle_verb`: pick=1, shake=1;
- `attribute_select`: one episode for each of its eight axis/value modes;
- `arm_select`: left=1, right=1;
- `stack_sequence`: one episode for each of six permutations;
- `place_relative`: one episode for each of five directions;
- `grasp_cube_approach`: top=1, side=1.

Running the validator on the whole directory intentionally exits 1 and reports:

```text
pick_diverse_object.generation.json: generation evidence has no adjacent manifest
```

That is the expected representation of bounded exhaustion, not a malformed partial manifest.

## Resume/provenance check

A later real `--resume --all` attempt first failed closed at bridge preflight before importing or probing tasks. The 18 destinations still resolved to the expected source files, but the current linked-source digest had changed from the pilot's `40c787…` to `047e24…` after Pick-Diverse env/pool edits.

The standard bridge command then refreshed only the untracked ownership metadata for the current sources (`add=0`, `remove-stale=0`, `owned=18`), and `bridge --check` passed. A second real resume passed bridge preflight but rejected all seven checkpoints with `resume provenance do not match the requested run`. It performed no oracle probes and did not replace any pilot artifact.

This is the intended two-layer provenance behavior: installation state can be refreshed to accurately describe current links, while a historical dirty-source checkpoint cannot be resumed after linked source content changes. The sidecars retain the exact digest under which this pilot ran, but this non-production pilot is not itself a source snapshot.

## Implication

The seed pipeline works end to end for exact probing, whole-block rejection, flat-manifest publication, evidence binding, and independent validation. This small sample is not enough to estimate stable rejection rates. Before a production freeze:

1. review current Pick-Diverse source changes and refresh bridge provenance deliberately;
2. investigate its setup/oracle reliability or run a larger bounded scan under one fixed source digest;
3. choose a production accepted-block count and candidate cap;
4. generate and freeze production manifests under a published task config;
5. only then make policy evaluators replay the flat seed lists.
