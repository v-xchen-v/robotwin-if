---
description: Pre-collection diagnostic for a RoboTwin task — success rate, per-mode balance, seed→scene mapping vs design, plus a video spot-check reminder.
argument-hint: <task_name> [N=20] [task_config=demo_clean]
---

Arguments (space-separated): **$ARGUMENTS**

Parse them: **1st token = `task_name`** (required), 2nd = `N` (default **20** if absent), 3rd = `task_config` (default **demo_clean** if absent). If no task_name was given, ask for one instead of guessing.

Run the pre-collection diagnostic SOP for that task and end with a clear go / no-go for bulk collection.

## 1. Run the engine (slow — one full episode per seed)

From the repo root, in the RoboTwin conda env, run in the **background** and Monitor its log for the per-seed lines and the three summary blocks (don't poll):

```
conda run -n RoboTwin --no-capture-output python tools/task_diag.py <task_name> <N> <task_config>
```

(Substitute the parsed values.) The engine reuses `collect_data`'s arg build, reads `env.mode` for the mode axis, and fingerprints each scene by `model_id` + all object poses. It runs `setup_demo + play_once + check_success` **in memory only — it writes NO episode data to disk** (that's what `collect_data` is for); its output is just the log.

## 2. Learn this task's DESIGNED seed relationship (needed to judge check #3)

Read `tasks/envs/<task_name>.py` and see how it derives things from the seed — e.g. `self.mode = [...][seed % 2]`, `scene_seed = seed // 2`, or the scene tied 1:1 to the seed. Also skim any matching design note under `docs/features/` or `notes/`. You need this because the tool only *observes* the mapping; deciding whether it's *intended* is task knowledge.

## 3. Interpret the three checks the tool prints

- **Success rate** — overall and per mode. Flag anything notably below the task's bar; if failures are visible, name which seeds/variants failed and why (e.g. a specific `model_id` walling).
- **Balance** — attempts vs **successes** per mode. The *successes* row is what actually gets collected; if it's skewed, say so and explain the cause (usually one mode or variant failing more, so it needs more retries).
- **Seed → scene** — compare the tool's observed scene grouping to the DESIGNED relationship from step 2. **Explicitly confirm it matches, or flag the mismatch.**

## 4. Video is not optional

Numeric checks are blind to **trajectory quality** — an unnatural motion (e.g. a gripper doing an extra wrist twist) passes every metric yet is a bad demo. See `notes/2026-08-31-laptop-verb/why-video-check.md`. Offer to collect a few episodes and spot-check the rendered mp4 (human or VLM) before bulk collection — especially if any motion logic is new or was recently changed.

## Output

Report the three blocks with your interpretation, then state: **ready for bulk collection**, or **what to fix first**.
