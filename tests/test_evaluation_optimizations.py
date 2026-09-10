"""Negative controls for render deferral and oracle reuse."""
import copy
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import sys
import unittest
from unittest.mock import patch

import numpy as np

from policies.evaluation import (ObservationRenderSync, OracleCache, check_initial,
                                 initial_signature, prepare_evaluation, setup_episode)


class RenderEnv:
    render_freq = 0
    crazy_random_light = False

    def __init__(self):
        self.updates = self.physics = self.checks = 0
        self.frames = []

    def _update_render(self):
        self.updates += 1
        self.rendered = self.physics

    def get_obs(self):
        self._update_render()
        self.frames.append(self.rendered)
        return self.rendered

    def take_action(self, observe_inside=False, fail=False):
        for _ in range(4):
            self.physics += 1
            self.checks += 1
            self._update_render()
        if fail:
            raise ValueError("physics failed")
        if observe_inside:
            return self.get_obs()


class OracleEnv:
    _init_box_z = 0.8
    mode = "left"
    step_lim = 400

    def __init__(self):
        self.setups = self.oracles = self.hooks = self.closes = 0
        self.plan_success = True
        self.changed_pixel = False

    def setup_demo(self, **kwargs):
        self.setups += 1

    def play_once(self):
        self.oracles += 1
        return {"info": {"arm": self.mode}}

    def check_success(self):
        return self.plan_success

    def close_env(self):
        self.closes += 1

    def start_policy_rollout(self):
        self.hooks += 1

    def set_instruction(self, instruction):
        self.instruction = instruction

    def get_obs(self):
        return {"observation": {k: {"rgb": np.full((2, 3, 3), int(self.changed_pixel), dtype=np.uint8)}
                                for k in ("head_camera", "left_camera", "right_camera")},
                "endpose": {"left_endpose": [0., 0., 0., 1., 0., 0., 0.], "left_gripper": 1.},
                "joint_action": {"vector": np.zeros(14)}}


class OptimizationTests(unittest.TestCase):
    def test_all_six_clis_expose_both_rollback_controls(self):
        for policy in ("xvla", "lingbot_va", "lingbot_vla", "vlact", "dm05", "hy_vla"):
            module = importlib.import_module(f"policies.{policy}.eval")
            with self.subTest(policy=policy), patch.object(sys, "argv", [
                "eval.py", "--task", "arm_select", "--output-dir", "unused",
                "--render-sync", "legacy", "--no-oracle-cache", "--oracle-cache-dir", "unused-cache"]):
                with patch.object(module, "select_seeds", side_effect=InterruptedError) as selected:
                    with self.assertRaises(InterruptedError):
                        module.main()
                args = selected.call_args.args[0]
                self.assertEqual(args.render_sync, "legacy")
                self.assertTrue(args.no_oracle_cache)
                self.assertTrue(args.oracle_cache_dir.is_absolute())

    def test_physics_success_checks_and_inner_observations_preserved(self):
        old, new = RenderEnv(), RenderEnv()
        sync = ObservationRenderSync(new)
        for env in (old, new):
            env.take_action()
            env.get_obs()
            self.assertEqual(env.take_action(observe_inside=True), 8)
            env.get_obs()
        self.assertEqual(old.frames, new.frames)
        self.assertEqual((old.physics, old.checks), (new.physics, new.checks))
        self.assertEqual(sync.skipped, 8)
        self.assertEqual(new.updates, 3)

    def test_viewer_dynamic_lighting_and_exception_restore(self):
        for field in ("render_freq", "crazy_random_light"):
            env = RenderEnv()
            setattr(env, field, 1)
            sync = ObservationRenderSync(env)
            env.take_action()
            self.assertEqual(env.updates, 4)
            self.assertEqual(sync.skipped, 0)
        env = RenderEnv()
        sync = ObservationRenderSync(env)
        with self.assertRaises(ValueError):
            env.take_action(fail=True)
        self.assertEqual(sync.depth, 0)
        self.assertEqual(env.get_obs(), 4)

    def test_signature_rejects_rgb_pose_mode_limit_and_nan(self):
        env = OracleEnv()
        initial = initial_signature(env.get_obs(), env, env.mode)
        for key, value in (("images", {}), ("mode", "right"), ("step_limit", 399)):
            bad = copy.deepcopy(initial)
            bad[key] = value
            with self.assertRaises(RuntimeError):
                check_initial(initial, bad)
        for value in (0.1, float("nan")):
            bad = copy.deepcopy(initial)
            bad["state"]["joint_state"][0] = value
            with self.assertRaises(AssertionError):
                check_initial(initial, bad)

    def fixture(self, base):
        for directory in ("envs", "task_config", "description", "assets", "script"):
            (base / "robotwin" / directory).mkdir(parents=True)
        (base / "robotwin/script/collect_data.py").write_text("# test")
        (base / "policies/xvla").mkdir(parents=True)
        (base / "policies/xvla/eval.py").write_text("# test")
        (base / "robotwin/assets/mesh.bin").write_bytes(b"original")
        return base / "robotwin"

    def test_identity_reuses_across_policies_and_invalidates_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = self.fixture(base)
            with patch("policies.evaluation.ROOT", base):
                def cache(**config):
                    return OracleCache(base / "cache", target, config)
                a, b = cache(policy_name="xvla"), cache(policy_name="dm05")
                self.assertEqual(a.key("arm_select", 100000, "unseen"), b.key("arm_select", 100000, "unseen"))
                self.assertNotEqual(a.key("arm_select", 100000, "unseen"), a.key("arm_select", 100001, "unseen"))
                self.assertNotEqual(a.key("arm_select", 100000, "seen"), a.key("arm_select", 100000, "unseen"))
                self.assertNotEqual(a.identity_sha256, cache(render_freq=1).identity_sha256)
                mesh = target / "assets/mesh.bin"
                before = mesh.stat()
                mesh.write_bytes(b"modified")
                # Same size and restored mtime must still invalidate via ctime.
                os.utime(mesh, ns=(before.st_atime_ns, before.st_mtime_ns))
                self.assertNotEqual(a.identity_sha256, cache().identity_sha256)
                c = cache()
                (target / "envs/helper.py").write_text("new source")
                self.assertNotEqual(c.identity_sha256, cache().identity_sha256)
                d = cache()
                (target / "envs/helper.py").unlink()
                self.assertNotEqual(d.identity_sha256, cache().identity_sha256)

    def test_cold_hit_failure_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = self.fixture(base)
            with patch("policies.evaluation.ROOT", base):
                cache = OracleCache(base / "cache", target, {})
            args = SimpleNamespace(task="arm_select")
            def run(env, seed=100000):
                env._evaluation_optimizations = {"cache": cache}
                record = {"mode": "left", "oracle_success": False}
                with patch("policies.xvla.eval.instruction_for", return_value="Use the left arm"):
                    result = setup_episode(env, {}, args, seed, "unseen", record, lambda suffix: base / suffix)
                return result, record
            cold, hit = OracleEnv(), OracleEnv()
            _, r1 = run(cold)
            _, r2 = run(hit)
            self.assertEqual((cold.setups, cold.oracles, cold.hooks), (2, 1, 1))
            self.assertEqual((hit.setups, hit.oracles, hit.hooks), (1, 0, 1))
            self.assertEqual(r1["oracle_cache"]["status"], "miss")
            self.assertTrue(r2["oracle_cache"]["initial_verified"])
            changed = OracleEnv()
            changed.changed_pixel = True
            with self.assertRaisesRegex(RuntimeError, "scene mismatch"):
                run(changed)
            failed = OracleEnv()
            failed.plan_success = False
            with self.assertRaisesRegex(RuntimeError, "qualification"):
                run(failed, 100002)
            self.assertIsNone(cache.read(cache.key("arm_select", 100002, "unseen")))
            key = cache.key("arm_select", 100000, "unseen")
            path = base / "cache/entries" / (key + ".json")
            damaged = json.loads(path.read_text())
            damaged["payload"]["instruction"] = "wrong"
            path.write_text(json.dumps(damaged))
            with self.assertRaises(ValueError):
                cache.read(key)

    def test_unsupported_tasks_and_randomized_config_fall_back(self):
        args = SimpleNamespace(task="arm_select", task_config="demo_randomized", render_sync="observation")
        self.assertFalse(prepare_evaluation(SimpleNamespace(), {}, args)["oracle_cache_enabled"])
        args.task_config = "demo_clean"
        config = {"domain_randomization": {"random_light": True}}
        self.assertEqual(prepare_evaluation(SimpleNamespace(), config, args)["render_sync"], "legacy")

    def test_cached_pair_gate_is_restored_only_after_scene_verification(self):
        class PairEnv(OracleEnv):
            _pair_ok = {}
            mode = "pick"

            def check_success(self):
                self._pair_ok[50000] = True
                return True

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = self.fixture(base)
            with patch("policies.evaluation.ROOT", base):
                cache = OracleCache(base / "cache", target, {})
            args = SimpleNamespace(task="bottle_verb")
            with patch("policies.xvla.eval.instruction_for", return_value="Pick the bottle"):
                for changed in (False, True, False):
                    env = PairEnv()
                    env._evaluation_optimizations = {"cache": cache}
                    env.changed_pixel = changed
                    record = {"mode": "pick", "oracle_success": False}
                    if changed:
                        with self.assertRaises(RuntimeError):
                            setup_episode(env, {}, args, 100000, "unseen", record, lambda s: base / s)
                        self.assertEqual(PairEnv._pair_ok, {})
                    else:
                        setup_episode(env, {}, args, 100000, "unseen", record, lambda s: base / s)
                        self.assertTrue(PairEnv._pair_ok[50000])
                    PairEnv._pair_ok.clear()


if __name__ == "__main__":
    unittest.main()
