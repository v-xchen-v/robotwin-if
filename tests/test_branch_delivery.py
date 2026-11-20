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
import yaml

from if_benchmark.seed_contracts import IF_SEED_CONTRACTS, CURRENT_SUITE_TASKS
from if_benchmark.seed_modes import build_seed_modes, check_seed_modes, export_texts

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'seed-manifests/20-blocks'
EXPANDED = ROOT / 'seed-manifests/200-blocks'
POLICIES = ('xvla', 'lingbot_va', 'lingbot_vla', 'vlact', 'dm05', 'hy_vla', 'fastwam', 'motus', 'xwam')


class SeedModeDeliveryTest(unittest.TestCase):
    def test_expanded_suite_preserves_old_prefixes_and_balanced_sizes(self):
        check_seed_modes(EXPANDED)
        data = build_seed_modes(EXPANDED)
        self.assertEqual((data['blocks_per_task'], data['episodes_per_policy']), (200, 4600))
        for task in data['tasks']:
            old = json.loads((RELEASE / f"{task['task']}.json").read_text())['seeds']
            self.assertEqual([r['seed'] for r in task['episodes'][:len(old)]], old)
        for blocks in (50, 100, 200):
            selected = [r for t in data['tasks'] for r in t['episodes'] if r['block'] < blocks]
            self.assertEqual(len(selected), 23 * blocks)
            for task in data['tasks']:
                self.assertEqual(Counter(r['mode'] for r in task['episodes'] if r['block'] < blocks),
                                 dict.fromkeys(task['mode_counts'], blocks))

    def test_suite_capacity_and_identity_must_match_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for task in CURRENT_SUITE_TASKS:
                shutil.copyfile(EXPANDED / f'{task}.json', directory / f'{task}.json')
            original = yaml.safe_load((EXPANDED / 'suite.yml').read_text())
            for field, value in (('blocks_per_task', 100), ('blocks_per_task', True),
                                 ('episodes_per_policy', 460)):
                bad = dict(original, **{field: value})
                (directory / 'suite.yml').write_text(yaml.safe_dump(bad))
                with self.assertRaises(ValueError):
                    build_seed_modes(directory)
            for field, value in (('manifest_sha256', '0' * 64), ('task_config', 'wrong'),
                                 ('blocks', 20), ('modes', {'press': 20, 'lift': 20})):
                bad = json.loads(json.dumps(original))
                bad['tasks'][0][field] = value
                (directory / 'suite.yml').write_text(yaml.safe_dump(bad))
                with self.assertRaisesRegex(ValueError, f'suite {field}'):
                    build_seed_modes(directory)

    def test_export_matches_frozen_results_and_twenty_balanced_blocks(self):
        check_seed_modes(RELEASE)
        data = build_seed_modes(RELEASE)
        self.assertEqual(data['episodes_per_policy'], 460)
        self.assertEqual([t['task'] for t in data['tasks']], list(CURRENT_SUITE_TASKS))
        for task in data['tasks']:
            with (ROOT / 'result/episodes.csv').open(newline='') as stream:
                frozen = [int(r['seed']) for r in csv.DictReader(stream) if r['policy'] == 'xvla' and r['task'] == task['task']]
            self.assertEqual([r['seed'] for r in task['episodes']], frozen)
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
            shutil.copyfile(RELEASE / "suite.yml", directory / "suite.yml")
            for task in CURRENT_SUITE_TASKS:
                shutil.copyfile(RELEASE / f'{task}.json', directory / f'{task}.json')
            for name, contents in export_texts(directory).items():
                (directory / name).write_text(contents)
            check_seed_modes(directory)
            path = directory / 'seed-modes.csv'
            path.write_text(path.read_text().replace(',press,', ',lift,', 1))
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
        shutil.copyfile(ROOT / 'tasks/task_config/demo_clean_arm_select.yml',
                        self.runtime / 'task_config/demo_clean_arm_select.yml')
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
                self.assertIn(str(ROOT / 'seed-manifests' / '20-blocks' / 'arm_select.json'), run.stdout)
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

    def test_expanded_suite_dry_run_selects_50_100_or_200_without_launching(self):
        for blocks in (50, 100, 200):
            run = self.run_launcher('--manifest-dir', str(EXPANDED), '--blocks', str(blocks), '--dry-run')
            self.assertEqual(run.returncode, 0, run.stderr)
            for task, contract in IF_SEED_CONTRACTS.items():
                self.assertIn(f'{task}: {blocks} blocks, {blocks * contract.block_size} episodes', run.stdout)
        for blocks in ('0', '-1', '201', '1.5'):
            self.assertNotEqual(self.run_launcher('--manifest-dir', str(EXPANDED),
                                                 '--blocks', blocks, '--dry-run').returncode, 0)
        self.assertEqual(self.launched(), [])
        self.assertFalse(self.output.exists())
        self.assertFalse(Path(self.env['FAKE_GPU_LOG']).exists())

    def test_expanded_full_run_passes_the_exact_200_block_plan_to_all_workers(self):
        run = self.run_launcher('--manifest-dir', str(EXPANDED), '--blocks', '200')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        calls = self.launched()
        self.assertEqual(len(calls), 6)
        self.assertTrue(all(r['options']['--blocks'] == '200' for r in calls))
        for task in CURRENT_SUITE_TASKS:
            path = self.output / 'vlact' / task / 'results.jsonl'
            actual = [json.loads(line)['seed'] for line in path.read_text().splitlines()]
            expected = json.loads((EXPANDED / f'{task}.json').read_text())['seeds']
            self.assertEqual(actual, expected)

    def test_zero_success_complete_tasks_continue_with_exact_seed_prefix(self):
        run = self.run_launcher('--blocks', '2')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(run.stdout.count('COMPLETE:'), 6)
        calls = self.launched()
        self.assertEqual([r['options']['--task'] for r in calls], list(CURRENT_SUITE_TASKS))
        self.assertTrue(all(r['gpu'] == '0' for r in calls))
        self.assertEqual(calls[3]['options']['--task-config'], 'demo_clean_arm_select')

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
        run = self.run_launcher('--task', 'press_lift_stapler')
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertIn('GPU safety check failed', run.stderr)
        self.assertEqual(self.launched(), [])

    def test_running_gpu_pressure_terminates_owned_simulator_process_group(self):
        pids = self.base / 'pids.json'
        self.env['FAKE_HANG'] = str(pids)
        run = self.run_launcher('--task', 'press_lift_stapler')
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        self.assertIn('GPU safety check failed', run.stderr)
        self.assertEqual(len(self.launched()), 1)
        for pid in json.loads(pids.read_text()):
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)


if __name__ == '__main__':
    unittest.main()
