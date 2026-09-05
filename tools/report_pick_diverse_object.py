#!/usr/bin/env python3
"""Report all-Seen-scene vs all-Unseen-scene Pick-Diverse-Object results.

This is a scene-level object-familiarity split: the target and all three distractors
come from the same group. The Seen/Unseen gap must not be interpreted as a pure
same-scene target-only causal effect.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from tasks.envs._pick_diverse_object_pool import (  # noqa: E402
    SEEN_POOL,
    UNSEEN_POOL,
    familiarity_for_seed,
    target_for_seed,
)

DEFAULT_COLLECTION = os.path.join(
    REPO, "third_party", "robotwin", "data", "pick_diverse_object", "demo_clean"
)
POOLS = {"seen": SEEN_POOL, "unseen": UNSEEN_POOL}


def target_of_seed(seed):
    familiarity = familiarity_for_seed(seed)
    noun, asset, model_id = target_for_seed(seed, POOLS[familiarity])
    return familiarity, noun, asset, model_id


def rate(successes, total):
    return successes / total if total else None


def pct(successes, total):
    value = rate(successes, total)
    return f"{successes}/{total} = {100 * value:.1f}%" if value is not None else "0/0 = n/a"


def scalar_pct(value):
    return "n/a" if value is None else f"{100 * value:.1f}%"


def report_seed_results(seed_success, heading):
    success_group = Counter()
    total_group = Counter()
    success_noun = Counter()
    total_noun = Counter()
    success_variant = Counter()
    total_variant = Counter()

    for seed, succeeded in seed_success:
        familiarity, noun, asset, model_id = target_of_seed(seed)
        noun_key = (familiarity, noun)
        variant_key = (familiarity, noun, asset, model_id)
        total_group[familiarity] += 1
        total_noun[noun_key] += 1
        total_variant[variant_key] += 1
        if succeeded:
            success_group[familiarity] += 1
            success_noun[noun_key] += 1
            success_variant[variant_key] += 1

    group_rates = {
        familiarity: rate(success_group[familiarity], total_group[familiarity])
        for familiarity in ("seen", "unseen")
    }
    available = [value for value in group_rates.values() if value is not None]
    balanced = sum(available) / len(available) if len(available) == 2 else None
    gap = (
        group_rates["seen"] - group_rates["unseen"]
        if all(value is not None for value in group_rates.values())
        else None
    )
    retention = (
        group_rates["unseen"] / group_rates["seen"]
        if group_rates["seen"] not in (None, 0) and group_rates["unseen"] is not None
        else None
    )

    print(heading)
    print("  Seen target / all-Seen scene   :", pct(success_group["seen"], total_group["seen"]))
    print("  Unseen target / all-Unseen scene:", pct(success_group["unseen"], total_group["unseen"]))
    print("  balanced average               :", scalar_pct(balanced))
    print("  absolute gap (Seen - Unseen)   :", scalar_pct(gap))
    print("  retention (Unseen / Seen)      :", scalar_pct(retention))

    for familiarity in ("seen", "unseen"):
        print(f"\n== {familiarity.upper()} target nouns / all-{familiarity.capitalize()} scenes ==")
        noun_rates = []
        for noun in POOLS[familiarity]:
            key = (familiarity, noun)
            noun_rate = rate(success_noun[key], total_noun[key])
            if noun_rate is not None:
                noun_rates.append(noun_rate)
            print(f"  {noun:<18s}: {pct(success_noun[key], total_noun[key])}")
        macro = sum(noun_rates) / len(noun_rates) if noun_rates else None
        micro = group_rates[familiarity]
        print(f"  {'micro':<18s}: {scalar_pct(micro)}")
        print(f"  {'macro over tried nouns':<18s}: {scalar_pct(macro)}")

    print("\n== exact target variants ==")
    for key in total_variant:
        familiarity, noun, asset, model_id = key
        print(
            f"  {familiarity:6s} {noun:<18s} {asset} base{model_id:<2d}: "
            f"{pct(success_variant[key], total_variant[key])}"
        )


def report_collection(data_dir):
    scene_path = os.path.join(data_dir, "scene_info.json")
    seed_path = os.path.join(data_dir, "seed.txt")
    with open(scene_path) as handle:
        scene = json.load(handle)
    with open(seed_path) as handle:
        seeds = [int(seed) for seed in handle.read().split()]
    if not seeds:
        raise RuntimeError(f"no successful seeds in {seed_path}")

    max_seed = max(seeds)
    kept = set(seeds)
    seed_success = [(seed, seed in kept) for seed in range(max_seed + 1)]
    print("# Pick-Diverse-Object object familiarity report")
    print("# comparison: Seen target / all-Seen scene vs Unseen target / all-Unseen scene")
    print("# interpretation: independent scenes; NOT a target-only same-scene causal gap")
    print(f"# source: {data_dir}")
    print(f"# tried seeds: 0..{max_seed} ({max_seed + 1}); kept: {len(seeds)}\n")
    report_seed_results(seed_success, "-- oracle kept / raw seeds tried --")

    kept_group = Counter()
    kept_noun = Counter()
    distractor_noun = Counter()
    mismatches = []
    for episode in scene.values():
        familiarity = episode.get("target_familiarity")
        noun = episode.get("target_noun")
        if familiarity is not None:
            kept_group[familiarity] += 1
            kept_noun[(familiarity, noun)] += 1
        if (
            familiarity is not None
            and episode.get("scene_familiarity") not in (None, familiarity)
        ):
            mismatches.append(episode)
        for distractor in episode.get("distractors", []):
            distractor_noun[distractor.split("/", 1)[0]] += 1

    print("\n-- kept episode composition (successful oracle episodes only) --")
    print("  familiarity:", "  ".join(
        f"{name}={kept_group[name]}" for name in ("seen", "unseen")
    ))
    for familiarity in ("seen", "unseen"):
        values = "  ".join(
            f"{noun}={kept_noun[(familiarity, noun)]}" for noun in POOLS[familiarity]
        )
        print(f"  {familiarity} target nouns: {values}")
    if distractor_noun:
        print("  distractor nouns:", ", ".join(
            f"{noun}={count}" for noun, count in distractor_noun.most_common()
        ))
    print("  logged target/scene familiarity mismatches:", len(mismatches))
    print(
        "\n# Unkept raw seeds combine setup, planning, and physical/check failures; "
        "use the probe JSON for stage-specific failure rates."
    )


def report_eval_log(path):
    results = []
    pending = None
    with open(path) as handle:
        for line in handle:
            if "Success!" in line:
                pending = True
            elif "Fail!" in line:
                pending = False
            match = re.search(r"current seed:\s*(\d+)", line)
            if match and pending is not None:
                results.append((int(match.group(1)), pending))
                pending = None
    if not results:
        raise RuntimeError(
            f"no episodes parsed from {path}; expected Success!/Fail! plus current seed"
        )
    print("# Pick-Diverse-Object policy report")
    print("# comparison: Seen target / all-Seen scene vs Unseen target / all-Unseen scene")
    print("# interpretation: independent scenes; NOT a target-only same-scene causal gap")
    print(f"# source: {path}; episodes: {len(results)}\n")
    report_seed_results(results, "-- policy success rate --")


def main():
    if len(UNSEEN_POOL) < 4:
        raise RuntimeError(
            "UNSEEN_POOL is not locked; reporting a production familiarity split "
            "would incorrectly treat metadata candidates as validated objects"
        )
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--collection", nargs="?", const=DEFAULT_COLLECTION)
    group.add_argument("--eval-log")
    args = ap.parse_args()
    if args.eval_log:
        report_eval_log(args.eval_log)
    else:
        report_collection(args.collection or DEFAULT_COLLECTION)


if __name__ == "__main__":
    main()
