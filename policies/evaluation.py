"""Shared exact-seed oracle qualification and policy scene setup."""

from copy import deepcopy
import random
import time

from if_benchmark.seed_contracts import observed_mode


def setup_episode(env, config, args, seed, split, record, path):
    """Qualify the exact seed, then reset it for a fresh policy rollout.

    Oracle qualifications are performed for every new episode. Rendering uses
    RoboTwin's native behavior; the shared setup does not wrap environment methods.
    """
    from policies.xvla.eval import instruction_for
    from policies.xvla.outputs import write_json

    started = time.monotonic()
    random.seed(seed)
    env.setup_demo(now_ep_num=0, seed=seed, is_test=True, **config)
    if record["mode"] is not None and observed_mode(args.task, env) != record["mode"]:
        raise RuntimeError("Oracle scene mode does not match the seed contract")
    info = deepcopy(env.play_once())
    record["oracle_success"] = bool(env.plan_success and env.check_success())
    write_json(path("_oracle.json"), info)
    if not record["oracle_success"]:
        raise RuntimeError("Exact seed failed oracle qualification; no seed substitution")
    if args.task in ("bottle_verb", "attribute_select"):
        pair_qualified = type(env)._pair_ok.get(seed // 2)
        if pair_qualified is not True:
            raise RuntimeError("Successful oracle did not qualify the paired scene")
    env.close_env()
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
    record["policy_setup_seconds"] = time.monotonic() - started
    return instruction, obs
