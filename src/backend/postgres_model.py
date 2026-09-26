"""Proyecciones SQL del contrato existente sobre el modelo relacional v1.

Las vistas son de lectura. Todas las escrituras las realiza postgres_backend
sobre tablas normalizadas; no existe una copia editable en tablas legacy.
"""
import re

KINDS={'clients':'clients','contacts':'contacts','catalog':'products','subscriptions':'subscriptions','contracts':'contracts'}
PAYLOADS={
 'employees':('employees',dict(email='email',legajo='legajo',first_name='firstName',last_name='lastName',position='role',area='area',dni='dni',birth_date='birthDate',phone='phone',manager_id='managerId',hire_date='hireDate',work_modality='modality',labor_status='laborStatus',availability='availability',photo_path='photo')),
 'clients':('clients',dict(name='name',legal_name='legalName',cuit='cuit',organization_type='organizationType',country='country',province='province',city='city',address='address',postal_code='postalCode',owner_employee_id='owner',status='status',logo_path='logo',since='since')),
 'contacts':('contacts',dict(client_id='clientId',first_name='firstName',last_name='lastName',email='email',position='position',phone='phone',role='role',status='status',is_principal='principal')),
 'catalog':('products',dict(name='name',description='description',product_type='type',status='status')),
 'subscriptions':('subscriptions',dict(client_id='clientId',product_id='productId',plan='plan',status='status',start_date='start')),
 'contracts':('contracts',dict(client_id='clientId',number='number',status='status',signed_date='signed',start_date='start',end_date='end',renewal='renewal',period='period',currency='currency',amount='amount',notes='notes')),
 'desk_requests':('requests',dict(client_id='clientId',subscription_id='subscriptionId',contact_id='contactId',title='title',description='description',status='status',priority='priority',request_type='type',queue='queue',agent_employee_id='agentId')),
 'desk_tasks':('tasks',dict(request_id='ticket',client_id='client',owner_employee_id='owner',title='title',status='status',priority='priority',due_date='due',done='done')),
 'absences':('leaves',dict(employee_id='employee',leave_type='type',start_date='start',end_date='end',days='days',status='status',reason='reason',created_by_label='createdBy',resolved_at='resolvedAt',resolved_by_label='resolvedBy',resolution_comment='resolutionComment')),
}
SIMPLE={
 'users':dict(id='id',email='email',role='role_code',status='status',employeeId='employee_id',permissions='legacy_permissions',lastAccess='legacy_last_access',passwordHash='password_hash',permissionProfile='profile_code',lastLoginAt='last_login_at',createdAt='created_at',updatedAt='updated_at'),
 'sessions':dict(tokenHash='token_hash',userId='user_id',csrf='csrf',expiresAt='expires_at',lastSeen='last_seen',idleSeconds='idle_seconds'),
 'login_attempts':dict(key='key',count='count',expiresAt='expires_at'),
}
AUDITS={'employee_audit':('employee_id','employee_id','employee'),'activity':('client_id','client_id','client'),'desk_events':('request_id','request_id','request'),'absence_events':('absence_id','leave_id','leave'),'user_audit':('entityId','user_id','user')}
FILES={'files':('crm','crm-data/files/'),'desk_files':('request','crm-data/files/desk-'),'absence_files':('leave','leave-data/files/')}

def schema_name(value):
 if not re.fullmatch(r'vitadev(?:_test_[a-z0-9_]+)?',value):raise ValueError('Esquema PostgreSQL no permitido')
 return value

def json_value(column,key):
 # NULL opcional conserva la representación histórica (cadena vacía o null).
 expression=f't.{column}'
 if column=='amount':expression+='::text'
 return f"COALESCE(to_jsonb({expression}),CASE WHEN t.extra_data->'{key}'='\"\"'::jsonb THEN '\"\"'::jsonb ELSE 'null'::jsonb END)"

def timestamp_sql(column):
 return f"(to_char({column} AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US')||'+00:00')"

def metadata_sql(column):
 return f"CASE WHEN jsonb_typeof({column}->'metadata')='string' THEN {column}->>'metadata' ELSE COALESCE({column}->'metadata','{{}}'::jsonb)::text END"

def payload_sql(key):
 table,mapping=PAYLOADS[key];mapping={**mapping,'created_at':'createdAt','updated_at':'updatedAt'}
 pairs=[f"'{key}',{json_value(column,key)}" for column,key in mapping.items()]
 children={
  'employees':{'skills':"SELECT jsonb_agg(skill ORDER BY position) FROM employee_skills WHERE employee_id=t.id"},
  'catalog':{'plans':"SELECT jsonb_agg(name ORDER BY position) FROM product_plans WHERE product_id=t.id",'configFields':"SELECT jsonb_agg(name ORDER BY position) FROM product_options WHERE product_id=t.id"},
  'subscriptions':{'configuration':"SELECT jsonb_agg(option_name ORDER BY position) FROM subscription_options WHERE subscription_id=t.id"},
  'contracts':{'subscriptionIds':"SELECT jsonb_agg(subscription_id ORDER BY position) FROM contract_subscriptions WHERE contract_id=t.id"},
  'desk_requests':{'attachments':"SELECT jsonb_agg('/api/desk/files/'||attachment_id ORDER BY position) FROM request_attachments WHERE request_id=t.id"},
 }
 for field,query in children.get(key,{}).items():pairs.append(f"'{field}',COALESCE(({query}),'[]'::jsonb)")
 if key=='employees':pairs.append("'name',to_jsonb(t.first_name||' '||t.last_name)")
 if key=='contracts':pairs.append("'document',to_jsonb(COALESCE('/api/crm/files/'||t.document_id,''))")
 if key=='absences':pairs.append("'attachment',to_jsonb(COALESCE(t.attachment_id,''))")
 return "(t.extra_data||jsonb_build_object("+','.join(pairs)+"))::text"

def views():
 out={}
 out['employees']=f'SELECT t.id,t.email,t.legajo,t.version,{payload_sql("employees")} AS payload FROM employees t'
 records=[]
 for kind,table in KINDS.items():
  client='t.client_id' if kind in ('contacts','subscriptions','contracts') else 'NULL::bigint'
  unique={'clients':"NULLIF(lower(t.cuit),'')",'catalog':'lower(t.name)','contracts':'lower(t.number)'}.get(kind,'NULL::text')
  records.append(f"SELECT t.id,'{kind}'::text AS kind,{client} AS client_id,{unique} AS unique_key,t.version,{payload_sql(kind)} AS payload FROM {table} t")
 out['records']=' UNION ALL '.join(records)
 for key,columns in [('desk_requests','t.id,t.client_id,t.subscription_id,t.contact_id,t.version'),('desk_tasks','t.id,t.request_id'),('absences','t.id,t.employee_id AS employee,t.start_date::text AS start,t.end_date::text AS end,t.status,t.version')]:
  out[key]=f'SELECT {columns},{payload_sql(key)} AS payload FROM {PAYLOADS[key][0]} t'
 for table,mapping in SIMPLE.items():
  def expr(key,column):
   if key=='permissions':return "COALESCE((SELECT jsonb_agg(permission_code ORDER BY permission_code) FROM profile_permissions WHERE profile_code=t.profile_code),'[]'::jsonb)::text"
   if column.endswith('_at') and table=='users':return timestamp_sql('t.'+column)
   return 't.'+column
  out[table]='SELECT '+','.join(f'{expr(key,column)} AS "{key}"' for key,column in mapping.items())+f' FROM {table} t'
 for table,(scope,_) in FILES.items():
  out[table]=f"SELECT id,name,mime"+(',owner_employee_id AS owner' if table=='absence_files' else '')+f" FROM attachments WHERE scope='{scope}'"
 for table,(legacy,column,entity) in AUDITS.items():
  common='source_id AS id,action,actor_user_id AS "actorUserId",actor_employee_id AS "actorEmployeeId",entity_type AS "entityType",entity_id AS "entityId",'+timestamp_sql('occurred_at')+' AS timestamp'
  metadata=metadata_sql('metadata')+' AS metadata'
  if table=='user_audit':extra=''
  else:
   extra=f", {column} AS {legacy},actor_label AS actor,"+timestamp_sql('occurred_at')+' AS created_at'
   if table=='employee_audit':extra+=',changed_fields::text AS fields'
   elif table=='absence_events':extra+=',comment'
   else:extra+=',reference'
  out[table]=f"SELECT {common},{metadata}{extra} FROM audit_entries WHERE source_table='{table}'"
 out['desk_comments']=f'''SELECT t.id,t.request_id,t.body AS text,t.actor_label AS actor,{timestamp_sql('t.created_at')} AS created_at,
 t.actor_user_id AS "actorUserId",t.actor_employee_id AS "actorEmployeeId",'requestComment'::text AS "entityType",t.request_id AS "entityId",{timestamp_sql('t.created_at')} AS timestamp,
 {metadata_sql('t.extra_data')} AS metadata,
 COALESCE((SELECT jsonb_agg('/api/desk/files/'||attachment_id ORDER BY position) FROM comment_attachments WHERE comment_id=t.id),'[]'::jsonb)::text AS attachments FROM comments t'''
 return out

def install(connection,schema):
 from psycopg import sql
 schema=schema_name(schema)
 connection.execute(sql.SQL('SET LOCAL search_path TO {},pg_catalog').format(sql.Identifier(schema)))
 # Los IDs comerciales conservan el espacio global de records existente.
 connection.execute('CREATE SEQUENCE IF NOT EXISTS records_id_seq')
 connection.execute("SELECT setval('records_id_seq',GREATEST(COALESCE((SELECT max(id) FROM ("+' UNION ALL '.join('SELECT id FROM '+t for t in KINDS.values())+") r),0)+1,1),false)")
 for table,query in views().items():
  connection.execute(sql.SQL('CREATE OR REPLACE VIEW {} WITH (security_invoker=true) AS ').format(sql.Identifier('legacy_'+table))+sql.SQL(query))
 connection.execute("INSERT INTO schema_migrations(version) VALUES(2) ON CONFLICT DO NOTHING")
