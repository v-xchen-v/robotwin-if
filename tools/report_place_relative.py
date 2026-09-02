#!/usr/bin/env python3
"""Report place_relative success rates, broken down by the SCORED axis (spatial
relation) and, for diagnostics, by mover / reference noun.

(relation, mover, reference) are reproducible from the seed alone (mirrors the env's
load_actors: relation = seed % 2, mover cycles by seed // 2, reference by seed // 12),
so no extra logging is needed for the denominator — same trick as the pick reporter.

Two data sources:
  --collection <dir>   oracle/collection stats from scene_info.json + seed.txt.
                       Default: third_party/robotwin/data/place_relative/demo_clean
  --eval-log <file>    policy eval stats parsed from eval_policy.py stdout.

    python tools/report_place_relative.py --collection
    python tools/report_place_relative.py --eval-log eval.log
"""
import argparse
import json
import os
import re
from collections import Counter

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_COLLECTION = os.path.join(
    _REPO, "third_party", "robotwin", "data", "place_relative", "demo_clean")

# Must match place_relative.MOVERS / BASES key order.
MOVER_NOUNS = ["mouse", "toycar", "stapler", "remotecontrol", "can", "soap"]
BASE_NOUNS = ["coffee-box", "tea-box"]
RELATIONS = ["beside", "on_top"]


def episode_of_seed(seed):
    # Mirrors place_relative.load_actors.
    relation = RELATIONS[seed % 2]
    mover = MOVER_NOUNS[(seed // 2) % len(MOVER_NOUNS)]
    reference = BASE_NOUNS[(seed // (2 * len(MOVER_NOUNS))) % len(BASE_NOUNS)]
    return relation, mover, reference


def _pct(a, b):
    return f"{a}/{b} = {100 * a / b:.1f}%" if b else f"{a}/0 = n/a"


def _breakdown(title, keys, succ, total):
    st = sum(succ.get(k, 0) for k in keys)
    tt = sum(total.get(k, 0) for k in keys)
    print(f"== {title} ==")
    print(f"  aggregate: {_pct(st, tt)}")
    for k in keys:
        print(f"  {k:<14}: {_pct(succ.get(k, 0), total.get(k, 0))}")


def _report(seed_success, header):
    dims = {"relation": (RELATIONS, Counter(), Counter()),
            "mover": (MOVER_NOUNS, Counter(), Counter()),
            "reference": (BASE_NOUNS, Counter(), Counter())}
    for seed, ok in seed_success:
        rel, mover, ref = episode_of_seed(seed)
        for name, val in (("relation", rel), ("mover", mover), ("reference", ref)):
            _, succ, tot = dims[name]
            tot[val] += 1
            if ok:
                succ[val] += 1
    print(header)
    _breakdown("success by RELATION (scored axis)", dims["relation"][0], dims["relation"][1], dims["relation"][2])
    print()
    _breakdown("success by mover noun", dims["mover"][0], dims["mover"][1], dims["mover"][2])
    print()
    _breakdown("success by reference noun", dims["reference"][0], dims["reference"][1], dims["reference"][2])


def report_collection(data_dir):
    seeds = [int(s) for s in open(os.path.join(data_dir, "seed.txt")).read().split()]
    mx = max(seeds)
    kept = set(seeds)
    seed_success = [(s, s in kept) for s in range(mx + 1)]

    print("# place_relative — collection (oracle expert) report")
    print(f"# source: {data_dir}")
    print(f"seeds tried 0..{mx} ({mx + 1}), kept {len(seeds)}\n")
    _report(seed_success, "-- oracle expert success rate (kept/tried) --")

    # scene_info.json is written by the (separate) data-export phase; the rate above only
    # needs seed.txt, so tolerate its absence and just skip the composition line.
    info_path = os.path.join(data_dir, "scene_info.json")
    if os.path.exists(info_path):
        scene = json.load(open(info_path))
        comp = Counter(v.get("relation") for v in scene.values())
        print("\n-- collected dataset composition (successful episodes) --")
        print("  relation: " + "  ".join(f"{r}={comp.get(r, 0)}" for r in RELATIONS) + f"  total={len(scene)}")


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
        print(f"no episodes parsed from {path}")
        return
    print(f"# place_relative — policy eval report")
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
