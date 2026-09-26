import os
os.environ['NEXO_TEST_MODE']='1'
import os,sys,tempfile,threading,json,unittest,urllib.request
from pathlib import Path
from datetime import datetime
storage=tempfile.TemporaryDirectory()
for key,sub in [('NEXO_TEAM_DATA','team'),('NEXO_CRM_DATA','crm'),('NEXO_LEAVE_DATA','leaves')]:os.environ[key]=storage.name+'/'+sub
sys.path.insert(0,str(Path('src/backend').resolve()))
import report_server as r
r.team.init();r.desk.init();r.leave.init()
server=r.team.ThreadingHTTPServer(('127.0.0.1',0),r.Handler);threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}'
def call(path,data=None,role='admin',employee=1):
 req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','X-Nexo-Client':'team','X-Nexo-View':role,'X-Nexo-Employee':str(employee)})
 with urllib.request.urlopen(req) as response:return json.load(response)
def request():return next(x for x in call('/api/desk')['requests'] if x['id']==1042)
class Stability(unittest.TestCase):
 def test_01_no_parallel_tasks(self):self.assertEqual(call('/api/desk')['tasks'],[])
 def test_02_task_single_record(self):
  call('/api/desk/requests/1042/tasks',dict(version=request()['version'],title='Validar integración',owner=3,priority=r.PRIORITY.HIGH,due=''))
  task=call('/api/desk')['tasks'][0];call('/api/desk/requests/1042/task-status',dict(version=request()['version'],taskId=task['id'],done=True),'employee',3)
  data=call('/api/desk');self.assertEqual(len(data['tasks']),1);self.assertTrue(data['tasks'][0]['done']);self.assertEqual(data['tasks'][0]['status'],r.TASK.COMPLETED);self.assertEqual(request()['agentId'],2)
 def test_03_resolved_time_stable(self):
  call('/api/desk/requests/1042/update',dict(version=request()['version'],status=r.REQUEST.RESOLVED));stamp=request()['resolvedAt']
  call('/api/desk/requests/1042/update',dict(version=request()['version'],priority=r.PRIORITY.URGENT));self.assertEqual(request()['resolvedAt'],stamp)
  today=datetime.now(r.LOCAL).date().isoformat();report=call('/api/reports?start='+today+'&end='+today);self.assertEqual(report['kpis']['resolved'],1)
 def test_04_identity_and_audit_preparation(self):
  with r.team.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM users').fetchone()[0],0)
  with r.crm.connect() as c:
   events=c.execute('SELECT * FROM desk_events').fetchall();self.assertGreater(len(events),3)
   for e in events:self.assertEqual(e['entityType'],'request');self.assertIsNone(e['actorUserId']);self.assertEqual(e['entityId'],e['request_id']);self.assertEqual(e['timestamp'],e['created_at'])
 def test_05_employee_licence_identity(self):
  item=call('/api/absences',dict(employee=1,type='Estudio / Examen',start='2026-10-12',end='2026-10-12',reason='Prueba',attachment=''),'employee',3)['item'];self.assertEqual(item['employee'],3)
  call('/api/absences/'+str(item['id'])+'/approve',dict(version=item['version'],confirm=True));own=call('/api/absences',role='employee',employee=3);self.assertTrue(any(l['id']==item['id'] and l['status']==r.LEAVE.APPROVED for l in own['items']))
 def test_06_employee_fields(self):
  for e in call('/api/team')['employees']:self.assertNotIn('load',e);self.assertNotIn('status',e);self.assertIn(e['laborStatus'],[r.LABOR.ACTIVE,r.LABOR.INACTIVE])
 def test_07_shared_config(self):
  config=json.loads(Path('src/domain.json').read_text(encoding='utf-8'));self.assertEqual(list(config['REQUEST'].values()),r.desk.STATES)
if __name__=='__main__':
 try:result=unittest.main(exit=False).result
 finally:server.shutdown();server.server_close()
 sys.exit(0 if result.wasSuccessful() else 1)
