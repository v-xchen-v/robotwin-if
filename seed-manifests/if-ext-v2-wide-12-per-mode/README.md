# Formal IF v2, wide grasp revision: 12 blocks

`grasp_cube_approach.json` uses independent seeds starting at 500000 and the archived `wide-r1` translation profile: x=[0, 0.08] m, y=[-0.085, -0.035] m. The cube and riser translate together without rotation. Each block pairs top and side with identical initial images and poses; each x stratum contributes four qualified blocks. Full candidate/repeat/wrong-direction evidence and exclusions are in `grasp_cube_approach.probe.yml`.

The other six manifests and their qualification evidence are unchanged. `reusable-results.yml` retains the original 276-episode baseline; additional completed results from the earlier 12-block run are recorded individually in the new evaluation's `support/migration.json`. Completed successes and failures are both retained. No old grasp geometry results may be imported into this release.

All six policies run grasp on msrait-03. All six policies run the other tasks on msrait-04. Exact initial RGB/state/instruction checks remain enabled within each task. Each host uses one simulator and one model server on separate GPUs.

The old release remains intact. Replaying it requires its original narrow config/source snapshot; the current same-named v2 config is wide. This release stores its geometry/config under `scene-snapshot/` and the formal run freezes the full source and manifest hashes.

Validate: `python seed-manifests/if-ext-v2-wide-12-per-mode/verify.py`.
