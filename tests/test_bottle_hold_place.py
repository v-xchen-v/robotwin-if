"""Behavioral tests for the experimental terminal task and paired runner."""

import ast
import math
from pathlib import Path
from copy import deepcopy
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from policies.evaluation import setup_episode
from tasks.envs._bottle_hold_place import HoldPlaceMonitor, INSTRUCTIONS, mode_for_seed
from tools.bottle_hold_place import check_policy_observation, pair_seeds, selected_seeds, summarize_pairs


ROOT = Path(__file__).resolve().parents[1]


def feed(monitor, seconds=5.2, *, position=(0, 0, 1), clearance=.12,
         held=True, supported=False, motion=None):
    start = monitor.time
    for i in range(1, round(seconds / .02) + 1):
        t = start + i * .02
        p, q = position, (1, 0, 0, 0)
        if motion:
            p, q = motion(t)
        monitor.observe(t, p, q, (0, 0), clearance, held, supported)


class MonitorTests(unittest.TestCase):
    def test_hold_requires_five_seconds_while_place_requires_two(self):
        for mode, required_seconds in (("hold", 5.0), ("place", 2.0)):
            with self.subTest(mode=mode):
                monitor = HoldPlaceMonitor()
                # Both instructions require a prior pickup.
                feed(monitor, .1, position=(.2, 0, 1))
                state = dict(held=mode == "hold", supported=mode == "place",
                             clearance=.12 if mode == "hold" else 0)
                feed(monitor, required_seconds, **state)
                self.assertAlmostEqual(monitor.stable_seconds, required_seconds - .02)
                self.assertFalse(monitor.success(mode))
                feed(monitor, .02, **state)
                self.assertAlmostEqual(monitor.stable_seconds, required_seconds)
                self.assertTrue(monitor.success(mode))

    def test_brief_hover_before_placement_never_passes_hold(self):
        for pause_seconds in (2.2, 3.0, 4.9):
            with self.subTest(pause_seconds=pause_seconds):
                monitor = HoldPlaceMonitor()
                feed(monitor, pause_seconds)
                self.assertFalse(monitor.success("hold"))
                feed(monitor, 2.2, held=False, supported=True, clearance=0)
                self.assertFalse(monitor.success("hold"))
                self.assertTrue(monitor.success("place"))

    def test_interrupted_hover_must_restart_the_full_five_seconds(self):
        interruptions = (
            dict(held=False), dict(supported=True), dict(clearance=.01),
            dict(position=(.2, 0, 1)), dict(position=(0, 0, 1.02)),
            dict(motion=lambda t: ((0, 0, 1), (math.cos(math.radians(10)),
                                              math.sin(math.radians(10)), 0, 0))),
        )
        for interruption in interruptions:
            with self.subTest(interruption=interruption):
                monitor = HoldPlaceMonitor()
                feed(monitor, 4.0)
                feed(monitor, .02, **interruption)
                feed(monitor, 2.2)
                self.assertFalse(monitor.success("hold"))
                feed(monitor, 2.8)
                self.assertFalse(monitor.success("hold"))
                feed(monitor, .02)
                self.assertTrue(monitor.success("hold"))

    def test_hold_and_released_place_are_exclusive(self):
        for mode in ("hold", "place"):
            with self.subTest(mode=mode):
                monitor = HoldPlaceMonitor()
                feed(monitor, .1, position=(.2, 0, 1))
                feed(monitor, 5.2 if mode == "hold" else 2.2,
                     held=mode == "hold", supported=mode == "place",
                     clearance=.12 if mode == "hold" else 0)
                self.assertTrue(monitor.success(mode))
                self.assertFalse(monitor.success("place" if mode == "hold" else "hold"))

    def test_wrong_location_height_contact_and_unreleased_bottle_fail(self):
        for kwargs in (dict(position=(.2, 0, 1)), dict(clearance=.01), dict(clearance=.3),
                       dict(held=False), dict(supported=True),
                       dict(held=False, supported=True, position=(.2, 0, 1))):
            with self.subTest(kwargs=kwargs):
                monitor = HoldPlaceMonitor()
                feed(monitor, **kwargs)
                self.assertFalse(monitor.success("hold"))
                self.assertFalse(monitor.success("place"))

    def test_bottle_pushed_onto_pad_without_a_pick_does_not_count_as_place(self):
        monitor = HoldPlaceMonitor()
        feed(monitor, 2.2, held=False, supported=True, clearance=0)
        self.assertFalse(monitor.success("place"))

    def test_queries_do_not_create_stability_and_observation_gap_resets(self):
        monitor = HoldPlaceMonitor()
        feed(monitor, .1)
        for _ in range(1000):
            self.assertFalse(monitor.success("hold"))
        monitor.observe(10, (0, 0, 1), (1, 0, 0, 0), (0, 0), .12, True, False)
        self.assertFalse(monitor.success("hold"))
        feed(monitor)
        self.assertTrue(monitor.success("hold"))

    def test_late_drop_or_regrasp_invalidates_transient_success(self):
        monitor = HoldPlaceMonitor()
        feed(monitor)
        self.assertTrue(monitor.success("hold"))
        feed(monitor, .1, held=False)
        self.assertFalse(monitor.success("hold"))
        feed(monitor, 2.2, held=False, supported=True, clearance=0)
        self.assertTrue(monitor.success("place"))
        feed(monitor, .1, supported=True, clearance=0)
        self.assertFalse(monitor.success("place"))

    def test_translation_or_rotation_shaking_never_becomes_stable(self):
        for rotating in (True, False):
            def motion(t):
                degrees = 20 * math.sin(t * 10) if rotating else 0
                q = (math.cos(math.radians(degrees / 2)), math.sin(math.radians(degrees / 2)), 0, 0)
                return ((0, 0, 1) if rotating else (.03 * math.sin(t * 10), 0, 1)), q
            monitor = HoldPlaceMonitor()
            feed(monitor, 7, motion=motion)
            self.assertFalse(monitor.success("hold"))
            # This experiment allows correction followed by sustained success.
            feed(monitor)
            self.assertTrue(monitor.success("hold"))

    def test_quaternion_sign_and_small_physical_jitter_are_tolerated(self):
        monitor = HoldPlaceMonitor()
        feed(monitor, motion=lambda t: ((.001 * math.sin(t * 10), 0, 1),
                                       (-1 if round(t * 50) % 2 else 1, 0, 0, 0)))
        self.assertTrue(monitor.success("hold"))


def task_class():
    # Execute the real task methods with only the heavyweight simulator imports
    # omitted; the terminal lifecycle can then be checked on a physical trace.
    path = ROOT / "tasks/envs/bottle_hold_place.py"
    tree = ast.parse(path.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    namespace = dict(Base_Task=object, INSTRUCTIONS=INSTRUCTIONS)
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["bottle_hold_place"]


class TerminalTaskTests(unittest.TestCase):
    def test_both_modes_wait_for_full_budget_and_use_terminal_state(self):
        for mode in ("hold", "place"):
            env = task_class()()
            env.mode, env.monitor, env.step_lim = mode, HoldPlaceMonitor(), 700
            env._terminal = False
            feed(env.monitor, .1, position=(.2, 0, 1))
            feed(env.monitor, 5.2 if mode == "hold" else 2.2,
                 held=mode == "hold", supported=mode == "place",
                 clearance=.12 if mode == "hold" else 0)
            self.assertTrue(env.check_success())
            env.start_policy_rollout()
            self.assertFalse(env.check_success())
            env.take_action_cnt = 699
            with self.assertRaisesRegex(RuntimeError, "complete policy action budget"):
                env.finalize_policy_success()
            env.take_action_cnt = 700
            self.assertFalse(env.check_success())
            self.assertTrue(env.finalize_policy_success())
            feed(env.monitor, .1, held=False, supported=False)
            self.assertFalse(env.finalize_policy_success())

    def test_terminal_hold_rejects_a_short_pause_or_later_placement(self):
        for pause_seconds in (2.2, 4.0, 5.2):
            for place_after in (False, True):
                with self.subTest(pause_seconds=pause_seconds, place_after=place_after):
                    env = task_class()()
                    env.mode, env.monitor, env.step_lim = "hold", HoldPlaceMonitor(), 700
                    env.start_policy_rollout()
                    feed(env.monitor, pause_seconds)
                    if place_after:
                        feed(env.monitor, 2.2, held=False, supported=True, clearance=0)
                    env.take_action_cnt = 700
                    self.assertFalse(env.check_success())
                    self.assertEqual(env.finalize_policy_success(),
                                     pause_seconds >= 5 and not place_after)

    def test_task_names_are_not_accepted_as_instructions(self):
        env = task_class()()
        env.mode = "hold"
        self.assertEqual(env.policy_instruction("unseen"), INSTRUCTIONS["hold"])
        with self.assertRaises(ValueError):
            env.policy_instruction("task-name")


class ExperimentTests(unittest.TestCase):
    def test_explicit_scenes_always_expand_to_distinct_complete_blocks(self):
        self.assertEqual(selected_seeds(0, None, [0, 3]), [0, 1, 6, 7])
        self.assertEqual(selected_seeds(2, 2, None), [4, 5, 6, 7])
        for args in ((0, None, []), (0, None, [0, 0]), (0, None, [-1]),
                     (0, None, [2**31]), (1, None, [3]), (0, 2, [3])):
            with self.subTest(args=args), self.assertRaises(ValueError):
                selected_seeds(*args)

    def test_policy_scene_guard_rejects_camera_state_instruction_and_budget_changes(self):
        import numpy as np
        from policies.xvla.client import CAMERAS, encode_proprio
        obs = {"observation": {c: {"rgb": np.zeros((2, 3, 3), dtype=np.uint8)} for c in CAMERAS},
               "endpose": {f"{arm}_{key}": value for arm in ("left", "right")
                           for key, value in (("endpose", [0, 0, 1, 1, 0, 0, 0]), ("gripper", 1))}}
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            np.savez_compressed(directory / "bottle_hold_place_ep0_initial.npz",
                                proprio=encode_proprio(obs), **{c: obs["observation"][c]["rgb"] for c in CAMERAS})
            env = SimpleNamespace(step_lim=700, ACTION_LIMIT=700)
            check_policy_observation(directory, 0, INSTRUCTIONS["hold"], obs, env)
            for field in ("camera", "state", "instruction", "budget"):
                altered = deepcopy(obs)
                instruction = INSTRUCTIONS["hold"]
                env.step_lim = 700
                if field == "camera":
                    altered["observation"][CAMERAS[1]]["rgb"][0, 0, 0] = 1
                elif field == "state":
                    altered["endpose"]["left_endpose"][0] = .1
                elif field == "instruction":
                    instruction = INSTRUCTIONS["place"]
                else:
                    env.step_lim = 699
                with self.subTest(field=field), self.assertRaises((AssertionError, RuntimeError)):
                    check_policy_observation(directory, 0, instruction, altered, env)

    def test_balanced_uint32_seeds_and_pair_success(self):
        self.assertEqual(pair_seeds(4, 2), [8, 9, 10, 11])
        for args in ((-1, 2), (0, 0), (2**31 - 1, 2)):
            with self.assertRaises(ValueError):
                pair_seeds(*args)
        records = [dict(seed=s, mode=mode_for_seed(s), success=s != 9) for s in pair_seeds(4, 2)]
        summary = summarize_pairs(records)
        self.assertEqual(summary["both_success"], 1)
        self.assertEqual(summary["per_mode"]["hold"], dict(episodes=2, successes=2))
        self.assertEqual(summary["per_mode"]["place"], dict(episodes=2, successes=1))

    def test_opt_in_instruction_hook_preserves_reset_mode_and_bypasses_generator(self):
        events = []
        env = SimpleNamespace(
            mode="hold", plan_success=True, step_lim=700,
            setup_demo=lambda **kw: events.append(kw["seed"]),
            play_once=lambda: {"mode": "hold", "info": {}},
            check_success=lambda: True, close_env=lambda: None,
            start_policy_rollout=lambda: None,
            policy_instruction=lambda split: INSTRUCTIONS["hold"],
            set_instruction=lambda instruction: events.append(instruction),
            get_obs=lambda: {"ready": True})
        for initial_mode in (None, "hold", "place"):
            with self.subTest(initial_mode=initial_mode):
                events.clear()
                record = {"mode": initial_mode}
                with tempfile.TemporaryDirectory() as tmp, patch("policies.xvla.eval.instruction_for") as generator:
                    if initial_mode == "place":
                        with self.assertRaisesRegex(RuntimeError, "mode does not match"):
                            setup_episode(env, {}, SimpleNamespace(task="bottle_hold_place"), 8,
                                          "unseen", record, lambda suffix: Path(tmp) / suffix)
                        self.assertEqual(events, [8])
                        continue
                    result = setup_episode(env, {}, SimpleNamespace(task="bottle_hold_place"), 8,
                                           "unseen", record, lambda suffix: Path(tmp) / suffix)
                generator.assert_not_called()
                self.assertEqual(record["mode"], "hold")
                self.assertEqual(events[:2], [8, 8])
                self.assertEqual(result, (INSTRUCTIONS["hold"], {"ready": True}))


if __name__ == "__main__":
    unittest.main()
