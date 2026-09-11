"""CPU safety checks for remote service isolation and immutable resume."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import run_remote_policy_queues as queues


class QueueTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.cfg=dict(host='sim-host',run_dir=str(self.base),policies=['lingbot_va','lingbot_vla'],
                      tasks=['bottle_verb'],port_offset=10000,
                      lanes=[dict(id=f'q{i}',sim_gpu=dict(uuid=f'sim-{i}',index=i,pci=f'0000:{31+i}:00.0'),
                                  model_gpu=dict(uuid=f'model-{i}',index=i,pci=f'0000:{41+i}:00.0')) for i in (0,1)],
                      remote=dict(host='model-host',run_dir=str(self.base),address='user@host',socket='/tmp/control'))

    def test_duplicate_gpu_and_policy_ownership_rejected(self):
        p=self.base/'cfg.json'
        def load():
            p.write_text(json.dumps(self.cfg));return queues.config(p)
        load()
        self.cfg['lanes'][1]['sim_gpu']['uuid']='sim-0'
        with self.assertRaises(AssertionError):load()
        self.cfg['lanes'][1]['sim_gpu']['uuid']='sim-1'
        self.cfg['policies'].append('lingbot_va')
        with self.assertRaises(AssertionError):load()

    def test_gpu_thresholds_are_per_device(self):
        rows=[['0','sim-0','00000000:31:00.0','5000','49140','70','20'],
              ['1','unrelated','00000000:32:00.0','49000','49140','90','100']]
        queues.check_gpu(rows,self.cfg['lanes'][0]['sim_gpu'],simulator=True)
        with self.assertRaises(AssertionError):
            queues.check_gpu(rows,self.cfg['lanes'][0]['sim_gpu'],simulator=True,idle=True)
        rows[0][3]='25000'
        with self.assertRaises(AssertionError):
            queues.check_gpu(rows,self.cfg['lanes'][0]['sim_gpu'],simulator=True)

    def test_stop_cannot_kill_a_different_session(self):
        state=dict(pid=123,start_ticks='456',session='some-other-session')
        p=self.base/'remote-services/q0.json';p.parent.mkdir();p.write_text(json.dumps(state))
        with patch.object(queues.socket,'gethostname',return_value='model-host'), \
             patch.object(queues,'alive',return_value=True),patch.object(queues.os,'killpg') as kill:
            with self.assertRaises(AssertionError):
                queues.service(self.cfg,dict(action='stop',lane=0,session='this-session'))
            kill.assert_not_called()

    def test_tunnel_binds_only_localhost(self):
        with patch.object(queues.subprocess,'run') as run:
            self.assertEqual(queues.tunnel(self.cfg,'lingbot_va','forward'),18011)
        argv=run.call_args.args[0]
        self.assertEqual(argv[argv.index('-L')+1],'127.0.0.1:18011:127.0.0.1:8011')
        self.assertIn('ExitOnForwardFailure=yes',argv)

    def test_pending_work_keeps_failures_and_excludes_other_host_task(self):
        plan=dict(tasks=[dict(task='bottle_verb',seeds=[2,3]),dict(task='grasp_cube_approach',seeds=[4,5])])
        queues.suite.write(self.base/'plan.json',plan)
        with patch.object(queues.suite,'completed_record',return_value={'status':'failure'}):
            self.assertEqual(queues.pending_specs(self.base,self.cfg,'lingbot_va'),[])
        with patch.object(queues.suite,'completed_record',side_effect=lambda b,p,s,seed: None if seed==3 else {'status':'failure'}):
            self.assertEqual(queues.pending_specs(self.base,self.cfg,'lingbot_va'),[plan['tasks'][0]])

    def test_two_queues_own_distinct_policies_and_finish_with_strict_validation(self):
        self.cfg.update(python='python',scene_probe=str(self.base/'probe'),code_sha256={})
        self.cfg['remote'].update(repo_root='/repo',python='python',config='/cfg')
        queues.suite.write(self.base/'plan.json',dict(tasks=[dict(task='bottle_verb',seeds=[2,3])]))
        queues.suite.write(self.base/'probe/validation.json',dict(complete=True,
            sim_gpu=self.cfg['lanes'][1]['sim_gpu'],source_sha256='hash',code_sha256={}))
        done=set();servers={};events=[]
        def rpc(cfg,r):
            i=r['lane']
            if r['action']=='start':
                self.assertNotIn(i,servers)
                self.assertNotIn(r['policy'],servers.values())
                servers[i]=r['policy'];events.append(('server',i))
            elif r['action']=='stop':
                servers.pop(i);events.append(('stop',i));return {}
            return dict(running=True,ready=True,state=dict(pid=100+i),metadata={})
        def popen(cmd,**kw):
            out=Path(cmd[cmd.index('--output')+1]);out.mkdir(parents=True)
            queues.suite.write(out/'summary.json',dict(complete=True))
            i=int(cmd[cmd.index('--lane')+1]);events.append(('sim',i))
            return SimpleNamespace(pid=200+i,returncode=0,poll=lambda:0)
        def ingest(base,policy,spec,out):
            if out.exists():done.add(policy)
        def report(base,state,current,error=None):
            return dict(status=state,updated_at='now',completed_episodes=2*len(done))
        with patch.object(queues.socket,'gethostname',return_value='sim-host'), \
             patch.object(queues,'check_sources'),patch.object(queues,'gpu_rows',return_value=[]), \
             patch.object(queues,'check_gpu',return_value=[]),patch.object(queues,'remote',side_effect=rpc), \
             patch.object(queues,'tunnel'),patch.object(queues.time,'sleep'), \
             patch.object(queues.subprocess,'Popen',side_effect=popen), \
             patch.object(queues.suite,'digest',return_value='hash'), \
             patch.object(queues.suite,'completed_record',side_effect=lambda b,p,s,n: {'status':'failure'} if p in done else None), \
             patch.object(queues.suite,'ingest_batch',side_effect=ingest),patch.object(queues.suite,'check_oracle_budget'), \
             patch.object(queues.suite,'stop'),patch.object(queues.suite,'report',side_effect=report), \
             patch.object(queues.suite,'verify') as verify, \
             patch('shutil.disk_usage',return_value=SimpleNamespace(free=500*1024**3)):
            queues.run(self.cfg,self.base/'cfg.json')
        self.assertEqual(events[:4],[('server',0),('server',1),('sim',0),('sim',1)])
        self.assertEqual(done,set(self.cfg['policies']))
        self.assertFalse(servers)
        verify.assert_called_once_with(self.base,require_complete=True)


if __name__=='__main__':
    unittest.main()
