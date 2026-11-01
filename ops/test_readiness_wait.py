import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from readiness_wait import node_state, deployment_state, application_state, wait_until, kubectl, poll


class ReadinessTests(unittest.TestCase):
    def deployment(self):
        return {'metadata': {'generation': 2}, 'spec': {'replicas': 1},
                'status': {'observedGeneration': 2, 'replicas': 1, 'updatedReplicas': 1,
                           'readyReplicas': 1, 'availableReplicas': 1}}

    def test_existing_node_is_not_enough(self):
        self.assertFalse(node_state({'status': {'conditions': [{'type': 'Ready', 'status': 'False'}]}})['ready'])
        self.assertFalse(node_state({})['ready'])
        self.assertTrue(node_state({'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]}})['ready'])

    def test_deployment_zero_replicas_or_old_generation_cannot_pass(self):
        obj=self.deployment(); self.assertTrue(deployment_state(obj)['ready'])
        obj['status']['observedGeneration']=1; self.assertFalse(deployment_state(obj)['ready'])
        obj=self.deployment(); obj['spec']['replicas']=0
        obj['status']={key:0 for key in obj['status']}
        self.assertFalse(deployment_state(obj)['ready'])

    def test_deployment_requires_updated_available_and_no_old_replicas(self):
        for key,value in [('updatedReplicas',0),('availableReplicas',0),('replicas',2),('readyReplicas',0)]:
            obj=self.deployment(); obj['status'][key]=value
            self.assertFalse(deployment_state(obj)['ready'],key)

    def test_missing_or_partial_application_status_is_pending(self):
        for obj in [{}, {'status': None}, {'status': {}}, {'status': {'sync': {'status':'Synced'}}}]:
            self.assertFalse(application_state(obj)['ready'])
        obj={'status': {'sync': {'status':'Synced'}, 'health': {'status':'Healthy'}}}
        self.assertTrue(application_state(obj)['ready'])
        obj['status']['operationState']={'phase':'Running'}
        self.assertFalse(application_state(obj)['ready'])

    def test_pending_then_ready_within_budget(self):
        now=[0.0]
        def sleep(duration):now[0]+=duration
        results=iter([{'ready':False},{'ready':True}])
        result=wait_until(lambda deadline:next(results),2,0.5,clock=lambda:now[0],sleep=sleep)
        self.assertTrue(result['ok']);self.assertEqual(result['attempts'],2)

    def test_deadline_and_late_success_are_not_accepted(self):
        now=[0.0]
        def sleep(duration):now[0]+=duration
        result=wait_until(lambda deadline:{'ready':False},2,10,clock=lambda:now[0],sleep=sleep)
        self.assertFalse(result['ok']);self.assertEqual(result['elapsed_seconds'],2)
        now[0]=0
        def slow(deadline):now[0]=3;return {'ready':True}
        self.assertFalse(wait_until(slow,2,1,clock=lambda:now[0],sleep=sleep)['ok'])

    def test_terminal_error_does_not_sleep(self):
        with patch('time.sleep') as sleep:
            result=wait_until(lambda deadline:{'ready':False,'terminal':True},2,1,sleep=sleep)
            self.assertFalse(result['ok']);sleep.assert_not_called()

    def test_node_ready_also_requires_api_readyz(self):
        node=json.dumps({'status': {'conditions': [{'type':'Ready','status':'True'}]}})
        with patch('readiness_wait.kubectl',side_effect=[(node,''),('not ready','')]):
            self.assertFalse(poll({'kind':'node','name':'cp'},100)['ready'])
        with patch('readiness_wait.kubectl',side_effect=[(node,''),('ok','')]):
            self.assertTrue(poll({'kind':'node','name':'cp'},100)['ready'])

    def test_kubectl_request_is_bounded_and_raw_error_is_hidden(self):
        result=type('Result',(),{'returncode':1,'stderr':'Forbidden SYNTHETIC-SECRET','stdout':''})()
        with patch('readiness_wait.time.monotonic',return_value=10), \
             patch('readiness_wait.subprocess.run',return_value=result) as run:
            text,error=kubectl({'kubeconfig':'/fake','request_timeout':10},['get','node','cp'],12)
            self.assertIsNone(text);self.assertNotIn('SYNTHETIC',error)
            self.assertEqual(run.call_args.kwargs['timeout'],2)
            self.assertIn('--request-timeout=2.000s',run.call_args.args[0])

    @unittest.skipUnless(os.name=='posix','verrous POSIX testés sous Ubuntu')
    def test_real_lock_held_by_parent_is_detected_in_child_without_deleting_file(self):
        import fcntl
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'lock';path.write_text('unchanged')
            fd=os.open(path,os.O_RDWR)
            script='import json,sys;from readiness_wait import apt_state;print(json.dumps(apt_state([sys.argv[1]])))'
            try:
                fcntl.lockf(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                child=subprocess.run([sys.executable,'-c',script,str(path)],cwd=Path(__file__).parent,
                                     capture_output=True,text=True,check=True,timeout=5)
                self.assertFalse(json.loads(child.stdout)['ready'])
            finally:os.close(fd)
            child=subprocess.run([sys.executable,'-c',script,str(path)],cwd=Path(__file__).parent,
                                 capture_output=True,text=True,check=True,timeout=5)
            self.assertTrue(json.loads(child.stdout)['ready'])
            self.assertEqual(path.read_text(),'unchanged')


if __name__=='__main__':unittest.main()
