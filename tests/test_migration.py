"""Pruebas locales de preparación. No equivalen a tests PostgreSQL/Supabase."""
import os,sys,tempfile,unittest,json,hashlib,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
temporary=tempfile.TemporaryDirectory();work=Path(temporary.name)
for key,folder in [('NEXO_TEAM_DATA','team-data'),('NEXO_CRM_DATA','crm-data'),('NEXO_LEAVE_DATA','leave-data')]:os.environ[key]=str(work/folder)
sys.path.insert(0,str(ROOT/'src/backend'));sys.path.insert(0,str(ROOT/'src/backend/migrations'))
import auth_server,inspect_sqlite,transform,migrate_supabase
auth_server.init()
class MigrationTests(unittest.TestCase):
 def test_01_inventory_has_no_private_values(self):
  result=inspect_sqlite.inspect(work);self.assertTrue(result['ready_for_export']);text=json.dumps(result)
  self.assertNotIn('example.invalid',text);self.assertNotIn('scrypt$',text)
  self.assertEqual(len(result['databases']),3)
 def test_02_ids_and_links_preserved(self):
  tables=transform.prepare(work);self.assertEqual([r['id'] for r in tables['employees']],[1,2,3,4,5,6]);self.assertEqual(len(tables['requests']),3)
  by_id={r['id']:r for r in tables['subscriptions']}
  for r in tables['requests']:self.assertEqual(by_id[r['subscription_id']]['client_id'],r['client_id'])
 def test_03_unknown_json_fields_are_preserved(self):
  data=transform.read_source(work);r=data['team','employees'][0];p=json.loads(r['payload']);p['historicalField']={'original':True};r['payload']=json.dumps(p)
  tables=transform.convert(data,json.loads((ROOT/'src/access-policy.json').read_text(encoding='utf-8')))
  self.assertEqual(tables['employees'][0]['extra_data']['historicalField'],{'original':True})
 def test_04_missing_historical_dates_are_not_invented(self):
  tables=transform.prepare(work)
  self.assertIsNone(tables['clients'][0]['since']);self.assertIsNone(tables['subscriptions'][0]['start_date'])
 def test_05_dry_run_does_not_modify_sqlite(self):
  paths=[work/p for p in inspect_sqlite.DATABASES.values()];before=[hashlib.sha256(p.read_bytes()).digest() for p in paths]
  transform.prepare(work)
  self.assertEqual(before,[hashlib.sha256(p.read_bytes()).digest() for p in paths])
 def test_06_orphan_across_databases_blocks_export(self):
  with auth_server.team.connect() as c:
   row=c.execute('SELECT * FROM employees WHERE id=1').fetchone();original=row['payload'];p=json.loads(original);p['managerId']=999;c.execute('UPDATE employees SET payload=? WHERE id=1',(json.dumps(p),))
  try:
   self.assertFalse(inspect_sqlite.inspect(work)['ready_for_export'])
   with self.assertRaises(ValueError):transform.prepare(work)
  finally:
   with auth_server.team.connect() as c:c.execute('UPDATE employees SET payload=? WHERE id=1',(original,))
 def test_07_no_connection_without_environment(self):
  value=os.environ.pop('SUPABASE_DB_URL',None)
  try:
   with self.assertRaisesRegex(ValueError,'SUPABASE_DB_URL'):migrate_supabase.connect()
  finally:
   if value is not None:os.environ['SUPABASE_DB_URL']=value
 def test_08_passwords_and_session_data_remain_in_memory(self):
  data=transform.read_source(work);data['team','users']=[dict(id=7,email='fixture@example.invalid',passwordHash='hash-fixture',role='ADMIN',status='ACTIVE',employeeId=1,permissionProfile='ADMINISTRATOR',lastLoginAt=None,createdAt=None,updatedAt=None,permissions='[]',lastAccess=None)]
  data['team','sessions']=[dict(tokenHash='hash-of-token',userId=7,csrf='test-csrf',expiresAt=9,lastSeen=1,idleSeconds=4)]
  tables=transform.convert(data,json.loads((ROOT/'src/access-policy.json').read_text(encoding='utf-8')))
  self.assertEqual(tables['users'][0]['password_hash'],'hash-fixture');self.assertEqual(tables['sessions'][0]['user_id'],7)
 def test_09_unknown_record_kind_rejected(self):
  data=transform.read_source(work);data['crm','records'][0]['kind']='unsupported'
  with self.assertRaises(ValueError):transform.convert(data,json.loads((ROOT/'src/access-policy.json').read_text(encoding='utf-8')))
 def test_10_desk_file_path_prefix(self):
  with auth_server.reports.desk.crm.connect() as c:c.execute('INSERT INTO desk_files VALUES(?,?,?)',('fixture','f.txt','text/plain'))
  file=work/'crm-data/files/desk-fixture';file.write_text('fixture')
  try:self.assertTrue(inspect_sqlite.inspect(work)['ready_for_export'])
  finally:
   with auth_server.reports.desk.crm.connect() as c:c.execute('DELETE FROM desk_files WHERE id=?',('fixture',))
   file.unlink()
if __name__=='__main__':unittest.main()
