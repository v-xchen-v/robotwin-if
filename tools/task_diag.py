#!/usr/bin/env python3
"""Pre-collection diagnostic for a RoboTwin task.

Runs N seeds through a task's setup_demo + play_once + check_success and reports
the three checks you want before trusting a bulk collection:

  1. SUCCESS RATE   — overall, and per mode if the task has a mode axis.
  2. BALANCE        — per-mode counts for ATTEMPTS and (more importantly) for
                      SUCCESSES, since collection only keeps successes; an
                      imbalance here is what actually skews the dataset.
  3. SEED -> SCENE  — groups the seeds by identical scene setup (variant + all
                      object poses) so you can check the mapping against the
                      task's DESIGNED seed relationship (e.g. laptop_verb pairs
                      (2k,2k+1) on one scene; other tasks tie scene to the seed).
                      The tool dumps what it observes and flags the common
                      invariants; "is this the intended relationship" is task
                      knowledge you (or the reviewing agent) confirm.

Generic: no per-task code. Mode is read from env.mode (falls back to
env.info['mode']); absent -> the task has no mode axis and balance is skipped.

NOTE: numeric checks are blind to TRAJECTORY QUALITY (an unnatural motion can
pass every metric). Always also spot-check rendered video (human or VLM) before
bulk collection — see notes/2026-08-31-laptop-verb/why-video-check.md.

Usage (inside the RoboTwin conda env, after ./bridge_tasks.sh):
    python tools/task_diag.py <task_name> [N=20] [task_config=demo_clean]
"""
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _p = os.path.dirname(_REPO)
    if _p == _REPO:
        raise RuntimeError("could not locate repo root")
    _REPO = _p
_RT = os.path.join(_REPO, "third_party", "robotwin")
os.chdir(_RT)
sys.path.insert(0, os.path.join(_RT, "script"))
sys.path.insert(0, _RT)

import numpy as np  # noqa: E402
import collect_data as cd  # noqa: E402

TASK_NAME = sys.argv[1] if len(sys.argv) > 1 else None
N = int(sys.argv[2]) if len(sys.argv) > 2 else 20
TASK_CONFIG = sys.argv[3] if len(sys.argv) > 3 else "demo_clean"
if TASK_NAME is None:
    print(__doc__)
    sys.exit(2)

_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run
cd.main(task_name=TASK_NAME, task_config=TASK_CONFIG)
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0


def get_mode():
    m = getattr(TASK, "mode", None)
    if m is None:
        try:
            m = TASK.info.get("mode")
        except Exception:
            m = None
    return None if m is None else str(m)


def scene_sig():
    """Task-agnostic scene fingerprint: variant id + every object's pose.
    Robot/table are constant across seeds so they don't affect same-vs-different;
    the task objects are what vary with the seed."""
    parts = []
    mid = getattr(TASK, "model_id", None)
    if mid is not None:
        parts.append(("model_id", int(mid)))
    scene = getattr(TASK, "scene", None)
    getters = []
    for name in ("get_all_actors", "get_all_articulations"):
        g = getattr(scene, name, None)
        if callable(g):
            getters.append(g)
    for g in getters:
        try:
            ents = g()
        except Exception:
            continue
        for e in ents:
            try:
                nm = e.get_name()
                p = e.get_pose()
                item = (nm, tuple(np.round(p.p, 4)), tuple(np.round(p.q, 4)))
                qp = getattr(e, "get_qpos", None)
                if callable(qp):
                    item = item + (tuple(np.round(np.asarray(qp()), 4)),)
                parts.append(item)
            except Exception:
                pass
    return tuple(sorted(map(str, parts)))


def setup(seed):
    s = seed
    last = None
    for _ in range(20):
        try:
            TASK.setup_demo(now_ep_num=0, seed=s, **ARGS)
            return True
        except Exception as e:
            last = e
            s += 1000  # jump far to keep the intended seed's parity elsewhere
    print(f"  [setup failed near seed {seed}: {last}]")
    return False


rows = []  # (seed, mode, sig, success)
print(f"== task_diag: {TASK_NAME}  N={N}  config={TASK_CONFIG} ==")
sig_ids = {}


def sig_short(sg):
    if sg not in sig_ids:
        sig_ids[sg] = len(sig_ids)
    return sig_ids[sg]


for seed in range(N):
    if not setup(seed):
        continue
    mode = get_mode()
    sg = scene_sig()
    try:
        TASK.play_once()
        ok = bool(TASK.check_success())
    except Exception as e:
        ok = False
        print(f"seed={seed:3d} {str(mode):6s} scene={sig_short(sg):2d} ERROR {type(e).__name__}")
        rows.append((seed, mode, sg, ok))
        continue
    rows.append((seed, mode, sg, ok))
    print(f"seed={seed:3d} {str(mode):6s} scene={sig_short(sg):2d} {'OK' if ok else 'FAIL'}")

if not rows:
    print("no episodes ran")
    sys.exit(1)

# ---------- 1. success ----------
print("\n==== 1. success rate ====")
tot = len(rows)
sok = sum(r[3] for r in rows)
print(f"overall: {sok}/{tot} ({100*sok/tot:.0f}%)")
modes = sorted({r[1] for r in rows if r[1] is not None})
for m in modes:
    sub = [r for r in rows if r[1] == m]
    print(f"  {m:6s}: {sum(r[3] for r in sub)}/{len(sub)} ({100*sum(r[3] for r in sub)/len(sub):.0f}%)")

# ---------- 2. balance ----------
print("\n==== 2. balance (per mode) ====")
if not modes:
    print("  (task has no mode axis — skipped)")
else:
    att = {m: sum(1 for r in rows if r[1] == m) for m in modes}
    suc = {m: sum(r[3] for r in rows if r[1] == m) for m in modes}
    print(f"  attempts : " + "  ".join(f"{m}={att[m]}" for m in modes))
    print(f"  successes: " + "  ".join(f"{m}={suc[m]}" for m in modes) + "   <- what gets collected")
    if len(set(suc.values())) > 1:
        print(f"  NOTE: success counts differ -> collected data will skew toward "
              f"{max(suc, key=suc.get)} (higher-success mode needs fewer retries).")

# ---------- 3. seed -> scene ----------
print("\n==== 3. seed -> scene mapping (check against your design) ====")
groups = {}
for r in rows:
    groups.setdefault(sig_short(r[2]), []).append(r[0])
sizes = {k: len(v) for k, v in groups.items()}
for k in sorted(groups):
    seeds = groups[k]
    ms = sorted({m for s in seeds for (sd, m, _, _) in rows if sd == s and m})
    print(f"  scene {k:2d}: seeds {seeds}" + (f"  modes={ms}" if ms else ""))
# auto-observations
uniq_sizes = set(sizes.values())
print("  observed:")
print(f"    - {len(groups)} distinct scenes over {tot} seeds")
if uniq_sizes == {1}:
    print("    - every seed is its own scene (scene tied 1:1 to seed)")
elif uniq_sizes == {2}:
    pairs_ok = all(sorted(v) == [min(v), min(v) + 1] for v in groups.values())
    print(f"    - every scene has exactly 2 seeds"
          + ("; each pair is consecutive (2k,2k+1)" if pairs_ok else "; pairs are NOT all consecutive!"))
else:
    print(f"    - scenes have varying #seeds: { {s: sum(1 for x in sizes.values() if x==s) for s in sorted(uniq_sizes)} }")
# adjacency: any two consecutive seeds sharing a scene beyond the intended grouping
print("  -> compare the grouping above to the task's DESIGNED seed relationship.")
print("\n(reminder: also eyeball a few rendered videos — metrics don't see motion quality.)")
