/* Módulo Equipo: su estado, formularios y persistencia están aislados del resto de Nexo. */
const team = {
  loaded: false,
  error: '',
  catalog: {},
  roles: [],
  today: '',
  query: '',
  area: 'Todos',
  labor: 'Todos',
  availability: 'Todos',
  profileId: null,
  tab: 'Resumen',
  draft: null,
  step: 0,
  touched: new Set(),
  errors: {},
  saving: false,
  photoBusy: false,
  returnFocus: null,
};
const teamSteps = [
  'Datos personales',
  'Información laboral',
  'Contacto y habilidades',
  'Acceso a VitaDev',
];
const teamTabs = ['Resumen', 'Trabajo', 'Tareas', 'Capacitación', 'Licencias'];
const teamDialog = document.createElement('dialog');
teamDialog.id = 'team-dialog';
teamDialog.setAttribute('aria-labelledby', 'team-dialog-title');
document.body.appendChild(teamDialog);
const teamEsc = esc;
const teamEmployee = (id) => employees.find((e) => e.id === Number(id));
const teamTasks = (id) => desk.data.tasks.filter((t) => t.owner === Number(id));
const teamActiveTasks = (id) =>
  teamTasks(id).filter(
    (t) => !t.done && ![TASK.COMPLETED, TASK.CANCELLED, REQUEST.CLOSED].includes(t.status),
  );
const teamAvailability = (e) =>
  leaves.some(
    (l) =>
      l.employee === e.id &&
      l.status === LEAVE.APPROVED &&
      l.start <= team.today &&
      l.end >= team.today,
  )
    ? AVAILABILITY.ON_LEAVE
    : e.availability || AVAILABILITY.AVAILABLE;
const teamDate = (value) =>
  /^\d{4}-\d{2}-\d{2}$/.test(value || '')
    ? new Intl.DateTimeFormat('es-AR', { dateStyle: 'medium' }).format(
        new Date(value + 'T12:00:00'),
      )
    : value || 'Sin informar';
const teamEmpty = (text) => `<div class="team-empty">${esc(text)}</div>`;
async function teamApi(path = '', data, method = 'POST') {
  const response = await fetch('/api/team' + path, {
    method: data === undefined ? 'GET' : method,
    headers:
      data === undefined ? {} : { 'Content-Type': 'application/json', 'X-Nexo-Client': 'team' },
    body: data === undefined ? undefined : JSON.stringify(data),
    cache: 'no-store',
  });
  let result;
  try {
    result = await response.json();
  } catch {
    throw {
      errors: {
        _form: 'El servicio de Equipo no está disponible. Tus datos permanecen en el formulario.',
      },
    };
  }
  if (!response.ok) {
    result.status = response.status;
    throw result;
  }
  return result;
}
async function teamLoad() {
  team.error = '';
  try {
    const data = await teamApi();
    if (!Array.isArray(data.employees)) throw Error();
    employees.splice(0, employees.length, ...data.employees);
    team.catalog = data.catalog;
    team.roles = data.accessRoles;
    team.today = data.today;
    team.loaded = true;
  } catch {
    team.error =
      'No pudimos conectar con el servicio de Equipo. Revisá la conexión y volvé a intentar.';
  }
  document.dispatchEvent(new Event('nexo:data-changed'));
  render();
}
function teamActions(e) {
  return `<details class="team-menu"><summary aria-label="Acciones de ${esc(e.name)}">${ico('more')}</summary><div class="team-menu-items"><button data-team-profile="${e.id}">Ver perfil</button><button data-team-edit="${e.id}">Editar</button><button data-team-access="${e.id}">Gestionar acceso</button><button class="team-danger-text" data-team-deactivate="${e.id}" ${e.laborStatus === LABOR.INACTIVE ? 'disabled' : ''}>Desactivar</button></div></details>`;
}
paths.more = 'M5 12h.01 M12 12h.01 M19 12h.01';
const originalTeamPage = employeesPage;
employeesPage = function () {
  if (state.role !== 'admin') return originalTeamPage();
  if (!team.loaded)
    return (
      heading('Equipo', 'Administración laboral y operativa del personal.') +
      `<section class="panel">${team.error ? `${visualState('error', '<button class="button" data-team-retry>Reintentar</button>')}` : '<p role="status">Cargando el equipo…</p>'}</section>`
    );
  if (team.profileId) return teamProfile(team.profileId);
  const list = employees.filter(
    (e) =>
      [e.name, e.legajo, e.role, ...e.skills]
        .join(' ')
        .toLocaleLowerCase('es')
        .includes(team.query.toLocaleLowerCase('es')) &&
      (team.area === 'Todos' || e.area === team.area) &&
      (team.labor === 'Todos' || e.laborStatus === team.labor) &&
      (team.availability === 'Todos' || teamAvailability(e) === team.availability),
  );
  return (
    heading(
      'Equipo',
      'Situación laboral, disponibilidad y carga de trabajo.',
      `<button class="button primary" data-team-new>Nuevo empleado</button>`,
    ) +
    `<section class="team-filterbar" aria-label="Filtros del equipo"><label class="team-search">Buscar<input type="search" id="team-query" placeholder="Nombre, legajo, puesto o habilidad" value="${esc(team.query)}"></label>${teamFilter('Área', 'area', Object.keys(team.catalog))}${teamFilter('Estado laboral', 'labor', [LABOR.ACTIVE, LABOR.INACTIVE])}${teamFilter('Disponibilidad', 'availability', [AVAILABILITY.AVAILABLE, AVAILABILITY.BUSY, AVAILABILITY.ABSENT, AVAILABILITY.ON_LEAVE])}<button class="link" data-team-clear>Limpiar filtros</button></section><div class="team-list-meta"><span>${list.length} de ${employees.length} empleados</span><span>La carga corresponde a tareas activas</span></div><section class="panel table-panel team-table"><div class="table-wrap"><table><thead><tr><th>Empleado</th><th>Área</th><th>Estado laboral</th><th>Disponibilidad</th><th>Carga actual</th><th>Acciones</th></tr></thead><tbody>${list.map((e) => `<tr><td><div class="person">${personImage(e)}<div><button class="text-action" data-team-profile="${e.id}">${esc(e.name)}</button><small>${esc(e.role)}</small><small class="team-legajo">${esc(e.legajo)}</small></div></div></td><td>${esc(e.area)}</td><td>${uiBadge(e.laborStatus, e.laborStatus === LABOR.ACTIVE ? 'success' : 'neutral')}</td><td>${uiBadge(teamAvailability(e))}</td><td><button class="link team-load" data-team-tasks="${e.id}"><b>${teamActiveTasks(e.id).length}</b> tareas activas</button></td><td>${teamActions(e)}</td></tr>`).join('') || '<tr><td colspan="6">' + (employees.length ? visualState('results', '<button class="button" data-team-clear>Limpiar filtros</button>') : teamEmpty('No hay empleados registrados.')) + '</td></tr>'}</tbody></table></div></section>`
  );
};
function teamFilter(label, key, items) {
  return `<label>${label}<select data-team-filter="${key}">${['Todos', ...items].map((v) => `<option ${team[key] === v ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></label>`;
}
function teamInfo(label, value) {
  return `<div><dt>${label}</dt><dd>${esc(value || 'Sin informar')}</dd></div>`;
}
function teamTaskTable(e) {
  const list = teamTasks(e.id);
  return list.length
    ? `<div class="table-wrap"><table><thead><tr><th>Tarea</th><th>Estado</th><th>Prioridad</th><th>Proyecto</th><th>Fecha límite</th></tr></thead><tbody>${list
        .map((t) => {
          const request = tickets.find((s) => s.id === t.ticket),
            client = clients.find((c) => c.id === t.client);
          return `<tr><td class="wrap-cell">${esc(t.title)}${t.ticket ? `<small class="team-secondary">Solicitud #${t.ticket}</small>` : ''}</td><td>${uiBadge(t.done ? TASK.COMPLETED : t.status || TASK.PENDING)}</td><td>${uiBadge(t.priority || request?.priority || 'Sin prioridad')}</td><td>${esc(t.project || (request ? hdProduct(request) : '') || 'Actividad interna')}<small class="team-secondary">${esc(client?.name || '')}</small></td><td>${esc(teamDate(t.due))}</td></tr>`;
        })
        .join('')}</tbody></table></div>`
    : teamEmpty('Este empleado no tiene tareas registradas.');
}
function teamProfile(id) {
  const e = teamEmployee(id);
  if (!e) {
    team.profileId = null;
    return employeesPage();
  }
  const manager = teamEmployee(e.managerId);
  let content = '';
  if (team.tab === 'Resumen')
    content = `<div class="team-profile-columns"><section><h2>Información laboral</h2><dl class="team-info">${teamInfo('Legajo', e.legajo)}${teamInfo('Área', e.area)}${teamInfo('Puesto', e.role)}${teamInfo('Estado laboral', e.laborStatus)}</dl><h2>Contacto</h2><dl class="team-info">${teamInfo('Correo corporativo', e.email)}${teamInfo('Teléfono', e.phone)}</dl><h2>Datos personales</h2><dl class="team-info">${teamInfo('DNI', e.dni)}${teamInfo('Fecha de nacimiento', teamDate(e.birthDate))}</dl></section><section><h2>Carga actual</h2><p class="team-work-count">${teamActiveTasks(e.id).length}<span>tareas activas</span></p><button class="link" data-team-tab="Tareas">Consultar tareas →</button><div class="team-section-line"><h2>Habilidades</h2><div class="tags">${e.skills.map((s) => uiBadge(s)).join('') || '<span class="muted">Sin habilidades registradas.</span>'}</div></div></section></div>`;
  if (team.tab === 'Trabajo')
    content = `<h2>Relación laboral</h2><dl class="team-info team-info-wide">${teamInfo('Puesto', e.role)}${teamInfo('Área', e.area)}${teamInfo('Responsable directo', manager?.name)}${teamInfo('Modalidad', e.modality)}${teamInfo('Fecha de ingreso', teamDate(e.hireDate))}${teamInfo('Disponibilidad base', e.availability)}</dl>${teamAvailability(e) === AVAILABILITY.ON_LEAVE ? '<p class="notice">Una licencia aprobada vigente puede determinar la disponibilidad operativa. El estado laboral se conserva por separado.</p>' : ''}<div class="team-section-line"><h2>Trazabilidad</h2><p class="sub">Se conservan las altas, modificaciones y desactivaciones.</p><button class="button" data-team-audit="${e.id}">Consultar historial de cambios</button>${e.deactivationReason ? `<p>Motivo de desactivación: ${esc(e.deactivationReason)}</p>` : ''}</div>`;
  if (team.tab === 'Tareas')
    content = `<div class="section-title"><h2>Tareas del empleado</h2><span class="sub">${teamActiveTasks(e.id).length} activas · ${teamTasks(e.id).length} registradas</span></div>${teamTaskTable(e)}`;
  if (team.tab === 'Capacitación')
    content = `<h2>Capacitaciones en curso</h2>${teamTraining(e, TASK.IN_PROGRESS)}<div class="team-section-line"><h2>Capacitaciones realizadas</h2>${teamTraining(e, TASK.COMPLETED)}</div><div class="team-section-line"><h2>Certificaciones</h2>${e.certifications?.length ? e.certifications.map((c) => `<p>${esc(c.name)} · ${esc(teamDate(c.date))}</p>`).join('') : teamEmpty('No hay certificaciones registradas para este empleado.')}</div>`;
  if (team.tab === 'Licencias') {
    const list = leaves.filter((l) => l.employee === e.id);
    content = `<h2>Historial de licencias</h2><p class="sub team-spaced">Consulta de los registros del módulo Licencias.</p>${list.length ? `<div class="table-wrap"><table><thead><tr><th>Tipo</th><th>Desde</th><th>Hasta</th><th>Estado</th></tr></thead><tbody>${list.map((l) => `<tr><td>${esc(l.type)}</td><td>${esc(teamDate(l.start))}</td><td>${esc(teamDate(l.end))}</td><td>${uiBadge(l.status)}</td></tr>`).join('')}</tbody></table></div>` : teamEmpty('Sin licencias registradas.')}`;
  }
  return `<button class="link team-back" data-team-back>← Volver al equipo</button><div class="team-profile-heading">${personImage(e, 'large')}<div><div class="eyebrow">${esc(e.legajo)} / ${esc(e.area)}</div><h1>${esc(e.name)}</h1><p class="sub">${esc(e.role)}</p><div class="tags">${uiBadge(e.laborStatus, e.laborStatus === LABOR.ACTIVE ? 'success' : 'neutral')}${uiBadge(teamAvailability(e))}</div></div><div class="actions"><button class="button primary" data-team-edit="${e.id}">Editar empleado</button>${teamActions(e)}</div></div><div class="team-tabs" role="tablist" aria-label="Perfil del empleado">${teamTabs.map((t) => `<button role="tab" id="team-tab-${teamTabs.indexOf(t)}" aria-controls="team-profile-content" aria-selected="${team.tab === t}" tabindex="${team.tab === t ? 0 : -1}" data-team-tab="${t}">${t}</button>`).join('')}</div><section id="team-profile-content" class="team-profile-content" role="tabpanel" aria-labelledby="team-tab-${teamTabs.indexOf(team.tab)}">${content}</section>`;
}
function teamTraining(e, status) {
  const list = (e.training || []).filter((t) => t.status === status);
  return list.length
    ? list
        .map(
          (t) => `<div class="summary-row"><span>${esc(t.title)}</span>${uiBadge(t.status)}</div>`,
        )
        .join('')
    : teamEmpty(
        status === TASK.IN_PROGRESS
          ? 'Sin capacitaciones en curso registradas.'
          : 'Sin capacitaciones realizadas registradas.',
      );
}
function teamBlank() {
  return {
    firstName: '',
    lastName: '',
    dni: '',
    birthDate: '',
    legajo: '',
    area: '',
    role: '',
    managerId: null,
    hireDate: '',
    modality: '',
    laborStatus: LABOR.ACTIVE,
    availability: AVAILABILITY.AVAILABLE,
    email: '',
    phone: '',
    skills: [],
    photo: ASSETS.avatar,
    access: { enabled: false, role: 'Empleado' },
  };
}
function teamOpenForm(id) {
  const e = id ? teamEmployee(id) : null;
  team.draft = e ? structuredClone(e) : teamBlank();
  team.step = 0;
  team.touched = new Set();
  team.errors = {};
  team.saving = false;
  team.photoBusy = false;
  team.returnFocus = document.activeElement;
  teamRenderForm();
  teamDialog.showModal();
  teamDialog.querySelector('input')?.focus();
}
function teamField(label, key, type = 'text', required = false) {
  const d = team.draft;
  return `<label class="team-field" for="tf-${key}">${label}${required ? ' <span aria-hidden="true">*</span>' : ''}<input id="tf-${key}" name="${key}" type="${type}" value="${esc(d[key] || '')}" ${required ? 'required' : ''} ${key === 'email' ? 'autocomplete="email"' : ''} maxlength="${key === 'legajo' ? 30 : 180}" aria-describedby="err-${key}" data-team-field="${key}"><small id="err-${key}" class="field-error" aria-live="polite"></small></label>`;
}
function teamSelect(label, key, options, required = false) {
  const value = key === 'accessRole' ? team.draft.access.role : team.draft[key];
  return `<label class="team-field" for="tf-${key}">${label}${required ? ' <span aria-hidden="true">*</span>' : ''}<select id="tf-${key}" data-team-field="${key}" ${required ? 'required' : ''} aria-describedby="err-${key}">${options
    .map((o) => {
      const [v, l] = Array.isArray(o) ? o : [o, o];
      return `<option value="${esc(v ?? '')}" ${String(value ?? '') === String(v ?? '') ? 'selected' : ''}>${esc(l)}</option>`;
    })
    .join(
      '',
    )}</select><small id="err-${key}" class="field-error" aria-live="polite"></small></label>`;
}
function teamValidation() {
  const d = team.draft,
    err = {};
  if (!d) return err;
  for (const k of [
    'firstName',
    'lastName',
    'legajo',
    'area',
    'role',
    'hireDate',
    'modality',
    'laborStatus',
    'email',
  ])
    if (!String(d[k] || '').trim()) err[k] = 'Este campo es obligatorio.';
  if (d.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(d.email.trim()))
    err.email = 'Ingresá un correo válido.';
  if (d.legajo && !/^[A-Za-z0-9_-]{1,30}$/.test(d.legajo.trim()))
    err.legajo = 'Usá letras, números, guiones o guiones bajos.';
  for (const key of ['email', 'legajo'])
    if (
      d[key] &&
      employees.some(
        (e) => e.id !== d.id && String(e[key]).toLowerCase() === d[key].trim().toLowerCase(),
      )
    )
      err[key] =
        key === 'email'
          ? 'Este correo ya pertenece a otro empleado.'
          : 'Este legajo ya está registrado.';
  if (d.dni && !/^\d{7,9}$/.test(d.dni)) err.dni = 'Ingresá entre 7 y 9 dígitos, sin puntos.';
  if (d.birthDate && d.birthDate > team.today)
    err.birthDate = 'La fecha de nacimiento no puede ser futura.';
  if (d.birthDate && d.hireDate && d.birthDate >= d.hireDate)
    err.hireDate = 'El ingreso debe ser posterior al nacimiento.';
  if (d.area && !(team.catalog[d.area] || []).includes(d.role))
    err.role = 'Seleccioná un puesto del área elegida.';
  if (d.managerId === d.id && d.id)
    err.managerId = 'Un empleado no puede ser su propio responsable.';
  if (d.access.enabled && !team.roles.includes(d.access.role))
    err.accessRole = 'Seleccioná un rol de acceso.';
  if (
    d.id &&
    teamEmployee(d.id)?.laborStatus === LABOR.ACTIVE &&
    d.laborStatus === LABOR.INACTIVE &&
    !d.confirmInactive
  )
    err.confirmInactive = 'Confirmá la desactivación para guardar.';
  return { ...err, ...team.errors };
}
function teamUpdateErrors() {
  const errors = teamValidation();
  Object.keys(team.draft || {})
    .concat(['accessRole', 'skills', 'photo', 'confirmInactive'])
    .forEach((key) => {
      const el = teamDialog.querySelector('#err-' + key),
        input = teamDialog.querySelector('#tf-' + key);
      if (el) el.textContent = team.touched.has(key) ? errors[key] || '' : '';
      if (input) input.setAttribute('aria-invalid', String(!!errors[key] && team.touched.has(key)));
    });
  const save = teamDialog.querySelector('[data-team-save]');
  if (save) save.disabled = Object.keys(errors).length > 0 || team.saving || team.photoBusy;
  const layout = teamDialog.querySelector('.team-editor-layout');
  if (layout) layout.inert = team.saving;
  const summary = teamDialog.querySelector('#team-save-hint');
  if (summary)
    summary.textContent = team.saving
      ? 'Guardando empleado…'
      : team.photoBusy
        ? 'Cargando fotografía…'
        : Object.keys(errors).filter((k) => k !== '_form').length
          ? 'Completá los campos obligatorios de todas las secciones para guardar.'
          : 'Datos listos para guardar.';
  const alert = teamDialog.querySelector('#team-form-error');
  if (alert) alert.textContent = errors._form || '';
}
function teamRenderForm() {
  const d = team.draft;
  teamDialog.className = 'team-editor';
  let body = '';
  if (team.step === 0)
    body = `<h3>Datos personales</h3><div class="team-photo-field">${personImage({ name: (d.firstName + ' ' + d.lastName).trim() || 'Nuevo empleado', photo: d.photo }, 'large')}<div><label class="button" for="team-photo">Seleccionar foto</label><input class="team-file" type="file" id="team-photo" accept="image/png,image/jpeg,image/webp"><p class="sub">PNG, JPEG o WebP · hasta 3 MB.</p><button type="button" class="link" data-team-remove-photo>Usar avatar genérico</button><small id="err-photo" class="field-error" aria-live="polite"></small></div></div><div class="team-form-grid">${teamField('Nombre', 'firstName', 'text', true)}${teamField('Apellido', 'lastName', 'text', true)}${teamField('DNI', 'dni')}${teamField('Fecha de nacimiento', 'birthDate', 'date')}</div>`;
  if (team.step === 1)
    body = `<h3>Información laboral</h3><div class="team-form-grid">${teamField('Legajo', 'legajo', 'text', true)}${teamSelect('Área', 'area', [['', 'Seleccionar área'], ...Object.keys(team.catalog)], true)}${teamSelect('Puesto', 'role', [['', 'Seleccionar puesto'], ...(team.catalog[d.area] || [])], true)}${teamSelect('Responsable directo', 'managerId', [['', 'Sin responsable'], ...employees.filter((e) => e.id !== d.id && e.laborStatus === LABOR.ACTIVE).map((e) => [e.id, e.name])])}${teamField('Fecha de ingreso', 'hireDate', 'date', true)}${teamSelect('Modalidad de trabajo', 'modality', [['', 'Seleccionar modalidad'], 'Remoto', 'Híbrido', 'Presencial'], true)}${teamSelect('Estado laboral', 'laborStatus', [LABOR.ACTIVE, LABOR.INACTIVE], true)}${teamSelect('Disponibilidad base', 'availability', [AVAILABILITY.AVAILABLE, AVAILABILITY.BUSY, AVAILABILITY.ABSENT, AVAILABILITY.ON_LEAVE])}</div><p class="sub">La disponibilidad operativa se ajusta si hay una licencia aprobada vigente.</p>`;
  if (team.step === 2)
    body = `<h3>Contacto</h3><div class="team-form-grid">${teamField('Correo corporativo', 'email', 'email', true)}${teamField('Teléfono', 'phone', 'tel')}</div><div class="team-section-line"><h3>Habilidades</h3><label class="team-field" for="team-skill">Agregar habilidad<div class="team-skill-input"><input id="team-skill" maxlength="40" placeholder="Por ejemplo: .NET, soporte, liderazgo"><button type="button" class="button" data-team-add-skill>Agregar</button></div></label><div class="team-chips">${d.skills.map((s, i) => `<span>${esc(s)}<button type="button" data-team-remove-skill="${i}" aria-label="Quitar ${esc(s)}">×</button></span>`).join('')}</div><small id="err-skills" class="field-error"></small></div>`;
  if (team.step === 3)
    body =
      '<h3>Acceso a VitaDev</h3><p>Después de guardar al empleado, abrí su perfil y elegí Crear acceso. La cuenta se administra separadamente de los datos laborales.</p>';
  teamDialog.innerHTML = `<div class="team-dialog-head"><div><p class="eyebrow">EQUIPO / ${d.id ? 'EDICIÓN' : 'ALTA'}</p><h2 id="team-dialog-title">${d.id ? 'Editar empleado' : 'Nuevo empleado'}</h2></div><button type="button" class="icon" data-team-close aria-label="Cerrar formulario">×</button></div><form id="team-form" novalidate><div class="team-editor-layout"><nav class="team-form-steps" aria-label="Secciones del formulario">${teamSteps.map((s, i) => `<button type="button" data-team-step="${i}" ${team.step === i ? 'aria-current="step"' : ''}><span>${i + 1}</span>${s}</button>`).join('')}</nav><div class="team-form-content"><p class="team-required">Los campos con * son obligatorios.</p>${body}<p id="team-form-error" class="field-error" role="alert"></p></div></div><div class="team-dialog-footer"><span id="team-save-hint" role="status"></span><div class="actions"><button type="button" class="button" data-team-close>Cancelar</button>${team.step < 3 ? `<button type="button" class="button" data-team-step="${team.step + 1}">Siguiente sección</button>` : ''}<button type="submit" class="button primary" data-team-save>Guardar empleado</button></div></div></form>`;
  if (
    team.step === 1 &&
    d.id &&
    teamEmployee(d.id)?.laborStatus === LABOR.ACTIVE &&
    d.laborStatus === LABOR.INACTIVE
  ) {
    teamDialog
      .querySelector('.team-form-content')
      .insertAdjacentHTML(
        'beforeend',
        `<label class="team-check"><input id="tf-confirmInactive" type="checkbox" data-team-field="confirmInactive" ${d.confirmInactive ? 'checked' : ''}>Confirmo desactivar al empleado, conservar su historial y deshabilitar su configuración de acceso.</label><small id="err-confirmInactive" class="field-error"></small>`,
      );
  }
  teamUpdateErrors();
}
function teamClose() {
  if (team.saving || team.photoBusy) return;
  teamDialog.close();
  team.draft = null;
  teamDialog.innerHTML = '';
  if (team.returnFocus?.isConnected) team.returnFocus.focus();
}
const TEAM_FIELD_LABELS = {
  firstName: 'Nombre',
  lastName: 'Apellido',
  dni: 'DNI',
  legajo: 'Legajo',
  email: 'Correo corporativo',
  phone: 'Teléfono',
  birthDate: 'Fecha de nacimiento',
  hireDate: 'Fecha de ingreso',
  area: 'Área',
  role: 'Puesto',
  managerId: 'Responsable directo',
  modality: 'Modalidad de trabajo',
  laborStatus: 'Estado laboral',
  availability: 'Disponibilidad base',
  photo: 'Fotografía',
  skills: 'Habilidades',
};
// Advertencia previa al guardado: resumen del alta o lista de campos modificados.
function teamConfirmSave(draft) {
  const name = (draft.firstName + ' ' + draft.lastName).trim();
  if (!draft.id)
    return confirmAction({
      title: `¿Dar de alta a ${name}?`,
      message: 'Revisá los datos principales antes de crear el legajo.',
      details: [
        ['Legajo', draft.legajo],
        ['Área', draft.area],
        ['Puesto', draft.role],
        ['Ingreso', teamDate(draft.hireDate)],
        ['Correo', draft.email],
      ],
      notes: [
        'El alta no crea una cuenta de acceso: se gestiona desde Usuarios y permisos.',
        ...(draft.managerId ? [] : ['No tiene responsable directo asignado.']),
      ],
      confirmLabel: 'Sí, dar de alta',
    });
  const original = teamEmployee(draft.id) || {};
  const changed = Object.keys(TEAM_FIELD_LABELS).filter(
    (k) => JSON.stringify(draft[k] ?? '') !== JSON.stringify(original[k] ?? ''),
  );
  if (!changed.length) return Promise.resolve(true);
  return confirmAction({
    title: '¿Guardar los cambios?',
    message: `Se actualizará la ficha de ${name}.`,
    details: [['Campos modificados', changed.map((k) => TEAM_FIELD_LABELS[k]).join(', ')]],
    notes:
      draft.laborStatus !== original.laborStatus && draft.laborStatus === LABOR.INACTIVE
        ? ['El estado laboral pasa a Inactivo: su acceso a VitaDev quedará deshabilitado.']
        : [],
    confirmLabel: 'Sí, guardar',
  });
}
async function teamSave() {
  if (Object.keys(teamValidation()).length || team.saving || team.photoBusy) return;
  if (!(await teamConfirmSave(team.draft))) return;
  team.saving = true;
  teamUpdateErrors();
  const draft = structuredClone(team.draft);
  try {
    const { employee } = await teamApi(
      draft.id ? '/' + draft.id : '',
      draft,
      draft.id ? 'PUT' : 'POST',
    );
    const i = employees.findIndex((e) => e.id === employee.id);
    if (i >= 0) employees[i] = employee;
    else employees.push(employee);
    team.saving = false;
    teamClose();
    team.profileId = null;
    render();
    if (draft.id) toast('Cambios guardados en la ficha de ' + employee.name + '.');
    else celebrate('¡Empleado dado de alta!', `${employee.name} ya forma parte del equipo.`);
  } catch (error) {
    if (error.status === 409) await teamLoad();
    team.errors = error.errors || { _form: 'No se pudo guardar. Tus datos se conservaron.' };
    Object.keys(team.errors).forEach((k) => team.touched.add(k));
    team.saving = false;
    teamUpdateErrors();
  }
}
function teamOpenProfile(id, tab = 'Resumen') {
  team.profileId = Number(id);
  team.tab = tab;
  state.page = 'employees';
  $('#modal').close();
  render();
  window.scrollTo({ top: 0, behavior: 'instant' });
}
const oldEmployeeDetail = employeeDetail;
employeeDetail = function (id) {
  if (state.role === 'admin' && team.loaded) teamOpenProfile(id);
  else oldEmployeeDetail(id);
};
const beforeTeamAction = action;
action = function (value) {
  if (value === 'new-employee' && state.role === 'admin') {
    if (team.loaded) teamOpenForm();
    else toast('Esperá a que cargue Equipo.');
    return;
  }
  beforeTeamAction(value);
};
function teamSmallDialog(title, html) {
  team.returnFocus = document.activeElement;
  teamDialog.className = 'team-small-dialog';
  teamDialog.innerHTML = `<div class="team-dialog-head"><h2 id="team-dialog-title">${title}</h2><button class="icon" data-team-close aria-label="Cerrar">×</button></div>${html}`;
  teamDialog.showModal();
}
function teamDeactivate(id) {
  const e = teamEmployee(id);
  if (!e || e.laborStatus === LABOR.INACTIVE) return;
  teamSmallDialog(
    'Desactivar empleado',
    `<p>¿Querés desactivar a <strong>${esc(e.name)}</strong>?</p><p class="sub">Se conservarán su historial y asignaciones. Su configuración de acceso quedará deshabilitada.</p>${teamActiveTasks(id).length ? `<p class="notice">Tiene ${teamActiveTasks(id).length} tareas activas. La desactivación no las reasigna.</p>` : ''}<form id="team-deactivate-form" data-id="${id}" novalidate><label class="team-field" for="team-reason">Motivo *<textarea id="team-reason" required maxlength="500" aria-describedby="team-deactivate-error"></textarea><small class="field-error" id="team-deactivate-error" role="alert"></small></label><div class="form-actions"><button class="button" type="button" data-team-close>Cancelar</button><button class="button danger" type="submit" disabled>Desactivar empleado</button></div></form>`,
  );
}
function teamAccess(id) {
  toast('Cargando gestión de acceso…');
}
async function teamAudit(id) {
  teamSmallDialog(
    'Historial de cambios',
    '<div id="team-audit-content" role="status">Cargando historial…</div>',
  );
  try {
    const result = await teamApi('/' + id + '/audit');
    const el = teamDialog.querySelector('#team-audit-content');
    if (el)
      el.innerHTML =
        result.events
          .map(
            (e) =>
              `<div class="team-audit-row"><strong>${esc(e.action)}</strong><small>${esc(new Date(e.created_at).toLocaleString('es-AR'))}</small><p class="sub">${esc(e.actor)}</p></div>`,
          )
          .join('') || teamEmpty('No hay cambios registrados.');
  } catch {
    const el = teamDialog.querySelector('#team-audit-content');
    if (el) el.textContent = 'No se pudo cargar el historial. Cerrá y volvé a intentar.';
  }
}
function teamReadField(input) {
  const k = input.dataset.teamField;
  if (!team.draft || !k) return;
  delete team.errors[k];
  delete team.errors._form;
  team.touched.add(k);
  if (k === 'confirmInactive') team.draft.confirmInactive = input.checked;
  else if (k === 'accessEnabled') team.draft.access.enabled = input.checked;
  else if (k === 'accessRole') team.draft.access.role = input.value;
  else if (k === 'managerId') team.draft.managerId = input.value ? Number(input.value) : null;
  else team.draft[k] = input.value;
  if (k === 'area') {
    team.draft.role = '';
    team.touched.delete('role');
    teamRenderForm();
  }
  if (k === 'laborStatus') {
    if (input.value === LABOR.INACTIVE) team.draft.access.enabled = false;
    teamRenderForm();
  }
  if (k === 'accessEnabled') {
    const select = teamDialog.querySelector('#tf-accessRole');
    if (select) select.disabled = !input.checked;
  }
  teamUpdateErrors();
}
function teamAddSkill() {
  const el = teamDialog.querySelector('#team-skill'),
    value = el.value.trim();
  if (!value) return;
  if (team.draft.skills.length >= 25) {
    team.errors.skills = 'Podés agregar hasta 25 habilidades.';
    team.touched.add('skills');
    teamUpdateErrors();
    return;
  }
  if (!team.draft.skills.some((s) => s.toLowerCase() === value.toLowerCase()))
    team.draft.skills.push(value);
  delete team.errors.skills;
  teamRenderForm();
  teamDialog.querySelector('#team-skill').focus();
}
document.addEventListener('click', (event) => {
  if (state.role !== 'admin') return;
  let b;
  if (event.target.closest('[data-team-new]')) teamOpenForm();
  if (event.target.closest('[data-team-retry]')) teamLoad();
  if (event.target.closest('[data-team-back]')) {
    team.profileId = null;
    render();
  }
  if (event.target.closest('[data-team-clear]')) {
    team.query = '';
    team.area = team.labor = team.availability = 'Todos';
    render();
  }
  for (const [key, fn] of [
    ['teamProfile', teamOpenProfile],
    ['teamEdit', teamOpenForm],
    ['teamAccess', teamAccess],
    ['teamDeactivate', teamDeactivate],
    ['teamAudit', teamAudit],
  ]) {
    b = event.target.closest('[data-' + key.replace(/[A-Z]/g, (m) => '-' + m.toLowerCase()) + ']');
    if (b) fn(Number(b.dataset[key]));
  }
  b = event.target.closest('[data-team-tasks]');
  if (b) teamOpenProfile(b.dataset.teamTasks, 'Tareas');
  b = event.target.closest('[data-team-tab]');
  if (b) {
    team.tab = b.dataset.teamTab;
    render();
    document.querySelector('[role="tab"][aria-selected="true"]')?.focus();
  }
  b = event.target.closest('[data-team-step]');
  if (b && !team.saving && !team.photoBusy) {
    team.step = Number(b.dataset.teamStep);
    teamRenderForm();
  }
  if (event.target.closest('[data-team-close]')) teamClose();
  if (event.target.closest('[data-team-add-skill]')) teamAddSkill();
  b = event.target.closest('[data-team-remove-skill]');
  if (b) {
    team.draft.skills.splice(Number(b.dataset.teamRemoveSkill), 1);
    delete team.errors.skills;
    teamRenderForm();
  }
  if (event.target.closest('[data-team-remove-photo]') && !team.photoBusy) {
    team.draft.photo = ASSETS.avatar;
    delete team.errors.photo;
    teamRenderForm();
  }
  document.querySelectorAll('.team-menu[open]').forEach((menu) => {
    if (!menu.contains(event.target)) menu.removeAttribute('open');
  });
});
document.addEventListener('input', (event) => {
  const el = event.target;
  if (el.id === 'team-query') {
    const pos = el.selectionStart;
    team.query = el.value;
    render();
    const next = $('#team-query');
    next.focus();
    next.setSelectionRange(pos, pos);
  }
  if (el.dataset.teamField && el.tagName === 'INPUT' && el.type !== 'checkbox') teamReadField(el);
  if (el.id === 'team-reason')
    teamDialog.querySelector('[type="submit"]').disabled = !el.value.trim();
});
document.addEventListener('change', async (event) => {
  const el = event.target;
  if (el.dataset.teamFilter) {
    team[el.dataset.teamFilter] = el.value;
    render();
  }
  if (el.dataset.teamField) teamReadField(el);
  if (el.id === 'team-photo') {
    const file = el.files[0];
    if (!file) return;
    team.touched.add('photo');
    if (
      file.size > 3 * 1024 * 1024 ||
      !['image/png', 'image/jpeg', 'image/webp'].includes(file.type)
    ) {
      team.errors.photo = 'Elegí PNG, JPEG o WebP de hasta 3 MB.';
      teamUpdateErrors();
      return;
    }
    team.photoBusy = true;
    teamUpdateErrors();
    try {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
      const result = await teamApi('/photos', { base64: data });
      team.draft.photo = result.photo;
      delete team.errors.photo;
    } catch (error) {
      team.errors.photo = error.errors?.photo || 'No se pudo cargar la foto. Volvé a intentar.';
    }
    team.photoBusy = false;
    teamRenderForm();
  }
});
document.addEventListener('submit', async (event) => {
  if (!['team-form', 'team-deactivate-form'].includes(event.target.id)) return;
  event.preventDefault();
  if (event.target.id === 'team-form') {
    await teamSave();
    return;
  }
  if (team.saving) return;
  const form = event.target,
    id = Number(form.dataset.id),
    employee = teamEmployee(id),
    errorEl = teamDialog.querySelector('#team-deactivate-error');
  team.saving = true;
  form.querySelector('[type="submit"]').disabled = true;
  try {
    const result = await teamApi('/' + id + '/deactivate', {
      version: employee.version,
      reason: teamDialog.querySelector('#team-reason').value,
    });
    employees[employees.findIndex((e) => e.id === id)] = result.employee;
    team.saving = false;
    teamClose();
    render();
    toast('Empleado desactivado. Su historial se conserva.');
  } catch (error) {
    team.saving = false;
    errorEl.textContent = Object.values(
      error.errors || { _form: 'No se pudo guardar. Volvé a intentar.' },
    ).join(' ');
    form.querySelector('[type="submit"]').disabled = false;
  }
});
document.addEventListener('keydown', (event) => {
  if (event.target.id === 'team-skill' && event.key === 'Enter') {
    event.preventDefault();
    teamAddSkill();
  }
  if (
    event.target.matches('.team-tabs [role="tab"]') &&
    ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)
  ) {
    event.preventDefault();
    let i = teamTabs.indexOf(team.tab);
    i =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? 4
          : (i + (event.key === 'ArrowRight' ? 1 : 4)) % 5;
    team.tab = teamTabs[i];
    render();
    document.querySelector('[role="tab"][aria-selected="true"]')?.focus();
  }
  if (event.key === 'Escape')
    document.querySelectorAll('.team-menu[open]').forEach((m) => m.removeAttribute('open'));
});
teamDialog.addEventListener('cancel', (event) => {
  event.preventDefault();
  teamClose();
});
const teamOriginalFooter = $('footer span').textContent;
const beforeTeamRender = render;
render = function () {
  beforeTeamRender();
  $('footer span').textContent =
    state.page === 'employees' && state.role === 'admin'
      ? 'Equipo · Guardado persistente en este equipo'
      : teamOriginalFooter;
};
document.addEventListener(
  'toggle',
  (event) => {
    const menu = event.target;
    if (!menu.matches?.('.team-menu') || !menu.open) return;
    document.querySelectorAll('.team-menu[open]').forEach((other) => {
      if (other !== menu) other.open = false;
    });
    const panel = menu.querySelector('.team-menu-items'),
      rect = menu.getBoundingClientRect();
    panel.style.left =
      Math.max(
        8,
        Math.min(rect.right - panel.offsetWidth, window.innerWidth - panel.offsetWidth - 8),
      ) + 'px';
    panel.style.top =
      Math.max(8, Math.min(rect.bottom + 5, window.innerHeight - panel.offsetHeight - 8)) + 'px';
  },
  true,
);
teamLoad();

document.addEventListener('focusout', (event) => {
  if (event.target.dataset.teamField && team.draft) {
    team.touched.add(event.target.dataset.teamField);
    teamUpdateErrors();
  }
});
