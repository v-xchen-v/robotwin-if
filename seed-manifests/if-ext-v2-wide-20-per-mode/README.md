# Formal IF v2 wide: 20 blocks

Historical seven-task release. The current runnable suite is [the six-task release](../if-ext-v2-six-tasks-20-per-mode/README.md); the verifier below reads archived task metadata without reactivating grasp approach.

This release retains the complete 12-block prefix for all seven tasks and all six models. VLAct uses `StarVLA/VLAct_Qwen3OFT_Robotwin_all_Finetune` at `999b37d4d7c1bd0f5588f78d72a185f6f052bf83`. All 1,944 prior results, including 1,140 failures, remain immutable. The extension adds 1,296 episodes: 540 per policy, 3,240 total, 840 complete policy/task blocks.

The five base tasks use the first 20 accepted whole blocks of the original 100-block oracle evidence. Arm v2 and grasp v2 wide-r1 retain the original 12 blocks and append the earliest qualified whole candidates above the old maximum seed, up to left=7, center=7, right=6. Twenty is not divisible by three; every instruction mode still has exactly 20 episodes. Planned repeat and wrong-arm/direction controls must pass. No policy success/failure is used to select seeds; rejected and unused candidates remain in the evidence.

Scene geometry, configs, language split, checkpoint revisions, action decoding and rollout options stay fixed. The 12-block release and reports are archived separately. `reusable-results.yml` records each prior provenance SHA-256 and artifact hashes; migration checks them before committing new markers. New outcomes never overwrite old results.

Validate with `python seed-manifests/if-ext-v2-wide-20-per-mode/verify.py`.
