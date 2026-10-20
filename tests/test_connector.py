import importlib.util, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('bridge',Path(__file__).parents[1]/'connector/server.py'); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_projection(self):
  data=m.normalize({'type':'chatgpt','email':'test@example.com','planType':'plus'},{'accountId':'id','rateLimitsByLimitId':{'codex':{'primary':{'usedPercent':3}}},'rateLimitResetCredits':{'availableCount':2,'credits':[{'id':'private-id','title':'Full reset','expiresAt':2000000000}]}},None)
  self.assertEqual(data['resetCredits'],2);self.assertEqual(data['resetCreditDetails'][0]['expiresAt'],2000000000);self.assertNotIn('id',data['resetCreditDetails'][0]);self.assertEqual(data['buckets']['codex']['primary']['usedPercent'],3);self.assertNotIn('id',data['id']);self.assertNotIn('token',str(data))
 def test_unavailable_account(self):
  with self.assertRaises(RuntimeError):m.normalize(None,{},None)
if __name__=='__main__':unittest.main()
