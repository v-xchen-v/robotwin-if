"""Keep parallel workers isolated and respect measured resource budgets."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from tools import run_parallel_stapler_suite as parallel


class ParallelStaplerTest(unittest.TestCase):
    def setUp(self):
        self.rows = [[0, 16000, 49140, 75, 40], [1, 4091, 49140, 65, 20]]
        self.ram = 32 * 1024**3

    def test_second_lane_can_join_existing_xvla_without_restarting_it(self):
        self.assertTrue(parallel.admission('lingbot_va', ['xvla'], self.rows, self.ram))

    def test_large_model_pair_is_deferred_but_a_fitting_pair_can_run(self):
        self.rows[1][1] = 33854
        self.assertFalse(parallel.admission('dm05', ['lingbot_va'], self.rows, self.ram))
        self.assertTrue(parallel.admission('vlact', ['lingbot_va'], self.rows, self.ram))

    def test_no_third_lane_or_second_client_for_same_model(self):
        self.assertFalse(parallel.admission('xvla', ['xvla'], self.rows, self.ram))
        self.assertFalse(parallel.admission('hy_vla', ['xvla', 'vlact'], self.rows, self.ram))

    def test_live_pressure_blocks_model_admission(self):
        for gpu, column, value in ((0, 1, 32768), (1, 1, 44000), (0, 3, 83)):
            with self.subTest(gpu=gpu, column=column):
                rows = [row.copy() for row in self.rows]
                rows[gpu][column] = value
                self.assertFalse(parallel.admission('lingbot_va', ['xvla'], rows, self.ram))
        self.assertFalse(parallel.admission('lingbot_va', ['xvla'], self.rows, 8 * 1024**3))

    def test_worker_keeps_formal_scene_guard_and_restores_hooks_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            original = Mock(return_value={'seed': 110000, 'status': 'success'})
            module = SimpleNamespace(run_episode=original)
            guard = parallel.formal.check_scene

            def formal_worker(run, policy, task, output):
                self.assertIs(parallel.formal.check_scene, guard)
                self.assertEqual((run, policy, task), (base, 'xvla', 'press_lift_stapler'))
                module.run_episode(None, {}, None, None, 110000, 'unseen', output, block=0)
                raise RuntimeError('simulator error')

            def cooled(env, episode, cooling, *args, **kwargs):
                return episode(env, *args, **kwargs)

            with patch.object(parallel, 'check_sources'), \
                 patch.object(parallel.importlib, 'import_module', return_value=module), \
                 patch.object(parallel, 'device_rows', return_value=[dict(index=0, uuid='GPU-sim')]), \
                 patch.object(parallel, 'CoordinatedActionCooling'), \
                 patch.object(parallel, 'cooled_episode', side_effect=cooled), \
                 patch.object(parallel.formal, 'worker', side_effect=formal_worker):
                with self.assertRaisesRegex(RuntimeError, 'simulator error'):
                    parallel.worker(base, 'xvla', base / 'batch')
            original.assert_called_once_with(None, {}, None, None, 110000, 'unseen', base / 'batch', block=0)
            self.assertIs(module.run_episode, original)
            self.assertIs(parallel.formal.check_scene, guard)

    def test_cooling_gate_pauses_peers_and_releases_them_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            first = parallel.CoordinatedActionCooling(base, 'GPU-sim', base / 'first.json')
            second = parallel.CoordinatedActionCooling(base, 'GPU-sim', base / 'second.json')
            rows = [[dict(uuid='GPU-sim', temperature=t)] for t in (80, 79, 74, 79)]
            with patch.object(parallel, 'device_rows', side_effect=rows):
                self.assertTrue(first.cooling_gate()[1])
                self.assertTrue(second.cooling_gate()[1])
                self.assertFalse(second.cooling_gate()[1])
                # A resumed peer may warm the GPU to 79 C. The first worker
                # must still resume instead of waiting alone for 74 C again.
                self.assertFalse(first.cooling_gate()[1])

    def test_admission_wait_preserves_empty_episode_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output = base / 'batch' / parallel.TASK
            output.mkdir(parents=True)

            def episode(env, config, client, args, seed, split, directory, block=None):
                self.assertFalse(list(directory.glob(parallel.formal.prefix(parallel.TASK, seed) + '*')))
                return dict(seed=seed, status='success')

            module = SimpleNamespace(run_episode=episode)
            def formal_worker(*args):
                return module.run_episode(None, {}, None, None, 110000, 'unseen', output, block=0)
            def cooled(env, original, cooling, *args, **kwargs):
                return original(env, *args, **kwargs)

            with patch.object(parallel, 'check_sources'), \
                 patch.object(parallel.importlib, 'import_module', return_value=module), \
                 patch.object(parallel, 'device_rows', return_value=[dict(index=0, uuid='GPU-sim')]), \
                 patch.object(parallel.CoordinatedActionCooling, 'before_action',
                              autospec=True, side_effect=lambda cooling: cooling.record('cooling')), \
                 patch.object(parallel, 'cooled_episode', side_effect=cooled), \
                 patch.object(parallel.formal, 'worker', side_effect=formal_worker):
                result = parallel.worker(base, 'xvla', output)
            self.assertEqual(result['status'], 'success')
            self.assertTrue((output.parent / (parallel.TASK + '-admission') / '110000.json').exists())

    def test_peer_cooling_request_bypasses_local_sampling_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cooling = parallel.CoordinatedActionCooling(base, 'GPU-sim', base / 'episode.json')
            parallel.formal.write(cooling.gate, dict(cooling=True))
            cooling.next_check = time.monotonic() + 60
            with patch.object(cooling, 'cooling_gate', side_effect=[
                    (dict(temperature=79), True), (dict(temperature=74), False)]) as gate, \
                 patch.object(parallel.time, 'sleep'):
                cooling.before_action()
            self.assertEqual(gate.call_count, 2)
            self.assertEqual(len(cooling.events), 1)
            self.assertIn('finished_at', cooling.events[0])


if __name__ == '__main__':
    unittest.main()
