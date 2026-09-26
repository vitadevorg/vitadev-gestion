import os,sys,tempfile,threading,json,unittest,urllib.request,urllib.error,http.cookiejar
from pathlib import Path
storage=tempfile.TemporaryDirectory();
for key,sub in [('NEXO_TEAM_DATA','team'),('NEXO_CRM_DATA','crm'),('NEXO_LEAVE_DATA','leave')]:os.environ[key]=storage.name+'/'+sub
os.environ.pop('NEXO_TEST_MODE',None);sys.path.insert(0,str(Path('src/backend').resolve()))
import auth_server as s
s.init();admin=s.auth.save_user(dict(email='admin@test.invalid',password='Nexo-test-password-2026',role='ADMIN',permissionProfile='ADMINISTRATOR',employeeId=1))
server=s.team.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}'
class Client:
 def __init__(self):self.jar=http.cookiejar.CookieJar();self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar));self.csrf=''
 def call(self,path,data=None,method=None,headers=None):
  h={'Content-Type':'application/json','X-Nexo-Client':'team','X-CSRF-Token':self.csrf};h.update(headers or {});req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=h,method=method)
  try:
   with self.opener.open(req) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:return e.code,json.load(e)
 def login(self,email='admin@test.invalid',password='Nexo-test-password-2026'):
  code,data=self.call('/api/auth/login',dict(email=email,password=password));self.csrf=data.get('user',{}).get('csrfToken','');return code,data
class Tests(unittest.TestCase):
 def setUp(self):self.admin=Client();self.assertEqual(self.admin.login()[0],200)
 def test_01_no_session(self):
  for path in ['/api/team','/api/crm','/api/desk','/api/absences/availability','/api/reports?start=2026-01-01&end=2026-09-12','/api/users']:self.assertEqual(Client().call(path)[0],401)
 def test_02_invalid_generic(self):
  a=Client().login(password='invalid')[1];b=Client().login(email='absent@test.invalid')[1];self.assertEqual(a,b)
 def test_03_session_restore_logout(self):
  self.assertEqual(self.admin.call('/api/auth/me')[0],200);self.assertEqual(self.admin.call('/api/auth/logout',{})[0],200);self.assertEqual(self.admin.call('/api/team')[0],401)
 def test_04_create_linked_unique(self):
  d=dict(email='marcos@test.invalid',password='Nexo-test-password-2026',employeeId=2,role='EMPLOYEE',permissionProfile='SUPPORT',status='ACTIVE');code,result=self.admin.call('/api/users',d);self.assertEqual(code,201);self.assertEqual(result['user']['employeeId'],2);self.assertNotIn('passwordHash',result['user']);self.assertEqual(self.admin.call('/api/users',{**d,'email':'other@test.invalid'})[0],422);self.assertEqual(len(self.admin.call('/api/team')[1]['employees']),6)
 def test_05_scope_and_spoof(self):
  user=Client();self.assertEqual(user.login('marcos@test.invalid')[0],200)
  self.assertEqual(user.call('/api/users')[0],403);self.assertEqual(user.call('/api/reports?start=2026-01-01&end=2026-09-12',headers={'X-Nexo-View':'admin'})[0],403);self.assertEqual(user.call('/api/users/1',{},method='DELETE')[0],403)
  self.assertEqual([e['id'] for e in user.call('/api/team')[1]['employees']],[2]);self.assertTrue(all(r['agentId']==2 for r in user.call('/api/desk')[1]['requests']));self.assertEqual(user.call('/api/crm')[1]['contracts'],[])
 def test_06_disable_reactivate(self):
  user=next(u for u in self.admin.call('/api/users')[1]['users'] if u['employeeId']==2);old=Client();self.assertEqual(old.login(user['email'])[0],200)
  self.assertEqual(self.admin.call('/api/users/'+str(user['id']),{**user,'status':'DISABLED'})[0],200);self.assertEqual(old.call('/api/auth/me')[0],401);self.assertEqual(Client().login(user['email'])[0],403)
  self.assertEqual(self.admin.call('/api/users/'+str(user['id']),{**user,'status':'ACTIVE'})[0],200);self.assertEqual(Client().login(user['email'])[0],200)
 def test_07_csrf_last_admin(self):
  self.assertEqual(self.admin.call('/api/users',{},headers={'X-CSRF-Token':''})[0],403);self.assertEqual(self.admin.call('/api/users/1',{**admin,'status':'DISABLED'})[0],422)
 def test_08_hash_and_audit(self):
  with s.team.connect() as c:
   row=c.execute('SELECT * FROM users WHERE id=1').fetchone();self.assertTrue(row['passwordHash'].startswith('scrypt$'));self.assertNotIn('Nexo-test-password',row['passwordHash']);self.assertTrue(c.execute('SELECT 1 FROM user_audit WHERE actorUserId=1').fetchone())
 def test_09_expired(self):
  with s.team.connect() as c:c.execute('UPDATE sessions SET expiresAt=0 WHERE userId=1')
  self.assertEqual(self.admin.call('/api/auth/me')[0],401)
 def test_10_employee_data_live(self):
  employee=next(e for e in self.admin.call('/api/team')[1]['employees'] if e['id']==1)
  employee.update(firstName='Ana actualizada',photo='assets/avatars/default-avatar.png')
  self.assertEqual(self.admin.call('/api/team/1',employee,method='PUT')[0],200)
  current=self.admin.call('/api/auth/me')[1]['user'];self.assertEqual(current['employee']['firstName'],'Ana actualizada');self.assertEqual(current['employee']['photo'],'assets/avatars/default-avatar.png')
  with s.team.connect() as c:self.assertTrue(c.execute('SELECT 1 FROM employee_audit WHERE actorUserId=1 AND employee_id=1').fetchone())
 def test_11_last_admin_employee_protected(self):
  self.assertEqual(self.admin.call('/api/team/1/deactivate',dict(version=1,reason='Prueba'))[0],422)
 def test_12_cookie_and_origin(self):
  cookie=next(iter(self.admin.jar));self.assertTrue(cookie.has_nonstandard_attr('HttpOnly'));self.assertEqual(cookie.get_nonstandard_attr('SameSite'),'Strict')
  self.assertEqual(self.admin.call('/api/auth/logout',{},headers={'Origin':'https://untrusted.invalid'})[0],403)
 def test_13_concurrent_identity_and_account_switch(self):
  from concurrent.futures import ThreadPoolExecutor
  clients=[Client() for _ in range(4)]
  for client in clients:self.assertEqual(client.login()[0],200)
  def browse(client):
   return [client.call(path)[0] for _ in range(5) for path in ['/api/auth/me','/api/users','/api/team']]
  with ThreadPoolExecutor(max_workers=5) as pool:
   reads=[pool.submit(browse,client) for client in clients]
   self.assertEqual(self.admin.login('marcos@test.invalid')[0],200)
   self.assertEqual(self.admin.call('/api/users')[0],403)
   self.assertEqual(self.admin.login()[0],200)
   for read in reads:self.assertTrue(all(code==200 for code in read.result(timeout=30)))
if __name__=='__main__':
 try:result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 finally:server.shutdown();server.server_close()
 sys.exit(not result.wasSuccessful())
