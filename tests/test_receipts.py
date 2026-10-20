import sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'connector'))
from receipts import capture, history, write_receipt
from warmup import send_hi
class Tests(unittest.TestCase):
 def test_capture_exact_response_completion_and_ignore_secrets(self):
  r={'threadId':'t'}
  capture(r,'account/login/completed',{'token':'secret'})
  capture(r,'item/completed',{'threadId':'other','item':{'type':'agentMessage','id':'wrong','text':'wrong'}})
  capture(r,'item/completed',{'threadId':'t','item':{'type':'agentMessage','id':'m','text':'hi\n','phase':'final_answer'}})
  capture(r,'turn/completed',{'threadId':'t','turn':{'id':'turn','status':'completed'}})
  self.assertEqual(r['response'],'hi\n');self.assertEqual(r['turnId'],'turn')
  self.assertNotIn('secret',str(r));self.assertNotIn('wrong',str(r))
 def test_legacy_history_never_fabricates_transcript(self):
  with tempfile.TemporaryDirectory() as d:
   r=history(d,'test',{'lastCompletedAt':100,'model':'known'})
   self.assertIsNone(r[0]['response']);self.assertIsNone(r[0]['request'])
   self.assertEqual(r[0]['evidence'],'legacy')
   self.assertEqual(len(history(d,'test',{'lastCompletedAt':100})),1)
 def test_recorded_turn_captures_prompt_ids_model_and_answer(self):
  class Done:
   def wait(self,timeout):return True
  class RPC:
   turn_done=Done();turn_result={'id':'turn','status':'completed'}
   def call(self,method,params=None):
    if method=='model/list':return {'data':[{'model':'gpt-6-luna','supportedReasoningEfforts':[{'reasoningEffort':'low'}]}]}
    if method=='thread/start':return {'thread':{'id':'thread'}}
    if method=='turn/start':
     self.capture_event('item/completed',{'threadId':'thread','item':{'type':'agentMessage','id':'a','text':'hi'}})
     self.capture_event('turn/completed',{'threadId':'thread','turn':self.turn_result})
     return {'turn':self.turn_result}
  with tempfile.TemporaryDirectory() as d, patch('warmup.DATA',Path(d)):
   r={'id':'run','accountId':'a'}
   send_hi(RPC(),Path(d),r,lambda:write_receipt(d,r))
   self.assertEqual((r['model'],r['request'],r['response'],r['threadId'],r['turnId'],r['completionStatus']),('gpt-6-luna','hi','hi','thread','turn','completed'))
if __name__=='__main__':unittest.main()
