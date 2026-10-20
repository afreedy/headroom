import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'connector'))
from warmup import plan, read_account, send_hi

def limits(reset,used=5,weekly=2):return {'primary':{'windowDurationMins':300,'usedPercent':used,'resetsAt':reset},'secondary':{'usedPercent':weekly,'resetsAt':999999}}
class Tests(unittest.TestCase):
 def test_active_skips(self):self.assertFalse(plan(limits(20000),{},10000)[0])
 def test_expired_waits_for_grace(self):
  self.assertFalse(plan(limits(10000),{},10020)[0]);self.assertTrue(plan(limits(10000),{},10031)[0])
 def test_unstarted_future_timestamp_after_due(self):self.assertTrue(plan(limits(28031,0),{'nextReset':10000},10031)[0])
 def test_real_work_started_new_window(self):self.assertFalse(plan(limits(27000,1),{'nextReset':10000},10031)[0])
 def test_duplicate_and_timestamp_drift(self):self.assertFalse(plan(limits(10004),{'nextReset':10000,'attemptedReset':10000},10035)[0])
 def test_weekly_exhaustion(self):self.assertFalse(plan(limits(10000,99,100),{},10031)[0])
 def test_unknown_window(self):self.assertFalse(plan({}, {},10031)[0])
 def test_identity_mismatch(self):
  class R:
   def call(self,method,params=None):return {'account':{'type':'chatgpt','email':'sample@example.com'}} if method=='account/read' else {'accountId':'other'}
  with self.assertRaises(RuntimeError):read_account(R(),'expected')
 def test_hi_has_no_tools_and_requires_completed(self):
  class Done:
   def wait(self,timeout):return True
  class R:
   turn_done=Done();turn_result={'status':'completed'}
   def __init__(self):self.calls=[]
   def call(self,method,params=None):
    self.calls.append((method,params))
    if method=='model/list':return {'data':[{'model':'gpt-6-luna','supportedReasoningEfforts':[{'reasoningEffort':'low'}]}]}
    if method=='thread/start':return {'thread':{'id':'test'}}
    return {}
  r=R();self.assertEqual(send_hi(r,Path('/tmp')),'gpt-6-luna')
  self.assertTrue(r.calls[1][1]['ephemeral']);self.assertEqual(r.calls[1][1]['sandbox'],'read-only');self.assertEqual(r.calls[2][1]['input'],[{'type':'text','text':'hi'}])
if __name__=='__main__':unittest.main()
