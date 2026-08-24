#!/usr/bin/env python3
"""Report pick_diverse_object success rates, broken down by what is being grounded:
  - aggregate: the whole task set
  - per target NOUN: all 12 categories
  - per target COLOR

The target (noun, color) is `variant[seed % N]` in the env's load_actors, so it is
reproducible from the seed alone (target_of_seed below mirrors that) -- no extra logging
needed for the denominator, exactly like operate_tabletop derives mode from seed parity.

Two data sources:
  --collection <dir>   oracle/collection stats from scene_info.json + seed.txt.
                       Default: third_party/robotwin/data/pick_diverse_object/demo_clean
  --eval-log <file>    policy eval stats parsed from eval_policy.py stdout:
                       bash script/eval_policy.sh ... | tee eval.log

Run from anywhere:
    python tools/report_pick_diverse_object.py
    python tools/report_pick_diverse_object.py --collection <dir>
    python tools/report_pick_diverse_object.py --eval-log eval.log
"""
import argparse
import json
import os
import re
from collections import Counter

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_COLLECTION = os.path.join(
    _REPO, "third_party", "robotwin", "data", "pick_diverse_object", "demo_clean")

# Must match pick_diverse_object.POOL (noun -> colors in order). Target noun cycles by
# seed % 12, color by seed // 12 -> every category is an equally likely target.
POOL = {
    "bottle": ["red", "green", "orange"], "cup": ["blue", "green"], "shoe": ["red", "green"],
    "mug": ["black"], "can": ["red"], "toycar": ["green"], "phone": ["black"],
    "soap": ["blue"], "hamburg": ["yellow"], "bread": ["golden"],
    "coffee-box": ["brown"], "mouse": ["gray"],
}
NOUNS = list(POOL.keys())
COLORS = ["red", "green", "blue", "orange", "black", "yellow", "golden", "brown", "gray"]


def target_of_seed(seed):
    # Matches pick_diverse_object.load_actors: noun = NOUNS[seed % 12], color cycles
    # within the noun by seed // 12 (seed%N cycle, not an rng draw, so consecutive seeds
    # give a uniform target distribution).
    noun = NOUNS[seed % len(NOUNS)]
    colors = POOL[noun]
    return (noun, colors[(seed // len(NOUNS)) % len(colors)])


def _pct(a, b):
    return f"{a}/{b} = {100 * a / b:.1f}%" if b else f"{a}/0 = n/a"


def _print_breakdown(title, keys, succ, total):
    st = sum(succ.get(k, 0) for k in keys)
    tt = sum(total.get(k, 0) for k in keys)
    print(f"== {title} ==")
    print(f"  aggregate (whole task set): {_pct(st, tt)}")
    for k in keys:
        print(f"  {k:<10}: {_pct(succ.get(k, 0), total.get(k, 0))}")


def _report(seed_success, header):
    """seed_success: list of (seed, succeeded_bool)."""
    succ_noun, tot_noun = Counter(), Counter()
    succ_color, tot_color = Counter(), Counter()
    for seed, ok in seed_success:
        noun, color = target_of_seed(seed)
        tot_noun[noun] += 1
        tot_color[color] += 1
        if ok:
            succ_noun[noun] += 1
            succ_color[color] += 1
    print(header)
    _print_breakdown("success by target NOUN", NOUNS, succ_noun, tot_noun)
    print()
    _print_breakdown("success by target COLOR", COLORS, succ_color, tot_color)


def report_collection(data_dir):
    scene = json.load(open(os.path.join(data_dir, "scene_info.json")))
    seeds = [int(s) for s in open(os.path.join(data_dir, "seed.txt")).read().split()]
    mx = max(seeds)
    kept = set(seeds)
    # Oracle: every seed 0..max was tried; those in seed.txt succeeded (kept).
    seed_success = [(s, s in kept) for s in range(mx + 1)]

    print("# pick_diverse_object — collection (oracle expert) report")
    print(f"# source: {data_dir}")
    print(f"seeds tried 0..{mx} ({mx + 1}), kept {len(seeds)}\n")
    _report(seed_success, "-- oracle expert success rate (kept/tried) --")

    # Extra detail from the kept episodes' logged makeup.
    comp = Counter(v.get("target_noun") for v in scene.values())
    print("\n-- collected dataset composition (successful episodes) --")
    print("  target noun: " + "  ".join(f"{n}={comp.get(n, 0)}" for n in NOUNS) + f"  total={len(scene)}")
    dcount = Counter(d.split("/")[0] for v in scene.values() for d in v.get("distractors", []))
    if dcount:
        print("  distractor nouns: " + ", ".join(f"{k}={c}" for k, c in dcount.most_common()))


def report_eval_log(path):
    results, pending = [], None
    for line in open(path):
        if "Success!" in line:
            pending = True
        elif "Fail!" in line:
            pending = False
        m = re.search(r"current seed:\s*(\d+)", line)
        if m and pending is not None:
            results.append((int(m.group(1)), pending))
            pending = None
    if not results:
        print(f"no episodes parsed from {path} "
              f"(expected 'Success!/Fail!' + 'current seed: N' lines)")
        return
    print(f"# pick_diverse_object — policy eval report")
    print(f"# source: {path}  ({len(results)} episodes)\n")
    _report(results, "-- policy success rate --")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--collection", nargs="?", const=_DEFAULT_COLLECTION,
                   help="collection data dir (default demo_clean)")
    g.add_argument("--eval-log", help="eval_policy.py stdout log to parse")
    a = ap.parse_args()

    if a.eval_log:
        report_eval_log(a.eval_log)
    else:
        report_collection(a.collection or _DEFAULT_COLLECTION)


if __name__ == "__main__":
    main()
