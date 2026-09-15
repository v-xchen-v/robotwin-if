"""CPU checks for the portable release and launcher; no real model or GPU access."""
from collections import Counter
import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from if_benchmark.seed_contracts import IF_SEED_CONTRACTS
from if_benchmark.seed_modes import build_seed_modes, check_seed_modes, export_texts

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'seed-manifests/if-ext-v2-six-tasks-spatial3-20-per-mode'
POLICIES = ('xvla', 'lingbot_va', 'lingbot_vla', 'vlact', 'dm05', 'hy_vla')


class SeedModeDeliveryTest(unittest.TestCase):
    def test_export_matches_frozen_results_and_twenty_balanced_blocks(self):
        check_seed_modes(RELEASE)
        data = build_seed_modes(RELEASE)
        self.assertEqual(data['episodes_per_policy'], 460)
        self.assertEqual([t['task'] for t in data['tasks']], list(IF_SEED_CONTRACTS))
        for task in data['tasks']:
            frozen = json.loads((ROOT / 'result/if-ext-v2-six-tasks-spatial3-20blocks/manifests' / task['manifest']).read_text())
            self.assertEqual([r['seed'] for r in task['episodes']], frozen['seeds'])
            self.assertEqual(task['mode_counts'], dict.fromkeys(IF_SEED_CONTRACTS[task['task']].modes, 20))
            blocks = {i: [r for r in task['episodes'] if r['block'] == i] for i in range(20)}
            for rows in blocks.values():
                self.assertEqual(Counter(r['mode'] for r in rows), dict.fromkeys(task['mode_counts'], 1))
            # These qualified manifests start at large, sometimes discontinuous seeds.
            self.assertEqual(task['episodes'][0]['block'], 0)
            self.assertNotEqual(task['episodes'][0]['seed'] // len(task['mode_counts']), 0)
        csv_rows = list(csv.DictReader(io.StringIO(export_texts(RELEASE)['seed-modes.csv'])))
        self.assertEqual(len(csv_rows), 460)
        self.assertEqual([(r['task'], int(r['seed']), r['mode']) for r in csv_rows],
                         [(t['task'], r['seed'], r['mode']) for t in data['tasks'] for r in t['episodes']])

    def test_stale_mode_export_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for task in IF_SEED_CONTRACTS:
                shutil.copyfile(RELEASE / f'{task}.json', directory / f'{task}.json')
            for name, contents in export_texts(directory).items():
                (directory / name).write_text(contents)
            check_seed_modes(directory)
            path = directory / 'seed-modes.csv'
            path.write_text(path.read_text().replace(',pick,', ',shake,', 1))
            with self.assertRaisesRegex(ValueError, 'differs from flat manifests'):
                check_seed_modes(directory)


class EvalLauncherTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='if delivery ')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.runtime = self.base / 'runtime'
        (self.runtime / 'envs').mkdir(parents=True)
        (self.runtime / 'task_config').mkdir()
        for task in IF_SEED_CONTRACTS:
            (self.runtime / 'envs' / f'{task}.py').touch()
        (self.runtime / 'task_config/demo_clean.yml').touch()
        shutil.copyfile(ROOT / 'tasks/task_config/demo_clean_arm_select_v2.yml',
                        self.runtime / 'task_config/demo_clean_arm_select_v2.yml')
        self.output = self.base / 'output with spaces'
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        TMPDIR=str(self.base), FAKE_LOG=str(self.base / 'launched.jsonl'),
                        FAKE_GPU_LOG=str(self.base / 'gpu-queries'), FAKE_RC='1', FAKE_GPU_TEMP='40')
        # Intercept only the simulator bootstrap. Planning and result validation use real Python.
        self.python = self.executable('sim-python', f'#!{sys.executable}\n' + '''
import json, os, sys
from pathlib import Path
if len(sys.argv) > 2 and sys.argv[1] == '-c' and 'from tools.sim_device' in sys.argv[2]:
    from if_benchmark.seed_contracts import IF_SEED_CONTRACTS
    args = sys.argv[4:]
    options = dict(zip(args[::2], args[1::2]))
    with open(os.environ['FAKE_LOG'], 'a') as log:
        log.write(json.dumps(dict(policy=sys.argv[3], options=options, gpu=os.environ.get('CUDA_VISIBLE_DEVICES'))) + '\\n')
    if os.environ.get('FAKE_HANG'):
        import signal, subprocess, time
        child = subprocess.Popen(['/bin/sleep', '60'])
        def terminate(signum, frame):
            child.wait(timeout=5)
            sys.exit(143)
        signal.signal(signal.SIGTERM, terminate)
        Path(os.environ['FAKE_HANG']).write_text(json.dumps([os.getpid(), child.pid]))
        while True:
            time.sleep(0.1)
    rc = int(os.environ['FAKE_RC'])
    if rc == 2:
        sys.exit(rc)
    task = options['--task']
    count = int(options['--blocks']) * IF_SEED_CONTRACTS[task].block_size
    seeds = json.loads(Path(options['--seed-manifest']).read_text())['seeds'][:count]
    output = Path(options['--output-dir'])
    output.mkdir(parents=True)
    records = [dict(seed=s, status='failure', oracle_success=True) for s in seeds]
    if os.environ.get('FAKE_WRONG_SEED'):
        records[-1]['seed'] += 10000
    (output / 'results.jsonl').write_text(''.join(json.dumps(r) + '\\n' for r in records))
    (output / 'summary.json').write_text(json.dumps(dict(complete=True, error=None,
        expected_episodes=count, recorded_episodes=count, successes=0)))
    sys.exit(rc)
os.execv(sys.executable, [sys.executable] + sys.argv[1:])
''')
        self.executable('nvidia-smi', f'#!{sys.executable}\n' + '''
import os
from pathlib import Path
with open(os.environ['FAKE_GPU_LOG'], 'a') as log:
    log.write('query\\n')
temperature = os.environ['FAKE_GPU_TEMP']
if os.environ.get('FAKE_HANG') and Path(os.environ['FAKE_HANG']).exists():
    temperature = '87'
print('0, 0, 40000, ' + temperature + ', 0')
print('1, 10000, 40000, 40, 20')
''')
        # Keep polling semantics without waiting 15 seconds per fake task.
        self.executable('sleep', '#!/bin/sh\nexec /bin/sleep 0.05\n')

    def executable(self, name, contents):
        path = self.bin / name
        path.write_text(contents)
        path.chmod(0o755)
        return path

    def run_launcher(self, *args):
        return subprocess.run(['bash', str(ROOT / 'scripts/eval.sh'), '--policy', 'vlact',
                               '--output-dir', str(self.output), '--python', str(self.python),
                               '--robotwin-dir', str(self.runtime), *args],
                              env=self.env, cwd=self.base, text=True, capture_output=True, timeout=25)

    def launched(self):
        path = Path(self.env['FAKE_LOG'])
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_dry_run_all_policies_endpoints_tasks_and_no_side_effects(self):
        for index, policy in enumerate(POLICIES):
            with self.subTest(policy=policy):
                run = self.run_launcher('--policy', policy, '--dry-run')
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.count('20 blocks,'), 6)
                protocol = 'http' if policy in ('xvla', 'dm05') else 'ws'
                self.assertIn(f'{protocol}://127.0.0.1:{8010 + index}', run.stdout)
                self.assertNotIn('grasp_cube_approach', run.stdout)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.launched(), [])
        self.assertFalse(Path(self.env['FAKE_GPU_LOG']).exists())

    def test_invalid_selection_and_existing_output_rejected_before_launch(self):
        for args in (('--task', 'grasp_cube_approach'), ('--blocks', '21'),
                     ('--sim-gpu', '01', '--model-gpu', '1')):
            with self.subTest(args=args):
                self.assertNotEqual(self.run_launcher(*args).returncode, 0)
        existing = self.output / 'vlact/place_relative'
        existing.mkdir(parents=True)
        sentinel = existing / 'results.jsonl'
        sentinel.write_text('old evidence')
        run = self.run_launcher()
        self.assertIn('task output exists', run.stderr)
        self.assertEqual(sentinel.read_text(), 'old evidence')
        self.assertEqual(self.launched(), [])

    def test_zero_success_complete_tasks_continue_with_exact_seed_prefix(self):
        run = self.run_launcher('--blocks', '2')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(run.stdout.count('COMPLETE:'), 6)
        calls = self.launched()
        self.assertEqual([r['options']['--task'] for r in calls], list(IF_SEED_CONTRACTS))
        self.assertTrue(all(r['gpu'] == '0' for r in calls))
        self.assertEqual(calls[3]['options']['--task-config'], 'demo_clean_arm_select_v2')

    def test_infrastructure_failure_and_substituted_seed_stop_following_tasks(self):
        self.env['FAKE_RC'] = '2'
        run = self.run_launcher()
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertIn('evaluator exited 2', run.stderr)
        self.assertEqual(len(self.launched()), 1)
        Path(self.env['FAKE_LOG']).unlink()
        self.env.update(FAKE_RC='1', FAKE_WRONG_SEED='1')
        run = self.run_launcher()
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('Seeds missing, reordered or substituted', run.stderr)
        self.assertEqual(len(self.launched()), 1)

    def test_hot_gpu_rejected_before_simulator_launch(self):
        self.env['FAKE_GPU_TEMP'] = '87'
        run = self.run_launcher('--task', 'bottle_verb')
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertIn('GPU safety check failed', run.stderr)
        self.assertEqual(self.launched(), [])

    def test_running_gpu_pressure_terminates_owned_simulator_process_group(self):
        pids = self.base / 'pids.json'
        self.env['FAKE_HANG'] = str(pids)
        run = self.run_launcher('--task', 'bottle_verb')
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        self.assertIn('GPU safety check failed', run.stderr)
        self.assertEqual(len(self.launched()), 1)
        for pid in json.loads(pids.read_text()):
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)


if __name__ == '__main__':
    unittest.main()
