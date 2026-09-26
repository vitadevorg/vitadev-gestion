import os
os.environ['NEXO_TEST_MODE']='1'
import sys,tempfile,os,threading,json,urllib.request,urllib.error,unittest,base64,gc
from pathlib import Path
root=Path.cwd();tmp=tempfile.TemporaryDirectory();os.environ['NEXO_TEAM_DATA']=tmp.name+'/team';os.environ['NEXO_CRM_DATA']=tmp.name+'/crm';sys.path.insert(0,str(root/'src/backend'))
import helpdesk_server as desk
desk.team.init();desk.init();server=desk.team.ThreadingHTTPServer(('127.0.0.1',0),desk.Handler);threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}'
def call(path,data=None):
 req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','X-Nexo-Client':'team'})
 try:
  with urllib.request.urlopen(req) as r:return r.status,json.load(r)
 except urllib.error.HTTPError as e:return e.code,json.load(e)
def request(id):return next(r for r in call('/api/desk')[1]['requests'] if r['id']==id)
class Tests(unittest.TestCase):
 def test_01_seed_and_team(self):
  all=call('/api/desk')[1];self.assertEqual(len(all['requests']),3);self.assertEqual(request(1042)['agentId'],2);self.assertTrue(all['requests'][0]['createdAt']);self.assertEqual(len(call('/api/team')[1]['employees']),6)
 def test_02_create_relations_queue(self):
  crm=call('/api/crm')[1];s=next(s for s in crm['subscriptions'] if s['clientId']==1);code,r=call('/api/crm/contacts',dict(clientId=1,firstName='Persona',lastName='Prueba',email='persona@example.com',status='Activo',principal=True));self.assertEqual(code,201);contact=r['record']['id'];d=dict(clientId=1,subscriptionId=s['id'],contactId=contact,title='Prueba',description='Contexto de prueba',type='Incidente',priority='Alta',agentId=1,status='Cerrada');code,r=call('/api/desk/requests',d);self.assertEqual(code,201);self.assertEqual(r['request']['status'],'Nueva');self.assertEqual(r['request']['queue'],'Mesa de Ayuda');self.assertIsNone(r['request']['agentId']);d['clientId']=2;self.assertEqual(call('/api/desk/requests',d)[0],422)
 def test_03_flow_conflict(self):
  r=request(1041);self.assertEqual(call('/api/desk/requests/1041/update',dict(version=r['version'],status='Cerrada'))[0],422);self.assertEqual(call('/api/desk/requests/1041/update',dict(version=r['version'],status='En atención'))[0],200);self.assertEqual(call('/api/desk/requests/1041/update',dict(version=r['version'],priority='Urgente'))[0],409)
  for s in ['Esperando cliente','En atención','Resuelta','Cerrada']:
   r=request(1041);self.assertEqual(call('/api/desk/requests/1041/update',dict(version=r['version'],status=s))[0],200)
 def test_04_task_does_not_reassign(self):
  r=request(1042);code,_=call('/api/desk/requests/1042/tasks',dict(version=r['version'],title='Corregir API',owner=3,priority='Alta',due='2026-09-20'));self.assertEqual(code,200);self.assertEqual(request(1042)['agentId'],2);self.assertTrue(any(t['owner']==3 and t['ticket']==1042 for t in call('/api/desk')[1]['tasks']))
 def test_05_comments_files(self):
  self.assertEqual(call('/api/desk/files',dict(name='peligro.exe',base64=base64.b64encode(b'hello').decode()))[0],422);code,r=call('/api/desk/files',dict(name='error.log',base64=base64.b64encode(b'log de prueba').decode()));self.assertEqual(code,201);rfile=r['url'];r=request(1042);self.assertEqual(call('/api/desk/requests/1042/comments',dict(version=r['version'],text='Analizando el incidente',attachments=[rfile]))[0],200);all=call('/api/desk')[1];self.assertTrue(any(c['text']=='Analizando el incidente' for c in all['comments']));self.assertTrue(any(e['action']=='Archivo agregado' for e in all['events']))
 def test_06_assignment_and_persistence(self):
  r=request(1042);self.assertEqual(call('/api/desk/requests/1042/update',dict(version=r['version'],agentId=999))[0],422);self.assertEqual(call('/api/desk/requests/1042/update',dict(version=r['version'],agentId=None))[0],200);desk.init();self.assertIsNone(request(1042)['agentId']);self.assertTrue(any(a['action']=='Solicitud creada' for a in call('/api/crm')[1]['activity']))
 def test_07_task_status_persists(self):
  r=request(1042);self.assertEqual(call('/api/desk/requests/1042/task-status',dict(version=r['version'],taskId=1,done=True))[0],200);desk.init();self.assertTrue(next(t for t in call('/api/desk')[1]['tasks'] if t['id']==1)['done']);self.assertIsNone(request(1042)['agentId'])
try:result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
finally:server.shutdown();server.server_close();gc.collect();tmp.cleanup()
sys.exit(not result.wasSuccessful())
