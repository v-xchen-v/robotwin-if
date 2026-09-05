#!/usr/bin/env python3
"""Oracle spike for IF-Sequence (stack_sequence): per-permutation reliability.

The gate before productionizing the stack-in-sequence task: the oracle must
stack 3 blocks in the COMMANDED bottom->top order at ~90% across ALL 6
permutations -- not just the native red-bottom default. Different orders visit
the blocks in a different temporal order -> different arm-switch patterns, so the
per-perm rate can be uneven; this sweep exposes that.

Per episode it prints L1 (a 3-stack formed at all) vs L2 (correct commanded
order), so a failure reads as "didn't stack" (L1 False) vs "stacked wrong
order / toppled" (L1 True, L2 False) rather than a bare rate.

A counter-example phase commands order 0 (red-bottom) but makes the oracle STACK
order 5 (blue-bottom); check_success must REJECT it (a valid stack in the wrong
order is not success) -- Layer-B.

Run inside the RoboTwin conda env, after bridging the env into the submodule:
    ./bridge_tasks.sh
    conda activate RoboTwin
    python tests/stack_sequence/sweep_per_perm.py [N]

Exit code is non-zero if any permutation is below the ~90% gate or the
counter-example leaks.
"""
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_REPO, "third_party", "robotwin")):
    _parent = os.path.dirname(_REPO)
    if _parent == _REPO:
        raise RuntimeError("could not locate repo root (no third_party/robotwin above this file)")
    _REPO = _parent
_RT = os.path.join(_REPO, "third_party", "robotwin")
os.chdir(_RT)
sys.path.insert(0, os.path.join(_RT, "script"))
sys.path.insert(0, _RT)

import numpy as np  # noqa: E402
import collect_data as cd  # noqa: E402  (RoboTwin's collector; reused for arg construction)

TASK_NAME = "stack_sequence"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
GATE = 0.90

_cap = {}


def _capture_run(task, args):
    _cap["task"] = task
    _cap["args"] = args


cd.run = _capture_run
cd.main(task_name=TASK_NAME, task_config="demo_clean")
TASK = _cap["task"]
ARGS = dict(_cap["args"])
ARGS["render_freq"] = 0

PERMS = TASK.PERMS
NAMES = TASK.COLOR_NAMES


def _perm_str(p):
    return ">".join(NAMES[c] for c in p)


def run_phase(label, mode, oracle_mode, expect_success):
    """Fix the commanded order (mode); vary the scene over N seeds. oracle_mode
    None -> oracle stacks the commanded order; else it stacks a different order
    (counter-example). Returns the L2 (correct-order) success rate."""
    TASK.MODE = mode
    TASK.ORACLE_MODE = oracle_mode
    tag = _perm_str(PERMS[mode])
    if oracle_mode is not None:
        tag += f"  (oracle stacks {_perm_str(PERMS[oracle_mode])})"
    print(f"\n== phase '{label}': commanded {tag}  {N} episodes ==")
    n_run = n_l1 = n_l2 = 0
    for ep in range(N):
        seed = ep
        last = None
        for _ in range(20):
            try:
                TASK.setup_demo(now_ep_num=0, seed=seed, **ARGS)
                last = None
                break
            except Exception as e:
                last = e
                seed += N
        if last is not None:
            print(f"[ep {ep:02d}] SKIP: no stable scene ({last})")
            continue
        try:
            TASK.play_once()
        except Exception as e:
            print(f"[ep {ep:02d}] ERROR play-crash: {e}")
            n_run += 1
            continue
        sig = TASK.eval_signals()
        ok = bool(TASK.check_success())
        n_run += 1
        n_l1 += int(sig["l1_stacked"])
        n_l2 += int(sig["l2_ordered"])
        if sig["l2_ordered"]:
            verdict = "OK  "
        elif sig["l1_stacked"]:
            verdict = "WRONG-ORDER"
        else:
            verdict = "NO-STACK"
        print(f"[ep {ep:02d}] {verdict:11s} L1={int(sig['l1_stacked'])} "
              f"L2={int(sig['l2_ordered'])} check={int(ok)}")
    l1_rate = n_l1 / n_run if n_run else 0.0
    l2_rate = n_l2 / n_run if n_run else 0.0
    print(f"  -> L1(any stack) {n_l1}/{n_run} ({l1_rate:.1%})   "
          f"L2(correct order) {n_l2}/{n_run} ({l2_rate:.1%})")
    return l2_rate, n_run


print(f"==== stack_sequence spike: N={N} per perm, gate {GATE:.0%} ====")
rates = {}
for mode in range(6):
    r, _ = run_phase(f"perm {mode}", mode, None, expect_success=True)
    rates[mode] = r

# Counter-example: command red-bottom (0), oracle stacks blue-bottom (5, the
# exact reverse). check_success must reject despite a valid stack forming.
ce_rate, _ = run_phase("counter-example", 0, 5, expect_success=False)

print("\n==== summary ====")
worst = min(rates.values()) if rates else 0.0
for mode in range(6):
    ok = rates[mode] >= GATE
    print(f"perm {mode} {_perm_str(PERMS[mode]):18s} L2 {rates[mode]:.1%}   "
          f"{'PASS' if ok else 'BELOW GATE'}")
print(f"counter-example (wrong order) L2 {ce_rate:.1%}   want <=10%   "
      f"{'PASS' if ce_rate <= 0.10 else 'LEAK'}")

all_pass = worst >= GATE
ce_pass = ce_rate <= 0.10
print(f"\nworst perm: {worst:.1%}   gate {GATE:.0%}")
if all_pass and ce_pass:
    print("PASS -> stack-in-sequence oracle viable across all 6 orders; lock design")
else:
    print("BELOW GATE -> inspect the failing perm's arm-switch/place chain before productionizing")
sys.exit(0 if (all_pass and ce_pass) else 1)
