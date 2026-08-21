#!/usr/bin/env python3
"""Report operate_stapler success rates in two views at once:
  - aggregate: the whole task set, mode-agnostic
  - per-mode: press vs move, split purely by seed parity (mode = seed % 2,
    so no extra logging is needed)

Two data sources:
  --collection <dir>   oracle/collection stats from scene_info.json + seed.txt.
                       Reports the collected-dataset composition and the oracle
                       (expert) success rate per mode.
                       Default: third_party/robotwin/data/operate_stapler/demo_clean
  --eval-log <file>    policy eval stats parsed from eval_policy.py stdout. Capture with:
                       bash script/eval_policy.sh ... | tee eval.log

Run from anywhere:
    python tools/report_operate_stapler.py                     # default collection dir
    python tools/report_operate_stapler.py --collection <dir>
    python tools/report_operate_stapler.py --eval-log eval.log
"""
import argparse
import json
import os
import re
from collections import Counter

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_COLLECTION = os.path.join(
    _REPO, "third_party", "robotwin", "data", "operate_stapler", "demo_clean")


def _mode_of(seed):
    return "press" if seed % 2 == 0 else "move"


def _pct(a, b):
    return f"{a}/{b} = {100 * a / b:.1f}%" if b else f"{a}/0 = n/a"


def _print_rates(title, succ_by_mode, total_by_mode):
    press_s, move_s = succ_by_mode.get("press", 0), succ_by_mode.get("move", 0)
    press_t, move_t = total_by_mode.get("press", 0), total_by_mode.get("move", 0)
    print(f"== {title} ==")
    print(f"  aggregate (whole task set): {_pct(press_s + move_s, press_t + move_t)}")
    print(f"  press                     : {_pct(press_s, press_t)}")
    print(f"  move                      : {_pct(move_s, move_t)}")


def report_collection(data_dir):
    scene = json.load(open(os.path.join(data_dir, "scene_info.json")))
    seeds = [int(s) for s in open(os.path.join(data_dir, "seed.txt")).read().split()]
    mx = max(seeds)

    # oracle success = kept(succeeded) / tried, bucketed by seed parity
    kept = Counter(_mode_of(s) for s in seeds)
    tried = Counter(_mode_of(s) for s in range(mx + 1))

    print(f"# operate_stapler — collection (oracle expert) report")
    print(f"# source: {data_dir}")
    print(f"seeds tried 0..{mx} ({mx + 1}), kept {len(seeds)}\n")

    print("-- collected dataset composition (successful episodes) --")
    comp = Counter(v.get("mode") for v in scene.values())
    print(f"  press={comp.get('press', 0)}  move={comp.get('move', 0)}  total={len(scene)}\n")

    _print_rates("oracle expert success rate (kept/tried)", kept, tried)

    ndist = Counter(len(v.get("distractors", [])) for v in scene.values())
    dist = Counter(x.split("/")[0] for v in scene.values() for x in v.get("distractors", []))
    print("\n-- distractors --")
    print(f"  per-episode count: {dict(sorted(ndist.items()))}")
    for k, c in dist.most_common():
        print(f"    {k}: {c}")


def report_eval_log(path):
    # Pair each "Success!/Fail!" line with the following "current seed: N" line.
    results = []  # (seed, success)
    pending = None
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

    succ = Counter(_mode_of(s) for s, ok in results if ok)
    total = Counter(_mode_of(s) for s, _ in results)
    print(f"# operate_stapler — policy eval report")
    print(f"# source: {path}  ({len(results)} episodes)\n")
    _print_rates("policy success rate", succ, total)


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
