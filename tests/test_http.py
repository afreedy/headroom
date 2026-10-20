import importlib.util, json, threading, unittest, urllib.request, urllib.error
from pathlib import Path
spec=importlib.util.spec_from_file_location('bridge',Path(__file__).parents[1]/'connector/server.py'); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=m.ThreadingHTTPServer(('127.0.0.1',0),m.Handler);cls.server.origin='https://dashboard.example';cls.server.origins={cls.server.origin};cls.server.token='test-key'
  m.refresh=lambda:{'accounts':[],'errors':[]}
  threading.Thread(target=cls.server.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
 def request(self,origin='https://dashboard.example',token='test-key',host='127.0.0.1:4318',method='GET'):
  req=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+'/usage',method=method,headers={'Origin':origin,'Authorization':'Bearer '+token,'Host':host})
  try:return urllib.request.urlopen(req)
  except urllib.error.HTTPError as e:return e
 def test_allowed(self):
  r=self.request();self.assertEqual(r.status,200);self.assertEqual(r.headers['Access-Control-Allow-Origin'],self.server.origin);self.assertEqual(json.load(r)['accounts'],[])
 def test_denied(self):
  self.assertEqual(self.request(origin='https://evil.example').status,403);self.assertEqual(self.request(token='wrong').status,401);self.assertEqual(self.request(host='evil.example:4318').status,403)
 def test_preflight(self):
  r=self.request(method='OPTIONS');self.assertEqual(r.status,204);self.assertEqual(r.headers['Access-Control-Allow-Private-Network'],'true')
if __name__=='__main__':unittest.main()
