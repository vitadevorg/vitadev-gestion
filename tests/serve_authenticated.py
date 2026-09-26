import sys,os
from pathlib import Path
for key in ['NEXO_PORT','NEXO_TEAM_DATA','NEXO_CRM_DATA','NEXO_LEAVE_DATA']:
 if not os.environ.get(key):sys.exit('La fixture exige almacenamiento y puerto explícitos: '+key)
root=Path(__file__).resolve().parents[1]
for key,folder in [('NEXO_TEAM_DATA','team-data'),('NEXO_CRM_DATA','crm-data'),('NEXO_LEAVE_DATA','leave-data')]:
 if Path(os.environ[key]).resolve()==(root/'work'/folder).resolve():sys.exit('La fixture no puede usar los datos normales de Nexo.')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/backend'))
import auth_server as server
server.init()
for email,employee,role,profile in [('admin@test.invalid',1,'ADMIN','ADMINISTRATOR'),('support@test.invalid',2,'EMPLOYEE','SUPPORT'),('employee@test.invalid',3,'EMPLOYEE','EMPLOYEE'),('ana@test.invalid',1,'EMPLOYEE','EMPLOYEE')]:
 if email=='ana@test.invalid' or (os.environ.get('NEXO_FIXTURE_ADMIN_ONLY')=='1' and role!='ADMIN'):continue
 server.auth.save_user({'email':email,'password':'Nexo-test-password-2026','employeeId':employee,'role':role,'permissionProfile':profile,'status':'ACTIVE'})
http=server.team.ThreadingHTTPServer(('127.0.0.1',int(os.environ['NEXO_PORT'])),server.Handler);print('Authenticated test server ready',flush=True);http.serve_forever()
