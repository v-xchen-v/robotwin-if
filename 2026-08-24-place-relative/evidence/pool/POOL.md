# Place-Relative pool — color verification (texture render)

Method per the "verify colors by texture" rule: rendered every base variant of each
candidate from its real `visual/base{K}.glb` baseColor (SAPIEN offscreen), eyeballed
`candidates.png`. Native `objects_description` color words are noisy and NOT used.

Render tool: `tools/render_place_pool_candidates.py`
Evidence: `candidates.png` + per-variant `cand_*.png` in this dir.

## Locked pool

Scene = 1 mover (A) + 1 base/receiver (B) + 1–3 distractors, SAME object pools in
both relations (beside / on-top) so the object set never leaks the relation — only the
instruction word decides beside vs on-top.

### Movers (A) — graspable, compact, clean color, pre_grasp_dis=0.1
| noun | asset | color | source of grasp params |
|---|---|---|---|
| mouse | 047_mouse/base0 | gray | place_object_stand set (0.1) |
| toycar | 057_toycar/base3 | green | place_object_stand set (0.1) |
| stapler | 048_stapler/base4 | red | place_object_stand set (0.1) |
| remotecontrol | 079_remotecontrol/base0 | black | place_object_stand set (0.1) |
| can | 071_can/base3 | red | pick pool (upright qpos, 0.1) |
| soap | 107_soap/base2 | blue | pick pool (0.1) |

### Bases (B) — flat-top box receivers, clear height for on-top vs beside separation
| noun | asset | color |
|---|---|---|
| coffee-box | 113_coffee-box/base0 | brown |
| tea-box | 112_tea-box/base1 | red |

## Dropped (with reason, so we don't re-litigate)
- **bell** (050): dome shape rolls off a flat box top; also special grasp. Native-proven
  for place_object_stand (concave stand cradles it) but not for stacking on a box.
- **rubikscube** (073): only clean single-color variant is solid black (base1) — odd as a
  "rubik's cube"; the natural multicolor variants have no nameable single color.
- **plate** (003): too flat — on-top vs beside differ by only ~1–2 cm in A.z, marginal for
  the height check. Boxes give robust separation.
- **displaystand** (074) / **electronicscale** (072): fixtures, not "everyday named objects".

## Notes
- Color collisions across different nouns (stapler/red + can/red) are fine: grounding is by
  noun; color is a grounding aid, not a scored axis, and we do not build same-noun confusers.
- All movers have non-empty grasp groups; all bases have functional points. Boxes also have
  grasp groups (could be movers) but are used only as bases here.
- on-top placement target = B top surface from AABB (B.z + half-height), NOT functional_point
  (box functional_point isn't guaranteed to be the top) — to be confirmed in Layer B.
