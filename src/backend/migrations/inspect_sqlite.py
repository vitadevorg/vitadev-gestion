from contextlib import closing
"""Inspección de SQLite sin escrituras ni exportación de datos personales/credenciales."""
import argparse,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
DATABASES={'team':'team-data/team.sqlite3','crm':'crm-data/crm.sqlite3','leave':'leave-data/leaves.sqlite3'}
def inspect(work):
 report={'databases':{},'issues':[]};data={}
 for key,relative in DATABASES.items():
  path=work/relative
  if not path.is_file():raise ValueError('Falta la base '+relative)
  with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as c:
   c.row_factory=sqlite3.Row
   if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':report['issues'].append(key+': integridad SQLite inválida')
   for r in c.execute('PRAGMA foreign_key_check'):report['issues'].append(f'{key}: FK inválida en {r[0]}, fila {r[1]}')
   tables={}
   for name, in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
    if not name.replace('_','').isalnum():raise ValueError('Nombre de tabla no compatible')
    rows=[dict(r) for r in c.execute('SELECT * FROM '+name)];data[key,name]=rows
    fields={}
    for row in rows:
     if 'payload' not in row:continue
     payload=json.loads(row['payload']);kind=row.get('kind',name);fields.setdefault(kind,{})
     for field,value in payload.items():fields[kind].setdefault(field,set()).add(type(value).__name__)
    tables[name]={'count':len(rows),'columns':[dict(r) for r in c.execute('PRAGMA table_info('+name+')')],'foreign_keys':[dict(r) for r in c.execute('PRAGMA foreign_key_list('+name+')')],'json_fields':{kind:{field:sorted(types) for field,types in values.items()} for kind,values in fields.items()}}
   report['databases'][key]={'file':relative,'tables':tables}
 employees={r['id'] for r in data['team','employees']};users={r['id'] for r in data['team','users']}
 records={r['id']:r for r in data['crm','records']};requests={r['id']:r for r in data['crm','desk_requests']}
 def fk(value,ids,where,nullable=True):
  if value is None and nullable:return
  if value not in ids:report['issues'].append(where+': referencia inexistente '+str(value))
 def kind(value,expected,where,nullable=False):fk(value,{i for i,r in records.items() if r['kind']==expected},where,nullable)
 for r in data['team','employees']:
  e=json.loads(r['payload']);fk(e.get('managerId'),employees,'employee '+str(r['id'])+' manager')
 for r in data['team','users']:fk(r['employeeId'],employees,'user '+str(r['id'])+' employee')
 for r in records.values():
  p=json.loads(r['payload']);where=r['kind']+' '+str(r['id'])
  if r['kind']=='clients':fk(p.get('owner'),employees,where+' owner')
  elif r['kind'] in ['contacts','subscriptions','contracts']:
   kind(p.get('clientId'),'clients',where+' client');
   if r['client_id']!=p.get('clientId'):report['issues'].append(where+': client_id difiere de payload.clientId')
  if r['kind']=='subscriptions':kind(p.get('productId'),'catalog',where+' product')
  if r['kind']=='contracts':
   for sid in p.get('subscriptionIds',[]):
    kind(sid,'subscriptions',where+' subscription')
    if sid in records and json.loads(records[sid]['payload']).get('clientId')!=p.get('clientId'):report['issues'].append(where+': contratación de otro cliente')
 for r in requests.values():
  p=json.loads(r['payload']);where='request '+str(r['id']);kind(r['client_id'],'clients',where+' client');kind(r['subscription_id'],'subscriptions',where+' subscription');kind(r['contact_id'],'contacts',where+' contact',True);fk(p.get('agentId'),employees,where+' agent')
  for column,key in [('client_id','clientId'),('subscription_id','subscriptionId'),('contact_id','contactId')]:
   if r[column]!=p.get(key):report['issues'].append(where+': '+column+' difiere del JSON')
  sub=records.get(r['subscription_id']);contact=records.get(r['contact_id'])
  for linked in [sub,contact]:
   if linked and json.loads(linked['payload']).get('clientId')!=r['client_id']:report['issues'].append(where+': relación de otro cliente')
 for r in data['crm','desk_tasks']:
  p=json.loads(r['payload']);fk(p.get('owner'),employees,'task '+str(r['id'])+' owner',False)
  if r['request_id']!=p.get('ticket'):report['issues'].append('task '+str(r['id'])+': request_id difiere de ticket')
 for r in data['leave','absences']:fk(r['employee'],employees,'leave '+str(r['id'])+' employee',False)
 for (database,table),rows in data.items():
  for r in rows:
   for key,ids in [('actorUserId',users),('actorEmployeeId',employees)]:
    if key in r:fk(r[key],ids,table+' '+str(r.get('id'))+' '+key)
 # Every registered file must exist before a migration; no fabricated attachment.
 for database,table,folder in [('crm','files','crm-data/files'),('crm','desk_files','crm-data/files'),('leave','absence_files','leave-data/files')]:
  for r in data[database,table]:
   if not (work/folder/(('desk-' if table=='desk_files' else '')+r['id'])).is_file():report['issues'].append(table+' '+r['id']+': archivo no encontrado')
 report['ready_for_export']=not report['issues'];return report
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path,default=ROOT/'work');parser.add_argument('--output',type=Path);args=parser.parse_args()
 result=inspect(args.work);text=json.dumps(result,ensure_ascii=False,indent=2)
 if args.output:args.output.write_text(text,encoding='utf-8')
 else:print(text)
 raise SystemExit(0 if result['ready_for_export'] else 2)
