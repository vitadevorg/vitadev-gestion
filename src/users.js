const access = {
  users: [],
  loaded: false,
  error: '',
  tab: 'users',
  query: '',
  policy: null,
  draft: null,
  busy: false,
};
async function accessLoad(draw = true) {
  if (!can('users.view')) return;
  try {
    const [data, policy] = await Promise.all([
      authRequest('/api/users'),
      authRequest('/api/users/policy'),
    ]);
    access.users = data.users;
    access.policy = policy;
    access.loaded = true;
    access.error = '';
  } catch {
    access.error = 'No pudimos cargar los usuarios. Intentá nuevamente.';
  }
  if (draw) render();
}
const accessName = (u) => u.employee?.name || u.email;
const accessStatus = (u) =>
  uiBadge(
    u.status === 'ACTIVE' ? 'Activo' : 'Desactivado',
    u.status === 'ACTIVE' ? 'success' : 'neutral',
  );
const accessLast = (u) =>
  u.lastLoginAt ? new Date(u.lastLoginAt).toLocaleString('es-AR') : 'Sin accesos registrados';
usersPage = function () {
  if (!can('users.view'))
    return heading('Acceso restringido', 'No tenés permisos para acceder a esta sección.');
  let body;
  if (access.error)
    body = `${visualState('error', '<button class="button" data-access="retry">Reintentar</button>')}`;
  else if (!access.loaded) body = '<p role="status">Cargando usuarios…</p>';
  else if (access.tab === 'roles')
    body = `<section class="panel"><p>Los perfiles definen acciones concretas. El área laboral no concede permisos.</p>${Object.entries(
      access.policy.profiles,
    )
      .map(
        ([key, permissions]) =>
          `<details><summary><strong>${esc(access.policy.profileLabels[key])}</strong> · ${permissions.length} permisos</summary><ul>${permissions.map((p) => `<li>${esc(p)}</li>`).join('')}</ul></details>`,
      )
      .join('')}</section>`;
  else {
    const users = access.users.filter((u) =>
      `${accessName(u)} ${u.email}`.toLowerCase().includes(access.query.toLowerCase()),
    );
    body = `<div class="users-toolbar"><input id="users-search" type="search" aria-label="Buscar usuario" placeholder="Buscar nombre o correo" value="${esc(access.query)}"></div><section class="panel users-table">${
      users.length
        ? crTable(
            ['Usuario', 'Tipo', 'Área / relación', 'Rol', 'Estado', 'Último acceso', 'Acciones'],
            users.map(
              (u) =>
                `<tr><td><div class="person">${personImage(u.employee)}<div><strong>${esc(accessName(u))}</strong><small>${esc(u.email)}</small></div></div></td><td>Interno</td><td>${esc(u.employee?.area || 'Sin empleado vinculado')}</td><td>${u.role === 'ADMIN' ? 'Administrador' : 'Empleado'}</td><td>${accessStatus(u)}</td><td>${esc(accessLast(u))}</td><td><button class="button" data-access="detail" data-id="${u.id}">Ver</button>${can('users.manage') ? `<button class="button" data-access="edit" data-id="${u.id}">Gestionar acceso</button><button class="link" data-access="toggle" data-id="${u.id}">${u.status === 'ACTIVE' ? 'Desactivar' : 'Reactivar'}</button>` : ''}</td></tr>`,
            ),
          )
        : `${access.users.length ? visualState('results') : '<p role="status">No hay usuarios registrados.</p>'}`
    }</section>`;
  }
  return (
    heading('Usuarios y permisos', 'Cuentas de acceso vinculadas a las personas de VitaDev.') +
    `<div class="users-tabs"><button class="button" data-access="users" aria-pressed="${access.tab === 'users'}">Usuarios</button><button class="button" data-access="roles" aria-pressed="${access.tab === 'roles'}">Roles y permisos</button></div>${body}`
  );
};
function accessSection(employee) {
  const user = access.users.find((u) => u.employeeId === employee.id);
  return `<section class="access-summary"><h2>Acceso a VitaDev</h2>${!access.loaded ? '<p>Cargando acceso…</p>' : user ? `${accessStatus(user)}<p>${esc(user.email)}</p><p>${user.role === 'ADMIN' ? 'Administrador' : 'Empleado'} · ${esc(access.policy.profileLabels[user.permissionProfile])}</p><p class="sub">Último acceso: ${esc(accessLast(user))}</p>` : '<p>Este empleado todavía no posee acceso a VitaDev.</p>'}${can('users.manage') ? `<button class="button" data-access="employee" data-id="${employee.id}" ${employee.laborStatus !== LABOR.ACTIVE && !user ? 'disabled' : ''}>${user ? 'Gestionar acceso' : 'Crear acceso'}</button>` : ''}</section>`;
}
function accessEditor(user, employee) {
  if (!can('users.manage')) return;
  access.draft = user
    ? {
        id: user.id,
        email: user.email,
        role: user.role,
        status: user.status,
        permissionProfile: user.permissionProfile,
        employeeId: user.employeeId,
        password: '',
      }
    : {
        email: employee.email,
        role: 'EMPLOYEE',
        status: 'ACTIVE',
        permissionProfile: employee.area === 'Soporte' ? 'SUPPORT' : 'EMPLOYEE',
        employeeId: employee.id,
        password: '',
      };
  const d = access.draft;
  modal(
    user ? 'Gestionar acceso' : 'Crear acceso',
    `<p>${esc(employee?.name || user?.employee?.name || 'Usuario sin empleado vinculado')}</p><form class="access-form" id="access-form" novalidate><label for="access-email">Correo de acceso *<input id="access-email" type="email" required value="${esc(d.email)}" autocomplete="off" aria-describedby="access-email-error"></label><small class="field-error" id="access-email-error"></small><label for="access-role">Rol *<select id="access-role"><option value="EMPLOYEE" ${d.role === 'EMPLOYEE' ? 'selected' : ''}>Empleado</option><option value="ADMIN" ${d.role === 'ADMIN' ? 'selected' : ''}>Administrador</option></select></label><small class="field-error" id="access-role-error"></small><label for="access-permissionProfile">Perfil de permisos *<select id="access-permissionProfile">${Object.entries(
      access.policy.profileLabels,
    )
      .map(
        ([value, label]) =>
          `<option value="${value}" ${d.permissionProfile === value ? 'selected' : ''}>${label}</option>`,
      )
      .join(
        '',
      )}</select></label><small class="field-error" id="access-permissionProfile-error"></small><label for="access-status">Estado<select id="access-status"><option value="ACTIVE" ${d.status === 'ACTIVE' ? 'selected' : ''}>Activo</option><option value="DISABLED" ${d.status === 'DISABLED' ? 'selected' : ''}>Desactivado</option></select></label><small class="field-error" id="access-status-error"></small><label for="access-password">${user ? 'Nueva contraseña (opcional)' : 'Contraseña inicial *'}<input id="access-password" type="password" minlength="12" maxlength="128" autocomplete="new-password" aria-describedby="access-password-error"></label><small class="field-error" id="access-password-error"></small><p class="sub">Usá entre 12 y 128 caracteres. No se envían invitaciones por correo. La contraseña guardada no puede consultarse.</p><p id="access-form-error" class="field-error" role="alert"></p><div class="form-actions"><button type="button" class="button" data-close>Cancelar</button><button type="submit" id="access-save" class="button primary">${user ? 'Guardar acceso' : 'Crear acceso'}</button></div></form>`,
  );
  $('#access-email').focus();
  accessValidate();
}
function accessValidate() {
  if (!access.draft || !$('#access-form')) return;
  const d = access.draft;
  for (const key of ['email', 'role', 'status', 'permissionProfile', 'password'])
    d[key] = $('#access-' + key).value;
  const errors = {};
  if (!$('#access-email').validity.valid || !d.email.trim())
    errors.email = 'Ingresá un correo válido.';
  if ((!d.id || d.password) && d.password.length < 12)
    errors.password = 'Usá al menos 12 caracteres.';
  if ((d.role === 'ADMIN') !== (d.permissionProfile === 'ADMINISTRATOR'))
    errors.permissionProfile = 'El perfil debe corresponder al rol elegido.';
  for (const key of ['email', 'password', 'permissionProfile'])
    $('#access-' + key + '-error').textContent = errors[key] || '';
  $('#access-save').disabled = access.busy || Object.keys(errors).length > 0;
  return errors;
}
async function accessDetail(id) {
  try {
    const { user: u } = await authRequest('/api/users/' + id);
    modal(
      'Detalle del usuario',
      `<h3>Acceso</h3><p>${esc(u.email)}</p>${accessStatus(u)}<p>${u.role === 'ADMIN' ? 'Administrador' : 'Empleado'} · ${esc(access.policy.profileLabels[u.permissionProfile])}</p><h3>Empleado relacionado</h3>${u.employee ? `<div class="person">${personImage(u.employee)}<div>${esc(u.employee.name)}<p>${esc(u.employee.role)} · ${esc(u.employee.area)}</p></div></div><button class="button" data-access="profile" data-id="${u.employeeId}">Ver empleado</button>` : '<p>Sin empleado vinculado.</p>'}<h3>Actividad de acceso</h3><p>Último acceso: ${esc(accessLast(u))}</p>`,
    );
  } catch {
    toast('No pudimos cargar el usuario. Intentá nuevamente.');
  }
}
teamAccess = function (id) {
  const employee = teamEmployee(id);
  if (employee && access.loaded)
    accessEditor(
      access.users.find((u) => u.employeeId === id),
      employee,
    );
};
const accessProfile = teamProfile;
teamProfile = function (id) {
  const html = accessProfile(id),
    e = teamEmployee(id);
  return html + (e && can('users.view') ? accessSection(e) : '');
};
document.addEventListener('input', (e) => {
  if (e.target.id === 'users-search') {
    const pos = e.target.selectionStart;
    access.query = e.target.value;
    render();
    $('#users-search').focus();
    $('#users-search').setSelectionRange(pos, pos);
  }
  if (e.target.closest('#access-form')) accessValidate();
});
document.addEventListener('change', (e) => {
  if (e.target.id === 'access-role')
    $('#access-permissionProfile').value =
      e.target.value === 'ADMIN' ? 'ADMINISTRATOR' : 'EMPLOYEE';
  if (e.target.closest('#access-form')) accessValidate();
});
// El backend revoca las sesiones de la cuenta si cambian credenciales, identidad o permisos.
function accessConfirmSave(d) {
  const label = (code) => access.policy?.profileLabels?.[code] || code;
  const original = d.id ? access.users.find((u) => u.id === d.id) : null;
  if (!original)
    return confirmAction({
      title: '¿Crear el acceso?',
      message: 'La persona podrá ingresar a VitaDev con este correo y la contraseña definida.',
      details: [
        ['Correo', d.email],
        ['Perfil', label(d.permissionProfile)],
        ['Estado', d.status === 'ACTIVE' ? 'Activo' : 'Deshabilitado'],
      ],
      notes: ['Comunicale la contraseña inicial por un canal privado: VitaDev no envía correos.'],
      confirmLabel: 'Sí, crear acceso',
    });
  const revokes =
    !!d.password ||
    ['email', 'role', 'status', 'permissionProfile'].some((k) => d[k] !== original[k]);
  if (!revokes) return Promise.resolve(true);
  const changes = [
    d.email !== original.email && 'correo',
    d.permissionProfile !== original.permissionProfile &&
      `perfil (${label(original.permissionProfile)} → ${label(d.permissionProfile)})`,
    d.status !== original.status && (d.status === 'ACTIVE' ? 'reactivación' : 'desactivación'),
    d.password && 'contraseña',
  ].filter(Boolean);
  const self = original.id === authSession?.userId;
  return confirmAction({
    tone: d.status !== 'ACTIVE' ? 'danger' : 'warning',
    title: '¿Guardar los cambios de acceso?',
    message: `Cambios: ${changes.join(', ')}.`,
    notes: [
      self
        ? 'Es tu propia cuenta: se cerrará tu sesión y deberás volver a ingresar.'
        : `Se cerrarán las sesiones abiertas de ${accessName(original)}.`,
    ],
    confirmLabel: 'Sí, guardar',
  });
}
document.addEventListener('submit', async (e) => {
  if (e.target.id !== 'access-form') return;
  e.preventDefault();
  if (access.busy || Object.keys(accessValidate()).length) return;
  if (!(await accessConfirmSave(access.draft))) return;
  access.busy = true;
  accessValidate();
  try {
    await authRequest('/api/users' + (access.draft.id ? '/' + access.draft.id : ''), access.draft);
    access.draft.password = '';
    $('#modal').close();
    access.busy = false;
    await accessLoad(false);
    render();
    toast('Acceso guardado correctamente.');
  } catch (error) {
    access.busy = false;
    accessValidate();
    for (const [key, message] of Object.entries(
      error.errors || { _form: 'No se pudo guardar el acceso.' },
    )) {
      const el = $('#access-' + key + '-error') || $('#access-form-error');
      el.textContent = message;
    }
  }
});
document.addEventListener('click', async (e) => {
  const b = e.target.closest('[data-access]');
  if (!b) return;
  const op = b.dataset.access,
    id = Number(b.dataset.id),
    u = access.users.find((u) => u.id === id);
  if (op === 'users' || op === 'roles') {
    access.tab = op;
    render();
  }
  if (op === 'retry') accessLoad();
  if (op === 'detail') accessDetail(id);
  if (op === 'edit') accessEditor(u, u.employee);
  if (op === 'employee') teamAccess(id);
  if (op === 'profile') {
    $('#modal').close();
    employeeDetail(id);
  }
  if (op === 'toggle' && can('users.manage')) {
    const enable = u.status !== 'ACTIVE';
    const ok = await confirmAction({
      tone: enable ? 'info' : 'danger',
      title: enable
        ? `¿Reactivar el acceso de ${accessName(u)}?`
        : `¿Desactivar el acceso de ${accessName(u)}?`,
      message: enable
        ? 'La cuenta volverá a poder iniciar sesión si cumple las condiciones de acceso.'
        : 'Ya no podrá ingresar a VitaDev y se cerrarán sus sesiones abiertas. Su información y actividad histórica se conservan.',
      confirmLabel: enable ? 'Sí, reactivar' : 'Sí, desactivar',
      cancelLabel: 'Volver',
    });
    if (!ok) return;
    try {
      await authRequest('/api/users/' + id, { ...u, status: enable ? 'ACTIVE' : 'DISABLED' });
      $('#modal').close();
      await accessLoad();
      notify('success', enable ? 'Acceso reactivado' : 'Acceso desactivado', accessName(u));
    } catch (error) {
      notify(
        'error',
        'No se pudo actualizar el acceso',
        Object.values(error.errors || { _form: 'Volvé a intentar.' }).join(' '),
      );
    }
  }
});
$('#profile').onclick = () => {
  const existing = $('#authenticated-menu');
  if (existing) {
    existing.remove();
    return;
  }
  const u = authSession,
    menu = document.createElement('div');
  menu.id = 'authenticated-menu';
  menu.className = 'user-menu';
  menu.innerHTML = `<strong>${esc(u.employee?.name || u.email)}</strong><p>${u.role === 'ADMIN' ? 'Administrador' : 'Empleado'}</p>${u.employeeId ? '<button class="button" id="auth-my-profile">Mi perfil</button>' : ''}<button class="button" id="auth-logout">Cerrar sesión</button>`;
  document.querySelector('header').append(menu);
  $('#auth-my-profile')?.addEventListener('click', () => {
    menu.remove();
    if (u.role === 'ADMIN') employeeDetail(u.employeeId);
    else nav('employees');
  });
  $('#auth-logout').onclick = async (event) => {
    event.target.disabled = true;
    event.target.classList.add('is-busy');
    event.target.textContent = 'Cerrando sesión…';
    try {
      await authRequest('/api/auth/logout', {});
      authSession = null;
      document.querySelector('#app').innerHTML = '';
      document.querySelectorAll('dialog[open]').forEach((d) => d.close());
      location.replace('/login');
    } catch {
      event.target.disabled = false;
      event.target.classList.remove('is-busy');
      event.target.textContent = 'Cerrar sesión';
      toast('No se pudo cerrar la sesión. Revisá la conexión y volvé a intentar.');
    }
  };
  menu.querySelector('button').focus();
};
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') $('#authenticated-menu')?.remove();
});
// Tocar fuera del menú lo cierra (en celular no hay otra forma evidente de descartarlo).
document.addEventListener('click', (e) => {
  const menu = $('#authenticated-menu');
  if (menu && !menu.contains(e.target) && !e.target.closest('#profile')) menu.remove();
});
if (can('users.view')) accessLoad();

$('#modal').addEventListener('close', () => {
  if (access.draft) access.draft.password = '';
  access.draft = null;
});
