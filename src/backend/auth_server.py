"""Punto de entrada autenticado de Nexo."""
import json,time,secrets,hashlib,re,os,sys
from urllib.parse import urlparse
import report_server as reports
import auth
team=reports.team
class Server(team.ThreadingHTTPServer):
 allow_reuse_address=False
 def server_bind(self):
  import socket
  if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
  super().server_bind()
class Handler(reports.Handler):
 def do_GET(self):
  path=urlparse(self.path).path
  if path not in ['/api/auth/me','/api/users','/api/users/policy'] and not re.fullmatch(r'/api/users/\d+',path):
   if path in ['/login','/inicio','/equipo','/clientes','/solicitudes','/licencias','/reportes','/usuarios','/tareas']:
    self.path='/index.html'
   return super().do_GET()
  try:
   self.guard()
   if path=='/api/auth/me':return self.send_json(200,{'user':self.principal})
   if path=='/api/users/policy':return self.send_json(200,auth.POLICY)
   with team.connect() as c:
    if path=='/api/users':return self.send_json(200,{'users':[auth.public(r,c) for r in c.execute('SELECT * FROM users ORDER BY id')]})
    row=c.execute('SELECT * FROM users WHERE id=?',(int(path.rsplit('/',1)[-1]),)).fetchone()
    if not row:raise team.Validation({'_form':'Usuario no encontrado.'},404)
    return self.send_json(200,{'user':auth.public(row,c),'events':[dict(r) for r in c.execute('SELECT * FROM user_audit WHERE entityId=? ORDER BY id DESC',(row['id'],))]})
  except team.Validation as e:self.send_json(e.status,{'errors':e.fields})
 def mutate(self):
  path=urlparse(self.path).path
  if not path.startswith(('/api/auth/','/api/users')):return super().mutate()
  try:
   if path=='/api/auth/login':
    self.guard(True,authentication=False);data=self.body();email=str(data.get('email','')).strip().lower();password=data.get('password','');errors={}
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):errors['email']='Ingresá un correo válido.'
    if not isinstance(password,str) or not password or len(password)>128:errors['password']='Ingresá tu contraseña.'
    if errors:raise team.Validation(errors)
    now=time.time();key=hashlib.sha256((self.client_address[0]+'|'+email).encode()).hexdigest()
    with team.connect() as c:
     c.execute('BEGIN IMMEDIATE');c.execute('DELETE FROM login_attempts WHERE expiresAt<?',(now,));ipkey='ip:'+self.client_address[0];ip=c.execute('SELECT * FROM login_attempts WHERE key=?',(ipkey,)).fetchone()
     if ip and ip['count']>=60:raise team.Validation({'_form':'Demasiados intentos. Esperá antes de volver a intentar.'},429)
     c.execute('INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',(ipkey,now+900));attempt=c.execute('SELECT * FROM login_attempts WHERE key=?',(key,)).fetchone()
     if attempt and attempt['count']>=8:raise team.Validation({'_form':'Demasiados intentos. Esperá 15 minutos antes de volver a intentar.'},429)
     c.execute('INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',(key,now+900));row=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
    valid=auth.verify(password,row['passwordHash'] if row else None)
    if not row or not valid:
     raise team.Validation({'_form':auth.GENERIC},401)
    user=auth.public(row)
    if row['status']!='ACTIVE' or (user['employeeId'] and (not user['employee'] or user['employee']['laborStatus']!=team.LABOR.ACTIVE)):raise team.Validation({'_form':'No podés acceder a VitaDev con esta cuenta. Contactá al administrador.'},403)
    remember=data.get('remember') is True;token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
    with team.connect() as c:
     from http.cookies import SimpleCookie
     previous=SimpleCookie(self.headers.get('Cookie',''))
     if auth.COOKIE in previous:c.execute('DELETE FROM sessions WHERE tokenHash=?',(hashlib.sha256(previous[auth.COOKIE].value.encode()).hexdigest(),))
     c.execute('DELETE FROM sessions WHERE expiresAt<?',(now,));c.execute('DELETE FROM login_attempts WHERE key=?',(key,));c.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row['id'],csrf,now+(2592000 if remember else 28800),now,604800 if remember else 7200));c.execute('UPDATE users SET lastLoginAt=?,lastAccess=? WHERE id=?',(team.now(),team.now(),row['id']));auth.principal.set(user);auth.audit(c,'Inicio de sesión',row['id'])
    self.extra_headers=[('Set-Cookie',auth.cookie_header(token,remember))];user['csrfToken']=csrf;return self.send_json(200,{'user':user})
   self.guard(True);data=self.body()
   if path=='/api/auth/logout':
    with team.connect() as c:c.execute('DELETE FROM sessions WHERE tokenHash=?',(self.session_hash,));auth.audit(c,'Cierre de sesión',self.principal['id'])
    self.extra_headers=[('Set-Cookie',auth.cookie_header('')+'; Max-Age=0')];return self.send_json(200,{'ok':True})
   if path=='/api/users' and self.command=='POST':return self.send_json(201,{'user':auth.save_user(data)})
   match=re.fullmatch(r'/api/users/(\d+)',path)
   if match and self.command in ['POST','PUT']:return self.send_json(200,{'user':auth.save_user(data,int(match[1]))})
   raise team.Validation({'_form':'Operación no permitida.'},403)
  except team.Validation as e:self.send_json(e.status,{'errors':e.fields})
  except (ValueError,TypeError):self.send_json(400,{'errors':{'_form':'Datos inválidos.'}})
  except Exception:
   import logging
   logging.exception('Error interno en operación de acceso')
   self.send_json(500,{'errors':{'_form':'No se pudo completar la operación. Intentá nuevamente.'}})
 def do_DELETE(self):
  try:self.guard(True);raise team.Validation({'_form':'Los usuarios con historial se desactivan; no se eliminan.'},403)
  except team.Validation as e:self.send_json(e.status,{'errors':e.fields})
def init():team.init();reports.desk.init();reports.leave.init();auth.init()
if __name__=='__main__':
 if auth.test_mode():sys.exit('NEXO_TEST_MODE es exclusivo de las suites de prueba; desactivalo para iniciar Nexo.')
 init()
 if '--create-admin' in sys.argv:
  import getpass
  with team.connect() as c:
   if c.execute("SELECT 1 FROM users WHERE role='ADMIN' AND status='ACTIVE'").fetchone():sys.exit('Ya existe un administrador. Gestioná las cuentas desde Nexo.')
  email=input('Correo del primer administrador: ').strip();password=getpass.getpass('Contraseña (12 a 128 caracteres): ')
  if password!=getpass.getpass('Repetir contraseña: '):sys.exit('Las contraseñas no coinciden.')
  try:user=auth.save_user({'email':email,'password':password,'role':'ADMIN','permissionProfile':'ADMINISTRATOR','status':'ACTIVE','employeeId':None});print('Administrador creado. Iniciá Nexo e ingresá con esas credenciales.')
  except team.Validation as e:sys.exit(' '.join(e.fields.values()))
 else:
  port=int(os.environ.get('NEXO_PORT','4173'));server=Server(('127.0.0.1',port),Handler);print(f'VitaDev: http://127.0.0.1:{port}/login',flush=True);server.serve_forever()
