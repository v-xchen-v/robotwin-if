"""All six runners must serialize the verdict made after their final action."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ('xvla', 'lingbot_va', 'lingbot_vla', 'vlact', 'dm05', 'hy_vla')


def fixtures(policy):
    spec=importlib.util.spec_from_file_location(f'{policy}_terminal_fixtures',
                                               ROOT/'tests'/policy/'test_client.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def client_for(policy, f):
    if policy == 'xvla':
        client=Mock()
        client.predict.return_value=(f.decode_actions(f.action_chunk()), dict(
            raw_actions=f.action_chunk(), proprio=f.encode_proprio(f.observation()), latency_seconds=.1))
        return client
    if policy == 'lingbot_va':
        return f.client_with_responses({}, {'action':f.chunk(True)}, {}, {'action':f.chunk()})[0]
    if policy == 'hy_vla':
        return f.client_with_responses({'ok':True}, *[f.step_response(i) for i in range(9)])[0]
    if policy == 'dm05':
        return f.client_with_responses({'status':'ok'}, *[{'actions':f.chunk().tolist()} for _ in range(2)])[0]
    return f.client_with_responses({}, *[{'action':f.chunk()} for _ in range(2)])[0]


class TerminalRunnerTests(unittest.TestCase):
    def test_all_six_runners_preserve_terminal_success_and_failure_artifacts(self):
        for policy in POLICIES:
            f=fixtures(policy)
            for success in (False, True):
                with self.subTest(policy=policy,success=success), tempfile.TemporaryDirectory() as tmp:
                    env=f.FakeEnv(success_at=10000)
                    final_calls=[]
                    def finalize():
                        self.assertEqual(env.take_action_cnt,env.step_lim)
                        final_calls.append(env.take_action_cnt)
                        return success
                    env.finalize_policy_success=finalize
                    def writer(path,**kwargs):
                        path.touch()
                        return Mock()
                    directory=Path(tmp)/'episode'
                    with patch('imageio.v2.get_writer',side_effect=writer):
                        result=f.run_episode(env,{},client_for(policy,f),
                            argparse.Namespace(task='click_bell',task_config='demo_clean'),
                            2000,'task-name',directory)
                    self.assertEqual(final_calls,[env.step_lim])
                    self.assertEqual(result['success'],success)
                    self.assertEqual(result['termination'],'action_limit')
                    self.assertEqual(result['action_calls'],env.step_lim)
                    summary=json.loads((directory/'click_bell_ep2000_summary.json').read_text())
                    self.assertEqual(summary['success'],success)
                    self.assertEqual(summary['steps'],env.step_lim)
                    self.assertTrue((directory/f'click_bell_ep2000_{int(success)}.mp4').exists())


if __name__ == '__main__':
    unittest.main()
