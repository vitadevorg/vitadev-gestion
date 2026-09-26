"""Carga inicial PostgreSQL, transaccional y explícita. No cambia el backend en ejecución."""
import argparse,json,os,sqlite3,sys
from contextlib import ExitStack
from datetime import datetime,timezone
from pathlib import Path
from inspect_sqlite import ROOT,DATABASES
from transform import prepare
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database_config import load_environment,connection_options

JSON_COLUMNS={'extra_data','metadata','changed_fields','legacy_permissions'}

def connect():
 url,options=connection_options()
 import psycopg
 return psycopg.connect(url,**options)

def load(connection,tables,schema='vitadev'):
 from psycopg import sql
 from psycopg.types.json import Jsonb
 from postgres_model import schema_name,install
 schema=schema_name(schema)
 with connection.transaction():
  # Un destino existente se rechaza: no se mezclan ni sobrescriben datos.
  connection.execute('SELECT pg_advisory_xact_lock(884109214)')
  if connection.execute("SELECT 1 FROM pg_namespace WHERE nspname=%s",(schema,)).fetchone():raise ValueError('El esquema de destino ya existe. No se sobrescribió.')
  connection.execute(Path(__file__).with_name('001_supabase.sql').read_text(encoding='utf-8').replace('vitadev',schema))
  for table,rows in tables.items():
   for row in rows:
    columns=list(row);values=[Jsonb(row[k]) if k in JSON_COLUMNS and row[k] is not None else row[k] for k in columns]
    statement=sql.SQL('INSERT INTO {}.{} ({}) VALUES ({})').format(sql.Identifier(schema),sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,columns)),sql.SQL(',').join(sql.Placeholder() for _ in columns))
    connection.execute(statement,values)
   actual=connection.execute(sql.SQL('SELECT count(*) FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(table))).fetchone()[0]
   if actual!=len(rows):raise ValueError('Conteo diferente en '+table)
   if rows and 'extra_data' in rows[0]:
    actual_rows=dict(connection.execute(sql.SQL('SELECT id,extra_data FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(table))).fetchall())
    if actual_rows!={r['id']:r['extra_data'] for r in rows}:raise ValueError('Contenido original no conservado en '+table)
  # Identidades nuevas deben continuar por encima de los IDs importados.
  sequences=connection.execute("SELECT table_name FROM information_schema.columns WHERE table_schema=%s AND column_name='id' AND is_identity='YES'",(schema,)).fetchall()
  for table, in sequences:
   maximum=connection.execute(sql.SQL('SELECT max(id) FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(table))).fetchone()[0]
   connection.execute("SELECT setval(pg_get_serial_sequence(%s,'id'),%s,%s)",(schema+'.'+table,maximum or 1,maximum is not None))
  connection.execute('SET CONSTRAINTS ALL IMMEDIATE')
  install(connection,schema)
 return {table:len(rows) for table,rows in tables.items()}

def migrate(work):
 # Bloquea escrituras SQLite durante copia/lectura. El servicio debe estar detenido.
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');backup=work/'backups'/('supabase-'+stamp)
 with ExitStack() as stack:
  locks=[]
  for relative in DATABASES.values():
   path=work/relative
   if not path.is_file():raise ValueError('Falta la base de origen '+relative)
   c=sqlite3.connect(path,timeout=1);stack.callback(c.close);c.execute('BEGIN IMMEDIATE');locks.append(c)
  tables=prepare(work);backup.mkdir(parents=True,exist_ok=False)
  for relative in DATABASES.values():
   source=sqlite3.connect((work/relative).resolve().as_uri()+'?mode=ro',uri=True);stack.callback(source.close)
   target=sqlite3.connect(backup/Path(relative).name);stack.callback(target.close)
   source.backup(target)
  with connect() as destination:counts=load(destination,tables)
 return counts

def main():
 load_environment()
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work',type=Path,default=ROOT/'work');parser.add_argument('--apply',action='store_true');parser.add_argument('--source-stopped',action='store_true',help='Confirma que el backend fue detenido antes de transferir');args=parser.parse_args()
 if args.apply:
  if not args.source_stopped:parser.error('Detené el backend y usá --source-stopped para una transferencia consistente.')
  if not os.environ.get('SUPABASE_DB_URL'):parser.error('Falta SUPABASE_DB_URL. No se cambió ninguna base.')
  counts=migrate(args.work)
 else:counts={table:len(rows) for table,rows in prepare(args.work).items()}
 print(json.dumps({'mode':'transferred' if args.apply else 'dry-run','tables':counts,'runtime_database':'SQLite; conmutación del backend pendiente'},indent=2))
if __name__=='__main__':
 try:main()
 except Exception as error:
  # Nunca imprimir DSN, parámetros de INSERT, hashes ni contenido de sesiones.
  print('No se completó la migración. Origen conservado. Error: '+type(error).__name__,file=sys.stderr);sys.exit(1)
