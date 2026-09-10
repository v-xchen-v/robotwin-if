"""Shared IF evaluation optimizations; no change to physics or policy cadence."""

from copy import deepcopy
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import time

from if_benchmark.seed_contracts import IF_SEED_CONTRACTS, observed_mode

ROOT = Path(__file__).resolve().parents[1]
CAMERAS = ("head_camera", "left_camera", "right_camera")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(canonical(value) + "\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class ObservationRenderSync:
    """Defer only take_action's redundant updates; get_obs always flushes.

    The physics loop and every check_success call still execute. Methods outside
    take_action (including oracle planning/setup) retain their original behavior.
    Dynamic lighting and viewers fall back to the original updates.
    """

    def __init__(self, env):
        self.depth = 0
        self.skipped = 0
        self.performed = 0
        update, take, observe = env._update_render, env.take_action, env.get_obs

        def update_render(*args, **kwargs):
            if self.depth and not env.render_freq and not env.crazy_random_light:
                self.skipped += 1
                return None
            self.performed += 1
            return update(*args, **kwargs)

        def take_action(*args, **kwargs):
            self.depth += 1
            try:
                return take(*args, **kwargs)
            finally:
                self.depth -= 1

        def get_obs(*args, **kwargs):
            depth, self.depth = self.depth, 0
            try:
                return observe(*args, **kwargs)
            finally:
                self.depth = depth

        env._update_render = update_render
        env.take_action = take_action
        env.get_obs = get_obs


class OracleCache:
    """Content-addressed successful qualifications, shared across policies.

    File digests are memoized against device/inode/size/mtime/ctime. Every new
    evaluator walks the inputs again, so edits, additions and deletions invalidate
    the identity without repeatedly reading all 16 GB of assets.
    """

    def __init__(self, directory, robotwin, config):
        self.directory = Path(directory).resolve()
        robotwin = Path(robotwin).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        index_path = self.directory / "file-digests.json"
        previous = json.loads(index_path.read_text()) if index_path.exists() else {}
        index, files = {}, {}
        roots = [robotwin / name for name in ("envs", "task_config", "description", "assets")]
        roots += [ROOT / "tasks", ROOT / "if_benchmark"]
        roots += [(robotwin / config[name]).resolve() for name in ("left_robot_file", "right_robot_file")
                  if config.get(name)]
        paths = {robotwin / "script/collect_data.py", Path(__file__), ROOT / "policies/xvla/eval.py"}
        for root in roots:
            for directory_name, dirs, names in os.walk(root, followlinks=True):
                dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", ".git"))
                paths.update(Path(directory_name) / name for name in names
                             if not name.endswith((".pyc", ".log")))
        for path in sorted(paths):
            stat = path.stat()
            stamp = [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
            key = str(path)
            old = previous.get(key, {})
            if old.get("stat") == stamp:
                sha = old["sha256"]
            else:
                hasher = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        hasher.update(block)
                after = path.stat()
                if stamp != [after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns]:
                    raise RuntimeError(f"Evaluation input changed while hashing: {path}")
                sha = hasher.hexdigest()
            index[key] = {"stat": stamp, "sha256": sha}
            files[key] = sha
        atomic_json(index_path, index)
        # These fields only label output; all simulation/instruction inputs stay.
        config = {k: v for k, v in config.items() if k not in ("policy_name", "ckpt_setting", "save_path")}
        versions = {}
        for name in ("sapien", "torch", "numpy", "mplib", "toppra", "trimesh", "transforms3d", "PyYAML", "curobo"):
            try:
                versions[name] = metadata.version(name)
            except metadata.PackageNotFoundError:
                versions[name] = None
        self.identity = {"schema": 1, "files": files, "config": config,
                         "versions": versions, "python": sys.version, "executable": sys.executable}
        driver = Path("/proc/driver/nvidia/version")
        self.identity["nvidia_driver"] = driver.read_text() if driver.exists() else None
        self.identity_sha256 = digest(self.identity)
        identity_path = self.directory / "identities" / (self.identity_sha256 + ".json")
        if not identity_path.exists():
            atomic_json(identity_path, self.identity)

    def key(self, task, seed, split):
        return digest({"identity": self.identity_sha256, "task": task, "seed": seed, "split": split})

    def read(self, key):
        path = self.directory / "entries" / (key + ".json")
        if not path.exists():
            return None
        entry = json.loads(path.read_text())
        payload = entry["payload"]
        if entry["sha256"] != digest(payload) or payload["key"] != key or payload["oracle_success"] is not True:
            raise ValueError(f"Invalid oracle cache entry: {path}")
        return payload

    def write(self, key, payload):
        atomic_json(self.directory / "entries" / (key + ".json"),
                    {"payload": payload, "sha256": digest(payload)})


def add_evaluation_arguments(parser):
    parser.add_argument("--render-sync", choices=("observation", "legacy"), default="observation",
                        help="Defer redundant IF demo_clean render updates until observation")
    parser.add_argument("--oracle-cache-dir", type=Path, default=ROOT / "outputs/policy-eval/oracle-cache",
                        help="Shared, versioned IF demo_clean oracle qualifications")
    parser.add_argument("--no-oracle-cache", action="store_true", help="Execute oracle for every episode")


def prepare_evaluation(env, config, args, *, robotwin=None):
    supported = args.task in IF_SEED_CONTRACTS and args.task_config == "demo_clean"
    clean = config.get("domain_randomization", {})
    supported = supported and not any(clean.get(k, False) for k in
                                      ("random_light", "random_background", "cluttered_table",
                                       "random_head_camera_dis", "random_table_height", "random_embodiment"))
    supported = supported and not config.get("render_freq") and not config.get("save_data")
    sync = ObservationRenderSync(env) if supported and args.render_sync == "observation" else None
    started = time.monotonic()
    cache = OracleCache(args.oracle_cache_dir, robotwin or args.robotwin_dir, config) if supported and not args.no_oracle_cache else None
    env._evaluation_optimizations = {"sync": sync, "cache": cache}
    return {"render_sync": "observation" if sync else "legacy", "oracle_cache_enabled": cache is not None,
            "oracle_identity_sha256": cache.identity_sha256 if cache else None,
            "identity_seconds": time.monotonic() - started,
            "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def initial_signature(obs, env, mode):
    import numpy as np
    images = {}
    for name in CAMERAS:
        rgb = np.asarray(obs["observation"][name]["rgb"])
        images[name] = {"shape": list(rgb.shape), "dtype": str(rgb.dtype),
                        "sha256": hashlib.sha256(rgb.tobytes()).hexdigest()}
    state = {k: np.asarray(v).tolist() for k, v in obs["endpose"].items()}
    state["joint_state"] = np.asarray(obs["joint_action"]["vector"]).tolist()
    return {"images": images, "state": state, "mode": mode, "step_limit": env.step_lim}


def check_initial(expected, actual):
    import numpy as np
    for key in ("images", "mode", "step_limit"):
        if actual[key] != expected[key]:
            raise RuntimeError(f"Oracle cache initial scene mismatch: {key}")
    if actual["state"].keys() != expected["state"].keys():
        raise RuntimeError("Oracle cache initial state fields changed")
    for key in actual["state"]:
        np.testing.assert_allclose(actual["state"][key], expected["state"][key], rtol=0, atol=1e-6,
                                   equal_nan=False, err_msg=f"Oracle cache initial state mismatch: {key}")


def setup_episode(env, config, args, seed, split, record, path):
    """Return the same policy-ready scene, instruction and initial observation."""
    from policies.xvla.eval import instruction_for
    from policies.xvla.outputs import write_json
    cache = getattr(env, "_evaluation_optimizations", {}).get("cache")
    key = cache.key(args.task, seed, split) if cache else None
    entry = cache.read(key) if cache else None
    record["oracle_cache"] = {"status": "hit" if entry else ("miss" if cache else "disabled"),
                              "key": key, "identity_sha256": cache.identity_sha256 if cache else None}
    started = time.monotonic()
    if entry is None:
        random.seed(seed)
        env.setup_demo(now_ep_num=0, seed=seed, is_test=True, **config)
        if record["mode"] is not None and observed_mode(args.task, env) != record["mode"]:
            raise RuntimeError("Oracle scene mode does not match the seed contract")
        info = deepcopy(env.play_once())
        record["oracle_success"] = bool(env.plan_success and env.check_success())
        write_json(path("_oracle.json"), info)
        if not record["oracle_success"]:
            raise RuntimeError("Exact seed failed oracle qualification; no seed substitution")
        pair_qualified = None
        if args.task in ("bottle_verb", "attribute_select"):
            pair_qualified = type(env)._pair_ok.get(seed // 2)
            if pair_qualified is not True:
                raise RuntimeError("Successful oracle did not qualify the paired scene")
        env.close_env()
    else:
        info = entry["oracle_info"]
        record["oracle_success"] = True
        write_json(path("_oracle.json"), info)
    record["oracle_seconds"] = time.monotonic() - started
    started = time.monotonic()
    random.seed(seed)
    env.setup_demo(now_ep_num=0, seed=seed, is_test=True, **config)
    if record["mode"] is not None and observed_mode(args.task, env) != record["mode"]:
        raise RuntimeError("Policy scene mode does not match the seed contract")
    if args.task == "arm_select" and env._init_box_z is None:
        raise RuntimeError("arm_select did not initialize its policy success baseline")
    if hasattr(env, "start_policy_rollout"):
        env.start_policy_rollout()
    instruction = instruction_for(args.task, info, split, seed)
    env.set_instruction(instruction)
    record.update(instruction=instruction, step_limit=env.step_lim)
    obs = env.get_obs()
    if cache:
        signature = initial_signature(obs, env, record["mode"])
        if entry:
            if instruction != entry["instruction"]:
                raise RuntimeError("Oracle cache instruction mismatch")
            check_initial(entry["initial"], signature)
            # These tasks' success checks otherwise create a buddy simulator on
            # the first successful grasp. Reuse only the actual pair-gate proof
            # established by check_success during the cached oracle run.
            if args.task in ("bottle_verb", "attribute_select"):
                if entry.get("pair_qualified") is not True:
                    raise RuntimeError("Oracle cache lacks paired-scene qualification")
                if type(env)._pair_ok.get(seed // 2) is False:
                    raise RuntimeError("Conflicting paired-scene qualification")
                type(env)._pair_ok[seed // 2] = True
        else:
            cache.write(key, {"key": key, "oracle_success": True, "oracle_info": info,
                              "instruction": instruction, "initial": signature,
                              "pair_qualified": pair_qualified})
        record["oracle_cache"]["initial_verified"] = bool(entry)
    record["policy_setup_seconds"] = time.monotonic() - started
    return instruction, obs


def render_counters(env):
    sync = getattr(env, "_evaluation_optimizations", {}).get("sync")
    if sync is None:
        return {"mode": "legacy"}
    counts = {"mode": "observation", "skipped_updates": sync.skipped, "performed_updates": sync.performed}
    sync.skipped = sync.performed = 0
    return counts
