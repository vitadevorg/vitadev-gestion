import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from domain import REQUEST,PRIORITY,LEAVE,LABOR,AVAILABILITY,TASK
"""Reportes de lectura sobre las fuentes operativas. No genera registros sintéticos."""
import io,json,math
from collections import Counter
from datetime import date,datetime,timedelta,timezone
from urllib.parse import urlparse,parse_qs
import leave_server as leave
desk=leave.desk;crm=desk.crm;team=desk.team
LOCAL=timezone(timedelta(hours=-3))
def day(value):
 if not value:return None
 try:return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(LOCAL).date() if 'T' in value else date.fromisoformat(value)
 except (ValueError,TypeError):return None
def sources(repository=None):
 if repository is not None:return repository.report_sources()
 with crm.connect() as c:
  data={k:crm.rows(c,k) for k in crm.KINDS};data['importedClients']={r['client_id'] for r in c.execute("SELECT client_id FROM activity WHERE action='Registro inicial importado'")};data['requests']=[desk.get(c,r['id']) for r in c.execute('SELECT id FROM desk_requests')];data['events']=[dict(r) for r in c.execute('SELECT * FROM desk_events ORDER BY id')];data['tasks']=[{**json.loads(r['payload']),'id':r['id']} for r in c.execute('SELECT * FROM desk_tasks')]
 c=team.connect()
 try:data['employees']=[team.unpack(r) for r in c.execute('SELECT * FROM employees')]
 finally:c.close()
 with leave.connect() as c:data['leaves']=[leave.decode(r) for r in c.execute('SELECT * FROM absences')]
 return data
def analyze(data,start,end,client=None,product=None,today=None):
 today=today or datetime.now(LOCAL).date();cutoff=min(end,today);days=(end-start).days+1;prev_end=start-timedelta(days=1);prev_start=prev_end-timedelta(days=days-1)
 subs={s['id']:s for s in data['subscriptions']};catalog={p['id']:p for p in data['catalog']};clients={c['id']:c for c in data['clients']}
 selected_clients={c['id'] for c in data['clients'] if (not client or c['id']==client) and (not product or any(s['clientId']==c['id'] and s['productId']==product for s in subs.values()))}
 requests=[r for r in data['requests'] if r['clientId'] in selected_clients and (not product or subs.get(r['subscriptionId'],{}).get('productId')==product)]
 events={r['id']:[e for e in data['events'] if e['request_id']==r['id']] for r in requests}
 received_dates={r['id']:next((e['created_at'] for e in events[r['id']] if e['action']=='Solicitud creada'),None) for r in requests}
 def received(a,b):return [r for r in requests if received_dates[r['id']] and a<=day(received_dates[r['id']])<=b]
 def resolutions(a,b):
  result=[]
  for r in requests:
   hits=[e for e in events[r['id']] if e['action']=='Estado actualizado' and e['reference']==REQUEST.RESOLVED and a<=day(e['created_at'])<=b]
   if hits:result.append((r,max(hits,key=lambda e:e['created_at'])))
  return result
 def state_at(r,at):
  if not day(r['createdAt']) or day(r['createdAt'])>at:return None
  hits=[e for e in events[r['id']] if e['action']=='Estado actualizado' and day(e['created_at'])<=at]
  if hits:return max(hits,key=lambda e:e['created_at'])['reference']
  if at>=today:return r['status']
  if received_dates[r['id']]:return REQUEST.NEW
  return None
 rec=received(start,cutoff);resolved=resolutions(start,cutoff);previous_rec=received(prev_start,prev_end);previous_res=resolutions(prev_start,prev_end)
 def average(pairs):
  values=[]
  for r,e in pairs:
   created=received_dates[r['id']]
   if created:
    seconds=(datetime.fromisoformat(e['created_at'])-datetime.fromisoformat(created)).total_seconds()
    if seconds>=0:values.append(seconds/60)
  return sum(values)/len(values) if values else None
 coverage=min((day(e['created_at']) for e in data['events']),default=today)
 comparable=prev_start>=coverage and prev_end<=today
 rate=100*len(resolved)/len(rec) if rec else None;old_rate=100*len(previous_res)/len(previous_rec) if previous_rec else None
 avg=average(resolved);old_avg=average(previous_res)
 # No hay snapshots de estados comerciales, asignaciones ni disponibilidad base históricas.
 snapshot=cutoff==today and start<=today
 known_clients=[c for c in clients.values() if c['id'] in selected_clients and day(c.get('createdAt')) and day(c['createdAt'])<=cutoff]
 active=sum(c['status']==LABOR.ACTIVE for c in known_clients) if snapshot else None
 new_clients=[c for c in known_clients if not c.get('imported') and c['id'] not in data.get('importedClients',set()) and start<=day(c['createdAt'])<=cutoff]
 clients_start=sum(day(c['createdAt'])<start for c in known_clients) if start>=coverage else None
 touched=[r for r in requests if any(start<=day(e['created_at'])<=cutoff for e in events[r['id']])]
 distribution=Counter(state_at(r,cutoff) or 'Sin historial de estado' for r in touched)
 byproduct=Counter(subs.get(r['subscriptionId'],{}).get('productId') for r in touched);byclient=Counter(r['clientId'] for r in touched)
 client_products=[]
 if snapshot:
  for p in catalog.values():
   ids={s['clientId'] for s in subs.values() if s['clientId'] in selected_clients and s['productId']==p['id'] and s['status']==LABOR.ACTIVE and (not product or p['id']==product)}
   if ids:client_products.append({'name':p['name'],'value':len(ids)})
 group='día' if days<=14 else 'semana' if days<=62 else 'mes';buckets=[];cursor=start
 while cursor<=end:
  if group=='día':last=cursor
  elif group=='semana':last=min(end,cursor+timedelta(days=6))
  else:last=min(end,(cursor.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1))
  buckets.append({'label':cursor.strftime('%d/%m') if group!='mes' else cursor.strftime('%m/%Y'),'start':cursor.isoformat(),'end':last.isoformat(),'received':sum(cursor<=day(received_dates[r['id']])<=last for r in rec),'resolved':sum(cursor<=day(e['created_at'])<=last for r,e in resolved)});cursor=last+timedelta(days=1)
 operational=[];availability=Counter();alerts=[];open_cutoff=[r for r in touched if state_at(r,cutoff) in [REQUEST.NEW,REQUEST.IN_PROGRESS,REQUEST.WAITING_CLIENT]]
 if snapshot:
  scope_employee=set()
  tasks=[t for t in data['tasks'] if t.get('ticket') in {r['id'] for r in touched} and not t.get('done')]
  for e in data['employees']:
   support=sum(r.get('agentId')==e['id'] for r in open_cutoff);task_count=sum(t['owner']==e['id'] for t in tasks)
   if support or task_count:operational.append({'id':e['id'],'name':e['name'],'photo':e.get('photo'),'support':support,'tasks':task_count});scope_employee.add(e['id'])
  if not client and not product:scope_employee={e['id'] for e in data['employees'] if e['laborStatus']==LABOR.ACTIVE}
  for e in data['employees']:
   if e['id'] not in scope_employee or e['laborStatus']!=LABOR.ACTIVE:continue
   absent=any(l['employee']==e['id'] and l['status']==LEAVE.APPROVED and l['start']<=today.isoformat()<=l['end'] for l in data['leaves'])
   availability[AVAILABILITY.ON_LEAVE if absent else e.get('availability',AVAILABILITY.AVAILABLE)]+=1
  old=[r for r in open_cutoff if received_dates[r['id']] and (datetime.now(timezone.utc)-datetime.fromisoformat(received_dates[r['id']])).total_seconds()>48*3600]
  for text,rs in [('Solicitudes abiertas por más de 48 horas',old),('Solicitudes urgentes aún abiertas',[r for r in open_cutoff if r['priority']==PRIORITY.URGENT]),('Solicitudes esperando respuesta del cliente',[r for r in open_cutoff if r['status']==REQUEST.WAITING_CLIENT])]:
   if rs:alerts.append({'text':text,'count':len(rs),'module':'support','ids':[r['id'] for r in rs]})
  if availability[AVAILABILITY.ON_LEAVE]:alerts.append({'text':'Personas de licencia al cierre disponible','count':availability[AVAILABILITY.ON_LEAVE],'module':'calendar','ids':[]})
 return {'start':start.isoformat(),'end':end.isoformat(),'cutoff':cutoff.isoformat(),'previousStart':prev_start.isoformat(),'previousEnd':prev_end.isoformat(),'generatedAt':team.now(),'clientLabel':clients[client]['name'] if client else 'Todos los clientes','productLabel':catalog[product]['name'] if product else 'Todos los productos/servicios','coverage':coverage.isoformat(),'snapshot':snapshot,'kpis':{'active':active,'received':len(rec),'resolved':len(resolved),'rate':rate,'minutes':avg,'receivedChange':100*(len(rec)-len(previous_rec))/len(previous_rec) if comparable and previous_rec else None,'rateChange':rate-old_rate if comparable and rate is not None and old_rate is not None else None,'minutesChange':avg-old_avg if comparable and avg is not None and old_avg is not None else None},'series':buckets,'group':group,'states':dict(distribution),'products':[{'name':catalog.get(p,{}).get('name','Sin producto'), 'value':v,'percent':100*v/len(touched)} for p,v in byproduct.most_common()],'topClients':[{'id':cid,'name':clients[cid]['name'],'value':n} for cid,n in byclient.most_common()],'clients':{'atStart':clients_start,'new':len(new_clients),'active':active},'clientProducts':client_products,'team':operational,'availability':dict(availability),'alerts':alerts,'imported':sum(any(e['action']=='Solicitud importada' for e in events[r['id']]) for r in touched),'activityCount':len(touched),'notes':['Recibidas: solicitudes con evento de creación; las importaciones no se cuentan como recepciones históricas.','Resueltas: solicitudes distintas con resolución fechada en el período; si se reabren, se toma su última resolución del período. La tasa puede superar 100% al resolver pendientes anteriores.','Productos, clientes y estados: solicitudes con actividad registrada en el período; incluye importaciones identificadas.','Clientes activos, carga y disponibilidad: corte actual solo si el período incluye hoy. No hay snapshots históricos suficientes para esos indicadores.','No se interpreta el volumen de trabajo como productividad individual.']}
def pdf_report(r):
 from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether
 from reportlab.lib.styles import getSampleStyleSheet
 from reportlab.lib import colors
 from reportlab.lib.pagesizes import A4
 from reportlab.graphics.shapes import Drawing,Rect,String
 from xml.sax.saxutils import escape
 out=io.BytesIO();styles=getSampleStyleSheet();styles['Title'].textColor=colors.HexColor('#17365c');styles['Heading2'].textColor=colors.HexColor('#17365c');styles['Heading2'].keepWithNext=True;story=[]
 def p(text,style='BodyText'):return Paragraph(escape(str(text)),styles[style])
 def section(title,rows):
  story.append(p(title,'Heading2'))
  if not rows:story.append(p('No hay datos suficientes para este período.'));return
  table=Table([[p(v) for v in row] for row in rows],hAlign='LEFT',colWidths=[340,170] if len(rows[0])==2 else None);table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#dde5ef')),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]));story.append(table)
 k=r['kpis'];value=lambda x: 'No disponible' if x is None else str(x)
 story.extend([p('VitaDev · Reportes','Title'),p(r['start']+' al '+r['end']),p(r['clientLabel']+' · '+r['productLabel']),p('Generado: '+r['generatedAt'][:19].replace('T',' ')+' UTC'),Spacer(1,16)])
 section('Indicadores principales',[['Clientes activos',value(k['active'])],['Solicitudes recibidas',k['received']],['Tasa de resolución',f"{k['rate']:.1f}%" if k['rate'] is not None else 'No disponible'],['Tiempo promedio de resolución',f"{k['minutes']:.0f} minutos" if k['minutes'] is not None else 'No disponible']])
 section('Comparación con el período anterior',[[label,('Sin datos comparativos' if k[key] is None else f'{k[key]:+.1f} {unit}')] for key,label,unit in [('receivedChange','Solicitudes recibidas','%'),('rateChange','Tasa de resolución','puntos porcentuales'),('minutesChange','Tiempo medio de resolución','minutos')]])
 story.append(p('Recibidas vs. resueltas','Heading2'))
 if any(b['received'] or b['resolved'] for b in r['series']):
  series=r['series'];chart=Drawing(510,170);maximum=max(1,max(max(b['received'],b['resolved']) for b in series));w=480/len(series)
  for i,b in enumerate(series):
   for j,key in enumerate(['received','resolved']):chart.add(Rect(20+i*w+j*w*.36,25,w*.3,110*b[key]/maximum,fillColor=colors.HexColor('#2865c7' if j==0 else '#9cafc9'),strokeColor=None))
   if i%max(1,math.ceil(len(series)/10))==0:chart.add(String(20+i*w,10,b['label'],fontSize=7))
  chart.add(String(20,150,'Azul: recibidas · Gris: resueltas',fontSize=9));story.append(chart)
 else:story.append(p('No hay datos suficientes para este período.'))
 section('Estado de solicitudes',list(r['states'].items()))
 section('Solicitudes por producto/servicio',[[v['name'],f"{v['value']} · {v['percent']:.1f}%"] for v in r['products']])
 section('Clientes',[[label,value(r['clients'][key])] for key,label in [('atStart','Clientes registrados al inicio'),('new','Nuevos clientes'),('active','Clientes activos')]])
 section('Clientes por producto/servicio',[[v['name'],v['value']] for v in r['clientProducts']])
 section('Clientes con mayor actividad',[[v['name'],v['value']] for v in r['topClients'][:5]])
 section('Carga operativa',[[v['name'],f"{v['support']} solicitudes · {v['tasks']} tareas"] for v in r['team']])
 section('Disponibilidad al cierre disponible',list(r['availability'].items()))
 section('Atención requerida',[[v['text'],v['count']] for v in r['alerts']])
 story.append(p('Alcance y calidad de los datos','Heading2'));story.append(p(f"{r['imported']} solicitudes importadas con actividad en el período. Comparaciones no disponibles cuando falta cobertura del período anterior."))
 for note in r['notes']:story.extend([p(note),Spacer(1,7)])
 def footer(canvas,doc):canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#64748b'));canvas.drawString(42,25,'VitaDev · Análisis operativo');canvas.drawRightString(550,25,str(doc.page))
 SimpleDocTemplate(out,pagesize=A4,rightMargin=42,leftMargin=42,topMargin=38,bottomMargin=42,title='VitaDev · Reportes').build(story,onFirstPage=footer,onLaterPages=footer);return out.getvalue()
class Handler(leave.Handler):
 def do_GET(self):
  path=urlparse(self.path).path
  if path not in ['/api/reports','/api/reports/pdf']:return super().do_GET()
  try:
   self.guard()
   if not getattr(self,'principal',None) and self.headers.get('X-Nexo-View')!='admin':raise team.Validation({'_form':'Reportes corresponde a la vista administrativa local.'},403)
   q=parse_qs(urlparse(self.path).query);errors={}
   try:start=date.fromisoformat(q.get('start',[''])[0])
   except ValueError:errors['start']='Ingresá una fecha válida.'
   try:end=date.fromisoformat(q.get('end',[''])[0])
   except ValueError:errors['end']='Ingresá una fecha válida.'
   if not errors and (end<start or (end-start).days>3652):errors['end']='Elegí un período válido de hasta diez años.'
   if errors:raise team.Validation(errors)
   data=sources();ids={}
   for key,kind in [('client','clients'),('product','catalog')]:
    try:ids[key]=int(q[key][0]) if q.get(key) else None
    except ValueError:raise team.Validation({key:'Filtro no válido.'})
    if ids[key] and not any(r['id']==ids[key] for r in data[kind]):raise team.Validation({key:'Registro no encontrado.'})
   result=analyze(data,start,end,**ids)
   if path.endswith('/pdf'):
    raw=pdf_report(result);self.send_response(200);self.send_header('Content-Type','application/pdf');self.send_header('Content-Disposition','attachment; filename="VitaDev-Nexo-Reporte.pdf"');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
   else:self.send_json(200,result)
  except team.Validation as e:self.send_json(e.status,{'errors':e.fields})
  except Exception:self.send_json(500,{'errors':{'_form':'No se pudo generar el reporte. Volvé a intentar.'}})
if __name__=='__main__':
 team.init();desk.init();leave.init();port=int(team.os.environ.get('NEXO_PORT','4173'));server=team.ThreadingHTTPServer(('127.0.0.1',port),Handler);print(f'Nexo: http://127.0.0.1:{port}',flush=True);server.serve_forever()
