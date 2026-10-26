# Press / Lift Stapler feasibility

Experimental candidate for the verb task. The maintained six-task suite and its
20-block bell manifest remain unchanged. This pilot first qualifies four paired
scenes, then evaluates LingBot-VA and X-VLA on all eight episodes each.

## Scene and instructions

| Mode | Instruction |
|---|---|
| press | `Press down on the stapler.` |
| lift | `Lift the stapler.` |

Both `seen` and `unseen` return the same mode-specific sentence. Episode `2k` is
Press and `2k+1` is Lift; the entire initial setup uses scene seed `k`. The first
pilot fixes scenes `50000–50003` / episodes `100000–100007` before qualification
or inference. Native stapler models 0 and 4 each appear on the left and right.

Native `move_stapler_pad` has eligible seen templates `Lift {A} to the {B} mat
using {a}`, `Lift {A} and drop it onto {B} mat`, and `Pick up {A} and place it on
{B} mat`. With the native `{A}/{B}/{a}` episode parameters, 49 seen templates
survive filtering, including both Lift templates. `{A}` expands to an asset
description such as `the red stapler`. Thus `Lift the stapler.` uses a native
verb but removes the destination, placement action, and detailed noun phrase;
it is not an exact native full-task sentence. Template counts do not establish
the actual training frequency of a checkpoint.

The target is dynamic, 0.05 kg, in both modes. It uses the native resting pose,
with x magnitude 0.14–0.19 m and y between -0.15 and -0.10 m. The mouse and toycar
use the bell experiment's deterministic `random-back-region-v1` sampler. There
is no destination mat. The completed model pilot below used the fixed quaternion
`[0.5, 0.5, 0.5, 0.5]` for all three actors. The current implementation adds
world-Z yaw (`random-yaw-v1`): stapler uniformly within +/-15 degrees, mouse and
toycar independently within +/-180 degrees. Each actor uses a separate scene-seed
stream, leaving position sampling unchanged. Press/Lift pairs share the same
rotations. The earlier model scores apply to the fixed-rotation scenes only.
Three initial RGB arrays and robot proprioception must
match exactly within each pair and between expert and policy setup.

Rotation validation (2026-10-26): expert Press 4/4, Lift 4/4. All four pairs have
identical initial RGB, proprioception, positions and quaternions. Model evaluation
has not been rerun with randomized rotations.

## Native action and checker alignment

Native `press_stapler` uses `048_stapler` contact point 2, with a +/- 3 cm contact
window. It uses a static target and ends upon contact; it does not require a
retreat. Native `move_stapler_pad` grasps the same asset, lifts it 10 cm, then
places it on a mat. The pilot uses its grasp/lift prefix.

`StaplerMonitor` reuses the bell first-action classifier with two changes: the
native stapler contact window is 3 cm, and Press completes on qualifying contact
without waiting for a retreat. Its version is
`press-lift-stapler-v1-native-press-contact`.

- Press: gripper already closed for at least 0.08 s, downward approach at least
  5 mm, first contact near point 2, table support, target rise no more than 1.5 cm
  and lateral displacement no more than 3 cm.
- Lift: target rises at least 3 cm, has closed-gripper contact and no table
  contact for at least 0.1 s.
- First completed action locks the verdict; doing the other action later cannot
  repair an incorrect first action. Closing an open gripper onto the target does
  not satisfy the preclosed Press approach gate.
- Native contact reports include zero-impulse points and are sampled at every
  actual physics step (4 ms). `native_press_success` separately reports the weaker
  native contact-only condition; it is not the scored verdict.
- Both modes have a 250-policy-action budget. The expert additionally retreats
  after pressing for observation, but the policy is not required to retreat.

The native static Press result is not directly comparable to this dynamic target
and stronger action-discrimination condition. Existing model success on a
multi-step placement task also does not establish success on the isolated Lift
sentence.

## Qualification and execution

The expert uses absolute 2 mm downward waypoints over the native 8 cm approach,
stopping on contact. Relative waypoints from the measured EE pose accumulated
tracking shortfall on model 4; the first qualification attempt retained those
two Press failures. This was corrected without changing seeds, scenes or success
thresholds. The final checker also removes the native-absent retreat requirement.

Final qualification: **Press 4/4, Lift 4/4, both actions 4/4 pairs**. All paired
initial arrays are exact; they also match across the retained oracle revisions.
The pilot is stored at
`outputs/policy-eval/press-lift-stapler-feasibility-4pairs-001/` (an alias to `/Data`).
`preflight-validation.json` records these checks; `preflight-v3/` contains the
qualified source snapshots and observations. Earlier attempts remain available.

```bash
python tools/press_lift_stapler.py --policy oracle \
  --scene-seeds 50000 50001 50002 50003 --output-dir <new-run>

# Start the chosen policy server separately, then:
python tools/press_lift_stapler.py --policy lingbot_va \
  --scene-seeds 50000 50001 50002 50003 --output-dir <new-policy-run>
```

No bridge installation or formal seed-contract registration is required. The
runner extends RoboTwin's environment search path only in its own process. Model
failures are retained; infrastructure or oracle errors stop the pilot. Source
hashes, server launch arguments, source snapshots, per-episode videos and physics
traces are recorded.

## Completed model pilot (2026-10-26)

| Policy | Press | Lift | Both actions in the same scene |
|---|---:|---:|---:|
| Expert | 4/4 | 4/4 | 4/4 |
| LingBot-VA | 4/4 | 0/4 | 0/4 |
| X-VLA | 0/4 | 3/4 | 0/4 |

All eight LingBot-VA episodes classify Press as their first completed action.
X-VLA lifts successfully under three of four Lift instructions. Under Press,
it lifts in the two model-0 scenes and completes neither action in the two
model-4 scenes. The remaining Lift failure is model 4 on the right; its maximum
rise is 8.18 mm, below the 30 mm threshold.

For X-VLA Press seed 100004, the physics trace has one initial contact at
19.176 s with the gripper still open. It satisfies the native contact diagnostic,
but not the pilot's already-closed downward Press approach. This distinction is
preserved in the result, without changing the checker after inference.

This establishes that X-VLA can lift the stapler with the current short sentence
on these scenes. Neither tested model succeeds on both verbs within a scene.
The pilot therefore supports further investigation, but does not yet establish
reliable verb following or justify a formal manifest replacement. It also does
not isolate wording, object geometry, or scene appearance as the cause of a
model's behavior. Native training-template availability is not evidence that a
checkpoint was trained on the exact isolated Lift instruction.

Both policy validations pass with exact initial scenes, unchanged qualified
sources, and all 16 planned episodes retained. All 16 videos decode with
`action_calls + 1` frames. Correct-action episodes stop on success; failures run
to 250 actions, so maximum heights have different observation windows. These
findings use the checker and physics traces; no manual visual review is claimed.
The pilot servers and simulators have stopped. The formal bell evaluation remains
paused.

- [Per-episode results and video index](../outputs/policy-eval/press-lift-stapler-feasibility-4pairs-001/README.md)
- [Machine-readable results and artifact hashes](../outputs/policy-eval/press-lift-stapler-feasibility-4pairs-001/pilot-summary.json)
- [Video viewer](http://127.0.0.1:8896/)
