from contextvars import ContextVar
principal=ContextVar("principal",default=None)
def bind(c):
 c.create_function("nexo_user",0,lambda:(principal.get() or {}).get("id"))
 c.create_function("nexo_employee",0,lambda:(principal.get() or {}).get("employeeId"))
 c.create_function("nexo_actor",0,lambda:((principal.get() or {}).get("employee") or {}).get("name") or (principal.get() or {}).get("email"))
"""Esquema preparatorio. No autentica ni crea cuentas de ejemplo."""
def prepare_users(c):
 c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT NOT NULL COLLATE NOCASE UNIQUE, role TEXT NOT NULL, status TEXT NOT NULL, employeeId INTEGER REFERENCES employees(id), permissions TEXT NOT NULL DEFAULT "[]", lastAccess TEXT)')

def prepare_audit(c,table,entity_type,entity_column):
 # Identificadores exclusivos de código; nunca se reciben desde una petición.
 columns={r[1] for r in c.execute(f'PRAGMA table_info({table})')}
 for name,kind in [('actorUserId','INTEGER'),('actorEmployeeId','INTEGER'),('entityType','TEXT'),('entityId','INTEGER'),('timestamp','TEXT'),('metadata','TEXT')]:
  if name not in columns:c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {kind}')
 c.execute(f"UPDATE {table} SET entityType=?,entityId={entity_column},timestamp=created_at,metadata=COALESCE(metadata,'{{}}') WHERE entityType IS NULL",(entity_type,))
 c.execute(f'DROP TRIGGER IF EXISTS {table}_identity')
 c.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_identity AFTER INSERT ON {table} BEGIN UPDATE {table} SET actorUserId=nexo_user(),actorEmployeeId=nexo_employee(),actor=COALESCE(nexo_actor(),NEW.actor),entityType='{entity_type}',entityId=NEW.{entity_column},timestamp=NEW.created_at,metadata=COALESCE(NEW.metadata,'{{}}') WHERE id=NEW.id; END")
