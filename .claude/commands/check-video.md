---
description: Extract key frames from a robot task/episode video and judge whether the behavior matches intent. Use this whenever the user wants to visually verify what happens in a .mp4 of robot motion — even casually phrased like "看看这个视频对不对", "这段视频符合预期吗", "帮我看下 episode 视频抓取动作", "does this grasp look right", "check the collected demo", "验证一下这个动作", or right after collecting/rendering demos when they want to eyeball the result. Triggers on any request to inspect, verify, or judge a robot-motion video against an expected behavior. The model cannot watch video directly, so this samples still frames and reasons over them.
argument-hint: <video_path> [intent, e.g. "gripper approaches the cube from the side and lifts it"]
allowed-tools: Bash(bash tools/extract_frames.sh:*), Bash(tools/extract_frames.sh:*), Read
---

Arguments: **$ARGUMENTS**

Parse them: **the first whitespace-delimited token is `video_path`** (required); **everything after it is the free-text `intent`** (optional). If no video path was given, ask for one instead of guessing. A bare task name like `grasp_cube` is not a path — if you get one, the video usually lives at `third_party/robotwin/data/<task>/<config>/video/episode0.mp4`; confirm the exact file before extracting.

Goal: decide whether what the robot actually does in the video matches `intent`. You cannot watch video — you reason over sampled still frames, so sample enough of them and read them in order.

## 1. Extract frames

From the repo root, run:

```
bash tools/extract_frames.sh <video_path> 8
```

This writes 8 evenly-spaced frames to a `frames_<stem>/` dir next to the video and prints their paths. Frames are named `frame_<order>_n<srcindex>.png` — `<order>` is the viewing order (00 first), `<srcindex>` is the position in the source video.

## 2. Read every frame in order

Read each `frame_*.png` from order 00 upward. Hold the whole sequence in mind as a motion, not isolated stills.

## 3. Describe the motion

In 3–5 lines, narrate the trajectory as a sequence: **start → approach → contact/grasp → end state**. Name concrete, checkable things — where the gripper enters from (above / side / angle), which face it contacts, whether the object leaves the surface, the gripper's orientation at contact (vertical vs horizontal), whether anything is knocked or missed.

## 4. Judge against intent

Compare the observed motion to `intent`. If no intent was given, instead report what the robot does and flag anything that looks unintended (missed grasp, collision, object toppling, wrong approach axis).

End with an explicit verdict line:
- **MATCHES** — behavior fits the intent; cite the frame(s) that show it.
- **DOES NOT MATCH** — state exactly which part diverges and in which frame.
- **UNSURE** — a decisive moment falls between sampled frames.

## 5. Look closer when unsure

If the verdict is UNSURE, or a key transition (the instant of contact, an approach direction) happens between two frames, re-extract a denser sample and re-read before concluding:

```
bash tools/extract_frames.sh <video_path> 16
```

Do not force a MATCHES/DOES NOT MATCH verdict on too few frames — sampling more is cheap; a wrong verdict is not.