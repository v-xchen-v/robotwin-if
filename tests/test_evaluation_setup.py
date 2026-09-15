"""CPU contracts for exact-seed qualification followed by fresh policy setup."""
import json
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from policies.evaluation import finalize_episode_success, setup_episode


class FinalVerdictTests(unittest.TestCase):
    def test_terminal_success_is_still_an_action_limit_termination(self):
        for success in (True, False):
            env=SimpleNamespace(take_action_cnt=700,step_lim=700,
                                finalize_policy_success=lambda: success)
            record={'success':False}
            finalize_episode_success(env,record)
            self.assertEqual(record,dict(success=success,status='success' if success else 'failure',
                                          termination='action_limit'))

    def test_early_success_and_timeout_are_unchanged_for_other_tasks(self):
        for count,success in ((50,True),(700,True),(700,False)):
            record={'success':success}
            finalize_episode_success(SimpleNamespace(take_action_cnt=count,step_lim=700),record)
            self.assertEqual(record['success'],success)
            self.assertEqual(record['termination'],'task_success' if success else 'action_limit')

    def test_finalization_error_is_not_silently_converted_to_policy_failure(self):
        def finalize():raise RuntimeError('Incomplete action budget')
        with self.assertRaisesRegex(RuntimeError,'Incomplete action budget'):
            finalize_episode_success(SimpleNamespace(finalize_policy_success=finalize),{'success':False})


class OracleEnv:
    step_lim = 400
    _init_box_z = 0.8
    mode = "left"
    axis, value = "color", 0
    AXIS_VALUES = {"color": ("red", "blue")}
    _pair_ok = {}

    def __init__(self):
        self.events, self.setups, self.random_values = [], [], []
        self.plan_success = self.success = True
        self.info = {"info": {"arm": "left"}}

    def setup_demo(self, **kwargs):
        self.events.append("setup")
        self.setups.append(kwargs)
        self.random_values.append(random.random())

    def play_once(self):
        self.events.append("oracle")
        return self.info

    def check_success(self):
        self.events.append("check")
        return self.success

    def close_env(self):
        self.events.append("close")
        self.info["info"].clear()  # Setup must retain a copy of the oracle info.

    def start_policy_rollout(self):
        self.events.append("rollout")

    def set_instruction(self, instruction):
        self.events.append("instruction")
        self.instruction = instruction

    def get_obs(self):
        self.events.append("observation")
        return {"ready": True}


class EpisodeSetupTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.env = OracleEnv()
        self.record = {"mode": "left"}
        self.args = SimpleNamespace(task="arm_select")
        state = random.getstate()
        self.addCleanup(random.setstate, state)
        instruction = patch("policies.xvla.eval.instruction_for", return_value="Use the left arm")
        self.instruction = instruction.start()
        self.addCleanup(instruction.stop)

    def path(self, suffix):
        return self.base / ("episode" + suffix)

    def setup(self):
        return setup_episode(self.env, {"eval_mode": True}, self.args, 200000,
                             "unseen", self.record, self.path)

    def test_qualify_close_and_reset_exact_seed_before_policy(self):
        self.assertEqual(self.setup(), ("Use the left arm", {"ready": True}))
        self.assertEqual(self.env.events, ["setup", "oracle", "check", "close", "setup",
                                          "rollout", "instruction", "observation"])
        expected = dict(now_ep_num=0, seed=200000, is_test=True, eval_mode=True)
        self.assertEqual(self.env.setups, [expected, expected])
        self.assertEqual(self.env.random_values[0], self.env.random_values[1])
        info = {"info": {"arm": "left"}}
        self.instruction.assert_called_once_with("arm_select", info, "unseen", 200000)
        self.assertEqual(json.loads(self.path("_oracle.json").read_text()), info)
        self.assertTrue(self.record["oracle_success"])
        self.assertEqual(self.record["step_limit"], 400)
        self.setup()
        self.assertEqual(self.env.events.count("oracle"), 2)

    def test_oracle_negative_never_substitutes_seed_or_starts_policy(self):
        for field in ("plan_success", "success"):
            with self.subTest(field=field):
                self.env = OracleEnv()
                setattr(self.env, field, False)
                with self.assertRaisesRegex(RuntimeError, "Exact seed failed oracle qualification"):
                    self.setup()
                self.assertFalse(self.record["oracle_success"])
                self.assertEqual([s["seed"] for s in self.env.setups], [200000])
                self.assertNotIn("rollout", self.env.events)
                self.instruction.assert_not_called()

    def test_mode_mismatch_in_either_scene_stops_before_policy(self):
        for modes, stage in ((["right"], "Oracle"), (["left", "right"], "Policy")):
            with self.subTest(stage=stage), patch("policies.evaluation.observed_mode", side_effect=modes):
                with self.assertRaisesRegex(RuntimeError, stage + " scene mode"):
                    self.setup()
                self.assertNotIn("rollout", self.env.events)

    def test_arm_success_baseline_is_required(self):
        self.env._init_box_z = None
        with self.assertRaisesRegex(RuntimeError, "policy success baseline"):
            self.setup()
        self.instruction.assert_not_called()

    def test_pair_qualification_must_be_proved_by_task(self):
        for task, mode in (("bottle_verb", "pick"), ("attribute_select", "color:red")):
            for qualified in (None, False, True):
                with self.subTest(task=task, qualified=qualified), \
                     patch.object(OracleEnv, "_pair_ok", {100000: qualified}):
                    self.env = OracleEnv()
                    self.env.mode = mode
                    self.args.task = task
                    self.record = {"mode": mode}
                    if qualified is True:
                        self.setup()
                        self.assertIn("rollout", self.env.events)
                    else:
                        with self.assertRaisesRegex(RuntimeError, "paired scene"):
                            self.setup()
                        self.assertNotIn("rollout", self.env.events)

    def test_raw_task_does_not_require_if_mode_or_rollout_hook(self):
        self.args.task = "ring_bell"
        self.record["mode"] = None
        # A native task need not implement the IF hook.
        class NativeEnv:
            pass
        native = NativeEnv()
        for method in ("setup_demo", "play_once", "check_success", "close_env", "set_instruction", "get_obs"):
            setattr(native, method, getattr(self.env, method))
        native.plan_success, native.step_lim = True, 400
        setup_episode(native, {}, self.args, 2000, "seen", self.record, self.path)
        self.instruction.assert_called_once_with("ring_bell", {"info": {"arm": "left"}}, "seen", 2000)
        self.assertNotIn("rollout", self.env.events)


if __name__ == "__main__":
    unittest.main()
