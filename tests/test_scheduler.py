import hashlib, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1]/'connector'))
import server, warmup

def row():
 return {'id':hashlib.sha256(b'personal').hexdigest()[:20], 'buckets':{'codex':{'primary':{'windowDurationMins':300,'usedPercent':5,'resetsAt':10000},'secondary':{'usedPercent':2,'resetsAt':999999}}}}

class Tests(unittest.TestCase):
 def test_overdue_timer_runs_promptly_after_clock_jump(self):
  self.assertEqual(server.scheduler_delay([{'warmup':{'nextCheckAt':100}}],100000),1)
  self.assertEqual(server.scheduler_delay([{'warmup':{'nextCheckAt':130}}],100),30)
  self.assertEqual(server.scheduler_delay([],100),60)
 def test_unknown_weekly_quota_never_sends(self):
  self.assertFalse(warmup.plan({'primary':row()['buckets']['codex']['primary']},{},10031)[0])
 def test_uncertain_attempt_does_not_resend_after_timestamp_changes(self):
  self.assertFalse(warmup.plan(row()['buckets']['codex'],{'attemptedReset':9900,'outcome':'uncertain'},10031)[0])
 def test_completed_warmup_and_post_read_failure_never_resend(self):
  with tempfile.TemporaryDirectory() as d, patch.object(warmup,'DATA',Path(d)), patch.object(warmup.time,'time',return_value=10031), patch.object(warmup,'send_hi',return_value='test') as send, patch.object(warmup,'read_account',side_effect=RuntimeError('offline')):
   r=row();state={};p=Path(d)/'state.json'
   warmup.process_account(None,r,state,p)
   self.assertEqual(state[r['id']]['outcome'],'completed')
   self.assertEqual(json.loads(p.read_text())[r['id']]['outcome'],'completed')
   warmup.process_account(None,r,state,p)
   self.assertEqual(send.call_count,1)
 def test_persisted_intent_survives_uncertain_message(self):
  with tempfile.TemporaryDirectory() as d, patch.object(warmup,'DATA',Path(d)), patch.object(warmup.time,'time',return_value=10031):
   r=row();p=Path(d)/'state.json';state={}
   def fail(*args):
    self.assertEqual(json.loads(p.read_text())[r['id']]['outcome'],'pending')
    raise RuntimeError('completion unknown')
   with patch.object(warmup,'send_hi',side_effect=fail) as send:
    warmup.process_account(None,r,state,p)
    warmup.process_account(None,r,state,p)
    self.assertEqual(send.call_count,1)
    self.assertEqual(state[r['id']]['outcome'],'uncertain')
 def test_desktop_login_is_never_used_for_legacy_account(self):
  with tempfile.TemporaryDirectory() as d, patch.object(server,'DATA',Path(d)), patch.object(server,'load',return_value=[{'id':'personal','home':None}]), patch.object(server,'save'), patch.object(server,'Rpc') as rpc:
   result=server.refresh()
   rpc.assert_not_called()
   self.assertTrue(result['accounts'][0]['needsLogin'])
 def test_one_account_failure_does_not_replace_identity_or_block_another(self):
  with tempfile.TemporaryDirectory() as d:
   data=Path(d);a=data/'accounts/a';b=data/'accounts/b'
   for home in [a,b]:home.mkdir(parents=True);(home/'auth.json').write_text('{}')
   rows=[{'id':'personal','home':str(a)},{'id':hashlib.sha256(b'work').hexdigest()[:20],'home':str(b)}]
   class RPC:
    def __init__(self,home):self.home=home
    def call(self,method,params=None):
     if method=='account/read':return {'account':{'type':'chatgpt'}}
     return {'accountId':'work','rateLimits':{}}
    def close(self):pass
   with patch.object(server,'DATA',data),patch.object(server,'load',return_value=rows),patch.object(server,'save'),patch.object(server,'Rpc',RPC):
    result=server.refresh()
   self.assertEqual(result['accounts'][0]['id'],'personal')
   self.assertTrue(result['accounts'][0]['needsLogin'])
   self.assertFalse(result['accounts'][1]['needsLogin'])
   self.assertIsNone(result['accounts'][1]['error'])
if __name__=='__main__':unittest.main()
