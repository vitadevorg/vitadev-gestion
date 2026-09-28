/* Ausencias: período aprobado determina disponibilidad; nunca el estado laboral. */
const lv = {
  loaded: false,
  role: null,
  error: '',
  items: [],
  events: [],
  types: [],
  today: '',
  view: 'calendar',
  month: new Date().getMonth(),
  year: new Date().getFullYear(),
  status: '',
  type: '',
  employee: '',
  filterYear: '',
  query: '',
  more: false,
  draft: null,
  errors: {},
  touched: new Set(),
  busy: false,
  detailId: null,
  comment: '',
  decision: null,
};
const lvDialog = document.createElement('dialog');
lvDialog.id = 'leave-dialog';
lvDialog.setAttribute('aria-labelledby', 'leave-title');
document.body.appendChild(lvDialog);
let lvFocus = null;
const lvPerson = (id) => employees.find((e) => e.id === Number(id));
const lvItem = (id) => lv.items.find((l) => l.id === Number(id));
const lvDay = (value) => new Date(value + 'T12:00:00');
const lvISO = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const lvDays = (a, b) =>
  /^\d{4}-\d{2}-\d{2}$/.test(a) && /^\d{4}-\d{2}-\d{2}$/.test(b) && b >= a
    ? Math.round((Date.parse(b + 'T12:00:00Z') - Date.parse(a + 'T12:00:00Z')) / 86400000) + 1
    : 0;
const lvBtn = (text, op, id = '', primary = false) =>
  `<button type="button" class="button ${primary ? 'primary' : ''}" data-lv="${op}" data-id="${id}" ${op === 'previous' ? 'aria-label="Mes anterior"' : op === 'next' ? 'aria-label="Mes siguiente"' : ''}>${text}</button>`;
const lvBadge = (s) => `<span class="lv-badge lv-${s.toLowerCase()}">${s}</span>`;
async function lvApi(path = '', data) {
  const response = await fetch('/api/absences' + path, {
    method: data === undefined ? 'GET' : 'POST',
    headers: {
      'X-Nexo-View': state.role,
      'X-Nexo-Employee': String(currentEmployeeId()),
      ...(data === undefined
        ? {}
        : { 'Content-Type': 'application/json', 'X-Nexo-Client': 'team' }),
    },
    body: data === undefined ? undefined : JSON.stringify(data),
    cache: 'no-store',
  });
  let result;
  try {
    result = await response.json();
  } catch {
    throw { errors: { _form: 'El servicio de Licencias no está disponible.' } };
  }
  if (!response.ok) {
    result.status = response.status;
    throw result;
  }
  return result;
}
let lvSequence = 0;
async function lvLoad(draw = true) {
  const sequence = ++lvSequence,
    role = state.role;
  try {
    // Ambas lecturas en paralelo: antes la segunda esperaba a que terminara la primera.
    const [available, data] = await Promise.all([
      lvApi('/availability'),
      ['admin', 'employee'].includes(role) ? lvApi() : { items: [], events: [], types: [] },
    ]);
    if (sequence !== lvSequence || role !== state.role) return;
    lv.today = available.today;
    team.today = available.today;
    lv.loadedAt = Date.now();
    lv.items = data.items;
    lv.events = data.events;
    lv.types = data.types;
    lv.role = role;
    lv.employeeContext = currentEmployeeId();
    lv.loaded = true;
    lv.error = '';
    const merged = new Map(
      available.periods.map((p) => [p.id, { ...p, type: 'Ausencia aprobada' }]),
    );
    for (const item of lv.items) merged.set(item.id, item);
    leaves.splice(0, leaves.length, ...merged.values());
  } catch (e) {
    lv.error = Object.values(e.errors || { _form: 'No se pudieron cargar las licencias.' }).join(
      ' ',
    );
  }
  document.dispatchEvent(new Event('nexo:data-changed'));
  if (draw) render();
}
function lvSummary() {
  const pending = lv.items.filter((l) => l.status === LEAVE.PENDING).length,
    today = new Set(
      lv.items
        .filter((l) => l.status === LEAVE.APPROVED && l.start <= lv.today && l.end >= lv.today)
        .map((l) => l.employee),
    ).size,
    next = lv.items.filter((l) => l.status === LEAVE.APPROVED && l.start > lv.today).length;
  return `<p class="lv-summary"><span><b>${pending}</b> ${pending === 1 ? 'pendiente' : 'pendientes'} de aprobación</span><span><b>${today}</b> ${today === 1 ? 'persona ausente hoy' : 'personas ausentes hoy'}</span><span><b>${next}</b> próximas ausencias</span></p>`;
}
function lvPending() {
  const items = lv.items.filter((l) => l.status === LEAVE.PENDING);
  return `<section class="lv-pending"><h2>Pendientes de aprobación</h2>${items.map((l) => `<div class="lv-pending-row"><div class="person">${personImage(lvPerson(l.employee))}<div><strong>${esc(lvPerson(l.employee)?.name)}</strong><small>${esc(l.type)}</small></div></div><p>${crDate(l.start)} → ${crDate(l.end)} · ${l.days} días</p><div class="lv-pending-actions">${lvBadge(l.status)}${lvBtn('Revisar', 'detail', l.id)}</div></div>`).join('') || '<p class="lv-empty">No hay licencias pendientes de aprobación.</p>'}</section>`;
}
function lvCalendar() {
  const first = new Date(lv.year, lv.month, 1, 12),
    offset = (first.getDay() + 6) % 7,
    start = new Date(lv.year, lv.month, 1 - offset, 12),
    count = Math.ceil((offset + new Date(lv.year, lv.month + 1, 0).getDate()) / 7),
    approved = lv.items.filter((l) => l.status === LEAVE.APPROVED);
  let weeks = '';
  for (let w = 0; w < count; w++) {
    const a = new Date(start);
    a.setDate(start.getDate() + w * 7);
    const b = new Date(a);
    b.setDate(a.getDate() + 6);
    const list = approved.filter((l) => l.start <= lvISO(b) && l.end >= lvISO(a));
    let cells = '';
    for (let i = 0; i < 7; i++) {
      const d = new Date(a);
      d.setDate(a.getDate() + i);
      cells += `<div class="lv-day ${d.getMonth() !== lv.month ? 'lv-outside' : ''}" style="grid-column:${i + 1};grid-row:1"><time datetime="${lvISO(d)}" ${lvISO(d) === lv.today ? 'aria-current="date"' : ''}>${d.getDate()}</time></div>`;
    }
    weeks += `<div class="lv-week">${cells}${list
      .map((l, i) => {
        const from = l.start < lvISO(a) ? 0 : lvDays(lvISO(a), l.start) - 1,
          to = l.end > lvISO(b) ? 6 : lvDays(lvISO(a), l.end) - 1;
        return `<button class="lv-period ${l.start < lvISO(a) ? 'lv-continues-left' : ''} ${l.end > lvISO(b) ? 'lv-continues-right' : ''}" style="grid-column:${from + 1}/${to + 2};grid-row:${i + 2}" data-lv="detail" data-id="${l.id}" aria-label="${esc(lvPerson(l.employee)?.name)} · ${esc(l.type)} · ${crDate(l.start)} al ${crDate(l.end)}">${personImage(lvPerson(l.employee))}<span><strong>${esc(lvPerson(l.employee)?.name)}</strong><small>${esc(l.type)}</small></span></button>`;
      })
      .join('')}</div>`;
  }
  return `<div class="lv-calendar-layout"><section class="lv-calendar"><div class="lv-month-head"><div>${lvBtn('←', 'previous')}<h2>${new Intl.DateTimeFormat('es-AR', { month: 'long', year: 'numeric' }).format(first)}</h2>${lvBtn('→', 'next')}</div>${lvBtn('Hoy', 'today')}</div><div class="lv-calendar-scroll"><div class="lv-month-grid"><div class="lv-weekdays">${['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'].map((d) => `<span>${d}</span>`).join('')}</div>${weeks}</div></div><p class="lv-calendar-note">${approved.some((l) => l.start <= lvISO(new Date(lv.year, lv.month + 1, 0, 12)) && l.end >= lvISO(first)) ? 'Solo ausencias aprobadas.' : 'No hay ausencias aprobadas en este mes.'} Los motivos y adjuntos se consultan en el detalle.</p></section>${state.role === 'admin' ? lvPending() : ''}</div>`;
}
function lvFilter(key, label, options) {
  return `<label>${label}<select data-lv-filter="${key}"><option value="">${label}</option>${options
    .map((v) => {
      const [id, text] = Array.isArray(v) ? v : [v, v];
      return `<option value="${esc(id)}" ${String(lv[key]) === String(id) ? 'selected' : ''}>${esc(text)}</option>`;
    })
    .join('')}</select></label>`;
}
function lvRequests() {
  const list = lv.items.filter(
    (l) =>
      (!lv.status || l.status === lv.status) &&
      (!lv.type || l.type === lv.type) &&
      (!lv.employee || l.employee === Number(lv.employee)) &&
      (!lv.filterYear ||
        (Number(l.start.slice(0, 4)) <= Number(lv.filterYear) &&
          Number(l.end.slice(0, 4)) >= Number(lv.filterYear))) &&
      [lvPerson(l.employee)?.name, lvPerson(l.employee)?.legajo]
        .join(' ')
        .toLowerCase()
        .includes(lv.query.toLowerCase()),
  );
  const years = new Set([Number(lv.today.slice(0, 4))]);
  for (const l of lv.items)
    for (let y = Number(l.start.slice(0, 4)); y <= Number(l.end.slice(0, 4)); y++) years.add(y);
  return `<div class="lv-filters"><label>Buscar empleado<input id="lv-search" type="search" value="${esc(lv.query)}" placeholder="Nombre o legajo"></label>${lvFilter('status', 'Todos los estados', [LEAVE.PENDING, LEAVE.APPROVED, LEAVE.REJECTED, LEAVE.CANCELLED])}<button class="button" data-lv="filters" aria-expanded="${lv.more}">Filtros${[lv.type, lv.employee, lv.filterYear].filter(Boolean).length ? ' · ' + [lv.type, lv.employee, lv.filterYear].filter(Boolean).length : ''}</button>${lvBtn('Limpiar', 'clear')}${
    lv.more
      ? `<div class="lv-extra-filters">${lvFilter(
          'type',
          'Todos los tipos',
          lv.types.map((t) => t.name),
        )}${
          state.role === 'admin'
            ? lvFilter(
                'employee',
                'Todos los empleados',
                employees.map((e) => [e.id, e.name]),
              )
            : ''
        }${lvFilter(
          'filterYear',
          'Todos los años',
          [...years].sort((a, b) => b - a),
        )}</div>`
      : ''
  }</div><p class="lv-count">${list.length} solicitudes</p><section class="panel table-panel">${crTable(
    ['Empleado', 'Tipo', 'Período', 'Días', 'Estado', 'Acción'],
    list.map(
      (l) =>
        `<tr><td><div class="person">${personImage(lvPerson(l.employee))}<div><strong>${esc(lvPerson(l.employee)?.name)}</strong><small>${esc(lvPerson(l.employee)?.legajo)}</small></div></div></td><td>${esc(l.type)}</td><td>${crDate(l.start)} – ${crDate(l.end)}</td><td>${l.days}</td><td>${lvBadge(l.status)}</td><td>${lvBtn(l.status === LEAVE.PENDING && state.role === 'admin' ? 'Revisar' : 'Ver', 'detail', l.id)}</td></tr>`,
    ),
  )}</section>`;
}
calendar = function () {
  if (state.role === 'client')
    return heading('Licencias', 'Esta vista corresponde al personal de VitaDev.');
  const head = heading(
    'Licencias',
    'Ausencias, solicitudes y disponibilidad del equipo.',
    lvBtn('+ Solicitar licencia', 'new', '', true),
  );
  if (!lv.loaded || lv.role !== state.role || lv.employeeContext !== currentEmployeeId())
    return `<div class="lv-module">${head}${lv.error ? visualState('error', lvBtn('Reintentar', 'retry')) : '<p role="status">Cargando licencias…</p>'}</div>`;
  return `<div class="lv-module">${head}${lvSummary()}<div class="lv-views" role="group" aria-label="Vista de Licencias"><button data-lv="calendar" aria-pressed="${lv.view === 'calendar'}">Calendario</button><button data-lv="requests" aria-pressed="${lv.view === 'requests'}">Solicitudes</button></div>${lv.view === 'calendar' ? lvCalendar() : lvRequests()}</div>`;
};
function lvOpen() {
  lvFocus = document.activeElement;
  lvDialog.showModal();
}
function lvClose() {
  if (lv.busy) return;
  lvDialog.close();
  lv.draft = null;
  lv.detailId = null;
  lv.decision = null;
  lvFocus?.focus();
}
function lvValidate() {
  if (!lv.draft) return {};
  const d = lv.draft,
    e = {};
  if (state.role === 'admin' && !d.employee) e.employee = 'Seleccioná un empleado.';
  if (!d.type) e.type = 'Seleccioná un tipo.';
  if (!d.start) e.start = 'Indicá la fecha inicial.';
  if (!d.end) e.end = 'Indicá la fecha final.';
  if (d.start && d.end && d.end < d.start)
    e.end = 'La fecha final no puede ser anterior a la inicial.';
  if (
    d.start &&
    d.end &&
    lv.items.some(
      (l) =>
        l.employee === Number(d.employee) &&
        [LEAVE.PENDING, LEAVE.APPROVED].includes(l.status) &&
        l.start <= d.end &&
        l.end >= d.start,
    )
  )
    e.end = 'El período se superpone con una licencia pendiente o aprobada.';
  if (lv.types.find((t) => t.name === d.type)?.reasonRequired && !d.reason.trim())
    e.reason = 'Indicá el motivo de la ausencia.';
  return { ...e, ...lv.errors };
}
function lvForm() {
  const d = lv.draft;
  lvDialog.className = 'lv-form-dialog';
  lvDialog.innerHTML = `<div class="lv-dialog-head"><div><h2 id="leave-title">Solicitar licencia</h2><p class="sub">${state.role === 'admin' ? 'Registro en nombre de un empleado.' : 'Tu solicitud se enviará a Administración.'}</p></div><button class="icon" data-lv="close" aria-label="Cerrar">×</button></div><form id="lv-form" novalidate><div class="lv-form-grid">${
    state.role === 'admin'
      ? `<label class="lv-field lv-full" for="lf-employee">Empleado *<select id="lf-employee" data-lv-field="employee" required aria-describedby="lf-employee-error"><option value="">Seleccionar empleado</option>${employees
          .filter((e) => e.laborStatus === LABOR.ACTIVE)
          .map(
            (e) =>
              `<option value="${e.id}" ${Number(d.employee) === e.id ? 'selected' : ''}>${esc(e.name)} · ${esc(e.legajo)}</option>`,
          )
          .join('')}</select><small id="lf-employee-error" class="field-error"></small></label>`
      : ''
  }<label class="lv-field lv-full" for="lf-type">Tipo de licencia *<select id="lf-type" data-lv-field="type" required aria-describedby="lf-type-error"><option value="">Seleccionar tipo</option>${lv.types.map((t) => `<option ${t.name === d.type ? 'selected' : ''}>${esc(t.name)}</option>`).join('')}</select><small id="lf-type-error" class="field-error"></small></label>${[
    ['start', 'Fecha desde'],
    ['end', 'Fecha hasta'],
  ]
    .map(
      ([k, label]) =>
        `<label class="lv-field" for="lf-${k}">${label} *<input id="lf-${k}" data-lv-field="${k}" type="date" value="${d[k]}" required aria-describedby="lf-${k}-error"><small id="lf-${k}-error" class="field-error"></small></label>`,
    )
    .join(
      '',
    )}<p class="lv-duration lv-full" id="lv-duration" role="status">${lvDays(d.start, d.end)} días corridos · incluye la fecha inicial y final</p><label class="lv-field lv-full" for="lf-reason"><span id="lv-reason-label">Motivo / comentario${lv.types.find((t) => t.name === d.type)?.reasonRequired ? ' *' : ' (opcional)'}</span><textarea id="lf-reason" data-lv-field="reason" rows="3" maxlength="3000" aria-describedby="lf-reason-error">${esc(d.reason)}</textarea><small id="lf-reason-error" class="field-error"></small></label><label class="lv-field lv-full" for="lf-attachment">Adjunto (opcional)<input id="lf-attachment" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp"><small>PDF o imagen de hasta 5 MB.</small><span id="lv-filename">${esc(d.attachmentName || '')}</span><small id="lf-attachment-error" class="field-error"></small></label>${d.attachment ? lvBtn('Quitar adjunto', 'remove-file') : ''}</div><p id="lv-form-error" class="field-error" role="alert"></p><div class="lv-dialog-actions">${lvBtn('Cancelar', 'close')}<button class="button primary" type="submit" id="lv-send">Enviar solicitud</button></div></form>`;
  lvErrors();
}
function lvErrors() {
  if (!lv.draft) return;
  const errors = lvValidate();
  for (const key of ['employee', 'type', 'start', 'end', 'reason', 'attachment']) {
    const el = document.getElementById('lf-' + key),
      msg = document.getElementById('lf-' + key + '-error');
    if (msg) msg.textContent = lv.touched.has(key) ? errors[key] || '' : '';
    el?.setAttribute('aria-invalid', String(lv.touched.has(key) && !!errors[key]));
  }
  $('#lv-send').disabled = lv.busy || Object.keys(errors).length > 0;
  $('#lv-send').textContent = lv.busy ? 'Enviando…' : 'Enviar solicitud';
  $('#lv-form-error').textContent = errors._form || '';
  $('#lv-duration').textContent =
    `${lvDays(lv.draft.start, lv.draft.end)} días corridos · incluye la fecha inicial y final`;
  $('#lv-reason-label').textContent =
    'Motivo / comentario' +
    (lv.types.find((t) => t.name === lv.draft.type)?.reasonRequired ? ' *' : ' (opcional)');
  $('#lf-reason').required = !!lv.types.find((t) => t.name === lv.draft.type)?.reasonRequired;
}
function lvDetail(id) {
  const l = lvItem(id);
  if (!l) return;
  lv.detailId = l.id;
  lv.comment = '';
  lv.decision = null;
  lv.draft = null;
  lvFocus = document.activeElement;
  lvDetailContent();
  if (!lvDialog.open) lvDialog.showModal();
}
function lvDetailContent() {
  const l = lvItem(lv.detailId);
  if (!l) return;
  const e = lvPerson(l.employee),
    admin = state.role === 'admin',
    overlap = lv.items.filter(
      (a) =>
        a.id !== l.id &&
        a.status === LEAVE.APPROVED &&
        a.start <= l.end &&
        a.end >= l.start &&
        lvPerson(a.employee)?.area === e?.area,
    ),
    tasks =
      typeof desk !== 'undefined' && desk.loaded
        ? desk.data.tasks.filter((t) => t.owner === l.employee && !t.done).length
        : null,
    requests =
      typeof desk !== 'undefined' && desk.loaded
        ? desk.data.requests.filter((r) => r.agentId === l.employee && hdOpen(r)).length
        : null,
    events = lv.events.filter((a) => a.absence_id === l.id);
  lvDialog.className = 'lv-detail-dialog';
  lvDialog.innerHTML = `<div class="lv-dialog-head"><h2 id="leave-title">Solicitud de licencia</h2><button class="icon" data-lv="close" aria-label="Cerrar">×</button></div><div class="lv-detail-person">${personImage(e)}<div><strong>${esc(e?.name)}</strong><small>${esc(e?.role)}</small></div>${lvBadge(l.status)}</div><h3>${esc(l.type)}</h3><p class="lv-detail-period">${crDate(l.start)} → ${crDate(l.end)} <span>${l.days} días</span></p><section class="lv-detail-section"><h3>Motivo / comentario</h3><p class="lv-private-text">${esc(l.reason) || 'Sin comentario.'}</p>${l.attachment ? `<p>${esc(l.attachmentName)} ${lvBtn('Ver adjunto', 'attachment', l.id)}</p>` : ''}</section>${admin ? `<section class="lv-detail-section"><h3>Impacto en el equipo</h3><p>${tasks === null ? 'Carga de tareas no disponible' : tasks + ' tareas activas'} · ${requests === null ? 'Carga de soporte no disponible' : requests + ' solicitudes de soporte asignadas'}</p>${overlap.length ? `<p class="sub">Otras ausencias de ${esc(e?.area)} en el período:</p><ul>${overlap.map((a) => `<li>${esc(lvPerson(a.employee)?.name)} · ${crDate(a.start)} → ${crDate(a.end)}</li>`).join('')}</ul>` : '<p class="sub">No hay otras ausencias aprobadas de la misma área durante el período.</p>'}</section>` : ''}${l.resolvedAt ? `<section class="lv-detail-section"><h3>Resolución</h3><p>${esc(l.resolvedBy)} · ${hdStamp(l.resolvedAt)}</p><p class="lv-private-text">${esc(l.resolutionComment) || 'Sin comentario de resolución.'}</p></section>` : ''}${(admin && l.status === LEAVE.PENDING) || ([LEAVE.PENDING, LEAVE.APPROVED].includes(l.status) && admin) || (l.status === LEAVE.PENDING && !admin) ? `<section class="lv-detail-section"><label class="lv-field" for="lv-comment">Comentario de resolución${!admin ? ' / cancelación' : ''}<textarea id="lv-comment" rows="2" maxlength="3000" aria-describedby="lv-comment-error">${esc(lv.comment)}</textarea><small id="lv-comment-error" class="field-error" role="alert"></small></label>${lv.decision ? `<div class="lv-decision-confirm"><p>¿Confirmás ${{ approve: 'aprobar', reject: 'rechazar', cancel: 'cancelar' }[lv.decision]} esta solicitud?</p><div class="lv-dialog-actions">${lvBtn('Volver', 'back-decision')}${lvBtn('Confirmar', 'confirm', '', true)}</div></div>` : `<div class="lv-dialog-actions">${l.status === LEAVE.PENDING && admin ? lvBtn('Rechazar', 'reject') + lvBtn('Aprobar', 'approve', '', true) : ''}${admin || l.status === LEAVE.PENDING ? lvBtn('Cancelar licencia', 'cancel') : ''}</div>`}</section>` : ''}<p id="lv-detail-error" class="field-error" role="alert"></p><details class="lv-audit"><summary>Historial · ${events.length} registros</summary>${events.map((a) => `<div><strong>${esc(a.action)}</strong><small>${hdStamp(a.created_at)} · ${esc(a.actor)}</small>${a.comment ? `<p>${esc(a.comment)}</p>` : ''}</div>`).join('')}</details>`;
}
const beforeLeaveAction = action;
action = function (value) {
  if (value === 'new-leave') {
    if (!lv.loaded || lv.role !== state.role || lv.employeeContext !== currentEmployeeId()) {
      toast('Esperá a que carguen las licencias.');
      return;
    }
    if (state.role === 'client') return;
    lv.draft = {
      employee: state.role === 'employee' ? currentEmployeeId() : '',
      type: '',
      start: '',
      end: '',
      reason: '',
      attachment: '',
    };
    lv.errors = {};
    lv.touched = new Set();
    lvForm();
    lvOpen();
    return;
  }
  beforeLeaveAction(value);
};
const beforeLeaveRender = render;
render = function () {
  beforeLeaveRender();
  if (state.page === 'calendar' && state.role !== 'client') {
    const description = $('#app .heading .sub');
    if (description)
      description.textContent = 'Ausencias, solicitudes y disponibilidad del equipo.';
    $('footer span').textContent = 'Licencias · Guardado persistente en este equipo';
  }
  if ((lv.role !== state.role || lv.employeeContext !== currentEmployeeId()) && !lv.busy) {
    lv.role = state.role;
    lv.employeeContext = currentEmployeeId();
    lv.loaded = false;
    lv.items = [];
    lv.events = [];
    lvDialog.close();
    lvLoad();
  }
};
function lvRead(el) {
  const key = el.dataset.lvField;
  if (!key || !lv.draft) return;
  lv.draft[key] = key === 'employee' ? (el.value ? Number(el.value) : '') : el.value;
  delete lv.errors[key];
  delete lv.errors._form;
  lv.touched.add(key);
  if (key === 'employee' || key === 'start') delete lv.errors.end;
  lvErrors();
}
document.addEventListener('input', (e) => {
  const el = e.target;
  if (el.id === 'lv-search') {
    const pos = el.selectionStart;
    lv.query = el.value;
    render();
    $('#lv-search').focus();
    $('#lv-search').setSelectionRange(pos, pos);
  }
  if (el.dataset.lvField) lvRead(el);
  if (el.id === 'lv-comment') {
    lv.comment = el.value;
    $('#lv-comment-error').textContent = '';
  }
});
document.addEventListener('change', async (e) => {
  const el = e.target;
  if (el.dataset.lvFilter) {
    lv[el.dataset.lvFilter] = el.value;
    render();
  }
  if (el.dataset.lvField) lvRead(el);
  if (el.id === 'lf-attachment' && el.files[0]) {
    const file = el.files[0];
    lv.busy = true;
    lvErrors();
    el.disabled = true;
    try {
      if (file.size > 5 * 1024 * 1024)
        throw { errors: { attachment: 'El adjunto debe pesar hasta 5 MB.' } };
      const base64 = await new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result.split(',')[1]);
        r.onerror = reject;
        r.readAsDataURL(file);
      });
      const result = await lvApi('/files', { name: file.name, base64 });
      lv.draft.attachment = result.id;
      lv.draft.attachmentName = result.name;
      delete lv.errors.attachment;
    } catch (err) {
      lv.errors.attachment = Object.values(
        err.errors || { attachment: 'No se pudo adjuntar el archivo.' },
      ).join(' ');
      lv.touched.add('attachment');
    }
    lv.busy = false;
    lvForm();
  }
});
document.addEventListener('submit', async (e) => {
  if (e.target.id !== 'lv-form') return;
  e.preventDefault();
  if (lv.busy || Object.keys(lvValidate()).length) return;
  const d = lv.draft,
    days = lvDays(d.start, d.end),
    admin = state.role === 'admin';
  const ok = await confirmAction({
    title: '¿Enviar la solicitud de licencia?',
    message: admin
      ? `Se registrará en nombre de ${lvPerson(d.employee)?.name || 'el empleado'}.`
      : 'Se enviará a Administración para su aprobación.',
    details: [
      ['Tipo', d.type],
      ['Período', crDate(d.start) + ' → ' + crDate(d.end)],
      ['Duración', days + (days === 1 ? ' día corrido' : ' días corridos')],
      ['Adjunto', d.attachmentName || ''],
    ],
    notes: [
      ...(d.start < lv.today ? ['La fecha de inicio ya pasó.'] : []),
      ...(days > 15 ? ['Es una licencia de más de 15 días.'] : []),
      'Quedará pendiente hasta que Administración la apruebe o rechace.',
    ],
    confirmLabel: 'Sí, enviar',
  });
  if (!ok) return;
  lv.busy = true;
  lvErrors();
  try {
    await lvApi('', lv.draft);
    lv.view = 'requests';
    await lvLoad(false);
    lv.busy = false;
    lvClose();
    render();
    notify('success', 'Solicitud de licencia enviada', 'Podés seguir su estado en Licencias.');
  } catch (err) {
    lv.busy = false;
    lv.errors = err.errors || { _form: 'No se pudo guardar. Tus datos se conservan.' };
    Object.keys(lv.errors).forEach((k) => lv.touched.add(k));
    lvErrors();
  }
});
document.addEventListener('click', async (e) => {
  const b = e.target.closest('[data-lv]');
  if (!b) return;
  e.preventDefault();
  if (lv.busy) return;
  const op = b.dataset.lv,
    id = Number(b.dataset.id);
  switch (op) {
    case 'new':
      action('new-leave');
      break;
    case 'close':
      lvClose();
      break;
    case 'retry':
      await lvLoad();
      break;
    case 'calendar':
      lv.view = 'calendar';
      render();
      break;
    case 'requests':
      lv.view = 'requests';
      render();
      break;
    case 'previous':
    case 'next': {
      const d = new Date(lv.year, lv.month + (op === 'next' ? 1 : -1), 1);
      lv.year = d.getFullYear();
      lv.month = d.getMonth();
      render();
      break;
    }
    case 'today': {
      const d = lvDay(lv.today);
      lv.year = d.getFullYear();
      lv.month = d.getMonth();
      render();
      break;
    }
    case 'filters':
      lv.more = !lv.more;
      render();
      break;
    case 'clear':
      lv.status = lv.type = lv.employee = lv.filterYear = lv.query = '';
      render();
      break;
    case 'detail':
      lvDetail(id);
      break;
    case 'remove-file':
      lv.draft.attachment = '';
      lv.draft.attachmentName = '';
      delete lv.errors.attachment;
      lvForm();
      break;
    case 'back-decision':
      lv.decision = null;
      lvDetailContent();
      break;
    case 'approve':
    case 'reject':
    case 'cancel':
      if (op === 'reject' && !lv.comment.trim()) {
        $('#lv-comment-error').textContent = 'Indicá el motivo del rechazo.';
        $('#lv-comment').focus();
        break;
      }
      lv.decision = op;
      lvDetailContent();
      break;
    case 'confirm': {
      lv.busy = true;
      b.disabled = true;
      const l = lvItem(lv.detailId);
      try {
        const decision = lv.decision;
        await lvApi('/' + l.id + '/' + lv.decision, {
          version: l.version,
          comment: lv.comment,
          confirm: true,
        });
        await lvLoad(false);
        lv.busy = false;
        lvClose();
        render();
        toast(
          decision === 'approve'
            ? 'Licencia aprobada.'
            : decision === 'reject'
              ? 'Licencia rechazada.'
              : 'Licencia cancelada.',
        );
      } catch (err) {
        lv.busy = false;
        if (err.status === 409) {
          await lvLoad(false);
          lv.decision = null;
          lvDetailContent();
        }
        $('#lv-detail-error').textContent = Object.values(
          err.errors || { _form: 'No se pudo actualizar.' },
        ).join(' ');
        b.disabled = false;
      }
      break;
    }
    case 'attachment': {
      try {
        const r = await fetch('/api/absences/' + id + '/attachment', {
          headers: { 'X-Nexo-View': state.role, 'X-Nexo-Employee': String(currentEmployeeId()) },
        });
        if (!r.ok) throw Error();
        const blob = await r.blob();
        lvViewFile(blob, lvItem(id).attachmentName || 'adjunto');
      } catch {
        $('#lv-detail-error').textContent = 'No se pudo abrir el adjunto.';
      }
      break;
    }
  }
});
document.addEventListener('focusout', (e) => {
  if (e.target.dataset.lvField && lv.draft) {
    lv.touched.add(e.target.dataset.lvField);
    lvErrors();
  }
});
lvDialog.addEventListener('cancel', (e) => {
  e.preventDefault();
  lvClose();
});
// Actualiza al volver a la ventana y al cambiar de día; no persiste disponibilidad derivada.
// Como máximo una vez por minuto: el foco también llega al iniciar sesión y al alternar ventanas.
window.addEventListener('focus', () => {
  if (!lv.busy && !lvDialog.open && Date.now() - (lv.loadedAt || 0) > 60000) lvLoad();
});
setInterval(() => {
  if (lvISO(new Date()) !== lv.today && !lv.busy && !lvDialog.open) lvLoad();
}, 60000);
// Contexto inicial: evita que el primer render lo tome como un cambio de rol y cargue dos veces.
lv.role = state.role;
lv.employeeContext = currentEmployeeId();
lvLoad();

const lvViewer = document.createElement('dialog');
lvViewer.id = 'lv-file-viewer';
lvViewer.setAttribute('aria-label', 'Adjunto de la licencia');
document.body.appendChild(lvViewer);
let lvFileURL = null;
function lvViewFile(blob, name) {
  if (lvFileURL) URL.revokeObjectURL(lvFileURL);
  lvFileURL = URL.createObjectURL(blob);
  lvViewer.innerHTML = `<div class="lv-dialog-head"><strong>${esc(name)}</strong><button class="button" id="lv-close-viewer">Cerrar</button></div>${blob.type.startsWith('image/') ? `<img src="${lvFileURL}" alt="Adjunto de la licencia">` : `<iframe title="Documento adjunto" src="${lvFileURL}"></iframe>`}<a class="link" href="${lvFileURL}" download="${esc(name)}">Descargar archivo</a>`;
  lvViewer.querySelector('#lv-close-viewer').onclick = () => lvViewer.close();
  lvViewer.showModal();
}
lvViewer.addEventListener('close', () => {
  if (lvFileURL) URL.revokeObjectURL(lvFileURL);
  lvFileURL = null;
  lvViewer.innerHTML = '';
});
document.addEventListener(
  'click',
  (event) => {
    const b = event.target.closest('[data-leave]');
    if (b && lv.loaded) {
      event.preventDefault();
      event.stopImmediatePropagation();
      lvDetail(Number(b.dataset.leave));
    }
  },
  true,
);
