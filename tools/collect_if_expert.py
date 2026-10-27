#!/usr/bin/env python3
"""Collect complete expert contrast blocks using RoboTwin's native data writer."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
import html
import itertools
import json
import os
from pathlib import Path
import random
import re
import shutil
import sys
import tempfile
import traceback

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from if_benchmark.seed_contracts import (  # noqa: E402
    CURRENT_SUITE_TASKS, IF_SEED_CONTRACTS, describe_seed, expand_block,
    first_block_at_or_above, observed_mode, validate_active_seeds,
)
from if_benchmark.seed_manifest import load_manifest, manifest_sha256  # noqa: E402
from if_benchmark.seed_generation import GenerationError  # noqa: E402
from scripts import _task_bridge as bridge  # noqa: E402
from tools.generate_if_seed_manifest import (  # noqa: E402
    _load_task, _robotwin_runtime, _task_config_identity,
)


class ExpertFailure(RuntimeError):
    """A scene, plan or collected trajectory did not pass the task checker."""


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return number


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=("all", *CURRENT_SUITE_TASKS),
                        help="default: all six tasks, or the tasks in supplied manifests")
    parser.add_argument("--blocks", type=positive, default=1,
                        help="successful complete blocks per task (default: 1)")
    parser.add_argument("--seed-manifest", type=Path, action="append", default=[],
                        help="optional flat manifest file or six-task directory; repeatable")
    parser.add_argument("--start-seed", type=nonnegative, default=None,
                        help="candidate seed floor without manifests (default: 0)")
    parser.add_argument("--max-candidate-blocks", type=positive,
                        help="optional attempt limit per task; otherwise try until enough")
    parser.add_argument("--task-config", help="override config for one task without a manifest")
    parser.add_argument("--output-dir", type=Path,
                        help="new output directory (default: outputs/expert-review/<timestamp>)")
    parser.add_argument("--robotwin-dir")
    parser.add_argument("--sim-gpu", type=nonnegative, default=0)
    parser.add_argument("--instruction-type", choices=("seen", "unseen"), default="unseen")
    parser.add_argument("--allow-compatible-commit", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="show candidates/configs; no simulation or output writes")
    return parser


def collection_specs(args):
    """Resolve all inputs before starting simulation; never import legacy modes."""
    manifests = {}
    for source in args.seed_manifest:
        source = source.expanduser().resolve()
        if source.is_dir():
            names = CURRENT_SUITE_TASKS if args.task in (None, "all") else (args.task,)
            paths = [source / f"{name}.json" for name in names]
        else:
            paths = [source]
        for path in paths:
            manifest = load_manifest(path)
            name = manifest["task"]
            ids = validate_active_seeds(name, manifest["seeds"])
            if name in manifests:
                raise ValueError(f"Duplicate manifest for {name}")
            manifests[name] = dict(task=name, task_config=manifest["task_config"],
                                   block_ids=list(ids), source=str(path),
                                   manifest_sha256=manifest_sha256(manifest))
    if manifests:
        if args.start_seed is not None or args.task_config is not None:
            raise ValueError("--start-seed/--task-config cannot override a manifest")
        names = (CURRENT_SUITE_TASKS if args.task == "all" else
                 (args.task,) if args.task else tuple(manifests))
        if set(names) != set(manifests):
            raise ValueError("Manifest tasks must match --task (all requires all six)")
        specs = [manifests[name] for name in names]
        for spec in specs:
            if len(spec["block_ids"]) < args.blocks:
                raise ValueError(f"{spec['task']}: manifest has fewer than {args.blocks} blocks")
    else:
        names = CURRENT_SUITE_TASKS if args.task in (None, "all") else (args.task,)
        if args.task_config and len(names) != 1:
            raise ValueError("--task-config requires a single --task")
        specs = [dict(task=name, task_config=args.task_config or (
            "demo_clean_arm_select_v3" if name == "arm_select" else "demo_clean"),
            start_block=first_block_at_or_above(name, args.start_seed or 0),
            source="candidate scan") for name in names]
    for spec in specs:
        config = spec["task_config"]
        if Path(config).name != config or config in (".", ".."):
            raise ValueError(f"Invalid task config basename: {config!r}")
    return specs


def candidates(spec, limit=None):
    ids = iter(spec["block_ids"]) if "block_ids" in spec else itertools.count(spec["start_block"])
    if limit is not None:
        ids = itertools.islice(ids, limit)
    for block_id in ids:
        yield block_id, expand_block(spec["task"], block_id)


def mode_directory(task, seed):
    description = describe_seed(task, seed)
    return f"{description.block_offset:02d}_" + re.sub(r"[^a-zA-Z0-9_-]", "_", description.mode)


def run_episode(env, config, task, seed, directory, split, *, collect=False):
    """Native plan -> saved joint paths -> reset/replay -> HDF5 and MP4."""
    directory.mkdir(parents=True, exist_ok=True)
    phase = "collect" if collect else "plan"
    kwargs = dict(config, save_path=str(directory), need_plan=not collect,
                  save_data=collect, save_freq=15 if collect else None)
    with (directory / f"{phase}.log").open("w", encoding="utf-8") as log, redirect_stdout(log), redirect_stderr(log):
        try:
            random.seed(seed)
            try:
                env.setup_demo(now_ep_num=0, seed=seed, is_test=True, **kwargs)
            except (OSError, ImportError):
                raise
            except Exception as exc:
                raise ExpertFailure(f"setup seed {seed}: {exc}") from exc
            if observed_mode(task, env) != describe_seed(task, seed).mode:
                raise ValueError(f"{task} seed {seed}: mode differs from seed contract")
            if collect:
                env.set_path_lst(dict(kwargs, **env.load_tran_data(0)))
                env._take_picture()
                import imageio.v2 as imageio
                import numpy as np
                obs = env.now_obs
                imageio.imwrite(directory / "initial.png", np.concatenate([
                    obs["observation"][name]["rgb"] for name in
                    ("head_camera", "left_camera", "right_camera")], axis=1))
            try:
                info = deepcopy(env.play_once())
                if not env.plan_success or not env.check_success():
                    raise ExpertFailure(f"{phase} seed {seed}: expert plan/check_success failed")
            except (ExpertFailure, OSError, ImportError):
                raise
            except Exception as exc:
                raise ExpertFailure(f"{phase} seed {seed}: {exc}") from exc
            if not collect:
                env.save_traj_data(0)
                return None
            from policies.xvla.eval import instruction_for
            instruction = (env.policy_instruction(split) if hasattr(env, "policy_instruction")
                           else instruction_for(task, info, split, seed))
            env.set_instruction(instruction)
            env._take_picture()  # Include the checked terminal state.
            env.merge_pkl_to_hdf5_video()
            env.remove_data_cache()
            record = dict(task=task, task_config=config["task_config"], seed=seed,
                          mode=observed_mode(task, env), instruction=instruction,
                          instruction_type=split, plan_success=True, check_success=True,
                          frames=env.FRAME_IDX, info=info)
            write_json(directory / "episode.json", record)
            (directory / "instruction.txt").write_text(instruction + "\n", encoding="utf-8")
            return record
        except BaseException:
            traceback.print_exc()
            raise
        finally:
            env.close_env()


def write_review(output, reports):
    """Static, portable review page; paths stay relative when copying the folder."""
    cards = []
    for report in reports:
        cards.append(f"<h2>{html.escape(report['task'])}: "
                     f"{report['accepted_blocks']}/{report['requested_blocks']} blocks</h2>")
        if report.get("error"):
            cards.append(f"<p>{html.escape(report['error'])}</p>")
        for block in report["blocks"]:
            cards.append(f"<h3>Block {block['ordinal']} · seeds {block['seeds']}</h3><div class=grid>")
            for episode in block["episodes"]:
                path = html.escape(episode["path"], quote=True)
                cards.append(f"<article><h4>{html.escape(episode['mode'])} · seed {episode['seed']}</h4>"
                             f"<p>{html.escape(episode['instruction'])}</p>"
                             f'<video controls preload="none" src="{path}/video/episode0.mp4"></video>'
                             f'<details><summary>Initial cameras: head / left / right</summary>'
                             f'<img loading="lazy" src="{path}/initial.png"></details>'
                             f'<p><a href="{path}/data/episode0.hdf5">Data (HDF5)</a> · '
                             f'<a href="{path}/episode.json">Episode details</a></p></article>')
            cards.append("</div>")
    (output / "index.html").write_text("""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>IF expert review</title>
<style>body{font:16px system-ui;max-width:1400px;margin:32px auto;padding:0 20px;background:#f5f6f8}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:20px}
article{background:white;padding:16px;border-radius:8px}video,img{width:100%}h4{margin-top:0}</style>
<h1>IF expert scene review</h1><p>Successful expert demonstrations for every mode.
Candidate scans show task examples; manifest replay uses the supplied evaluation scenes.
This page does not report policy performance.</p>
""" + "\n".join(cards) + "</html>\n", encoding="utf-8")
    write_json(output / "summary.json", dict(
        complete=all(r["complete"] for r in reports), tasks=reports))


def collect_task(spec, args, report, episode_runner, progress):
    """Reject whole blocks, including replay failures; never fill modes separately."""
    task_dir = args.output_dir / spec["task"]
    task_dir.mkdir()
    for block_id, seeds in candidates(spec, args.max_candidate_blocks):
        report["attempted_blocks"] += 1
        with tempfile.TemporaryDirectory(prefix=".candidate-", dir=task_dir) as temporary:
            pending = Path(temporary)
            episodes = []
            stage, seed = "plan", seeds[0]
            try:
                for stage in ("plan", "collect"):
                    for seed in seeds:
                        print(f"{spec['task']}: {stage} seed={seed} "
                              f"mode={describe_seed(spec['task'], seed).mode}", flush=True)
                        record = episode_runner(seed, pending / mode_directory(spec["task"], seed),
                                                collect=stage == "collect")
                        if stage == "collect":
                            episodes.append(record)
            except ExpertFailure as exc:
                rejection = dict(block_id=block_id, seeds=list(seeds), stage=stage,
                                 failed_seed=seed, reason=str(exc))
                with (task_dir / "rejected.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(rejection, ensure_ascii=False) + "\n")
                report["rejected_blocks"] += 1
                print(f"{spec['task']}: skip block {block_id}: {exc}", flush=True)
                progress()
                continue
            ordinal = report["accepted_blocks"]
            destination = task_dir / f"block_{ordinal:03d}"
            pending.rename(destination)
            for episode in episodes:
                episode["path"] = (destination / mode_directory(spec["task"], episode["seed"])
                                   ).relative_to(args.output_dir).as_posix()
            report["blocks"].append(dict(ordinal=ordinal, block_id=block_id,
                                          seeds=list(seeds), episodes=episodes))
            report["accepted_blocks"] += 1
            report["complete"] = report["accepted_blocks"] == args.blocks
            print(f"{spec['task']}: {report['accepted_blocks']}/{args.blocks} blocks collected "
                  f"(seeds {list(seeds)})", flush=True)
            progress()
            if report["complete"]:
                return
    report["error"] = "Candidates exhausted before enough complete blocks were collected"
    progress()


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        specs = collection_specs(args)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        args.output_dir = (args.output_dir or REPO_ROOT / "outputs/expert-review" / stamp).expanduser().resolve()
        if args.output_dir.exists():
            raise FileExistsError(f"Output already exists; choose a new directory: {args.output_dir}")
        for spec in specs:
            first = next(candidates(spec))[1]
            print(f"{spec['task']} / {spec['task_config']}: {args.blocks} blocks, "
                  f"{len(IF_SEED_CONTRACTS[spec['task']].modes) * args.blocks} episodes; "
                  f"source={spec['source']}; first candidate={list(first)}", flush=True)
        print(f"Review: {args.output_dir / 'index.html'}", flush=True)
        if args.dry_run:
            return 0
        target = bridge.resolve_robotwin_dir(args.robotwin_dir)
        bridge.bridge(target, check=True, allow_compatible_commit=args.allow_compatible_commit)
        for spec in specs:
            spec.update(_task_config_identity(target, spec["task_config"]))
            if spec["task_config"] == "demo_clean_arm_select_v3":
                installed = target / "task_config/demo_clean_arm_select_v3.yml"
                if installed.read_bytes() != (REPO_ROOT / "tasks/task_config" / installed.name).read_bytes():
                    raise ValueError("Installed Arm config differs from tasks/task_config")
        if shutil.which("ffmpeg") is None:
            raise ValueError("ffmpeg is required for native collection videos")
    except (ValueError, OSError, bridge.BridgeError, GenerationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    reports = [dict(**spec, requested_blocks=args.blocks, accepted_blocks=0,
                    attempted_blocks=0, rejected_blocks=0, complete=False, blocks=[])
               for spec in specs]
    args.output_dir.mkdir(parents=True)
    progress = lambda: write_review(args.output_dir, reports)
    progress()
    try:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(args.sim_gpu)
        from tools.sim_device import pin_renderer
        pin_renderer()
        with _robotwin_runtime(target) as native:
            description_path = str(target / "description/utils")
            sys.path.insert(0, description_path)
            try:
                for spec, report in zip(specs, reports):
                    env, config = _load_task(native, spec["task"], spec["task_config"])
                    def episode_runner(seed, directory, *, collect):
                        return run_episode(env, config, spec["task"], seed, directory,
                                           args.instruction_type, collect=collect)
                    collect_task(spec, args, report, episode_runner, progress)
            finally:
                sys.path.remove(description_path)
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        traceback.print_exc()
        for report in reports:
            if not report["complete"]:
                report["error"] = f"{type(exc).__name__}: {exc}"
        progress()
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0 if all(report["complete"] for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
