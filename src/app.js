const $ = (s) => document.querySelector(s),
  esc = (s) =>
    String(s ?? '').replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
const paths = {
  home: 'M3 10l9-7 9 7v10H3z M9 20v-7h6v7',
  people:
    'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M17 4a4 4 0 0 1 0 7 M22 21v-2a4 4 0 0 0-3-4',
  clients: 'M4 21V5h11v16 M15 10h5v11 M8 9h3 M8 13h3 M8 17h3',
  support: 'M4 13v-3a8 8 0 0 1 16 0v3 M4 12H2v7h4v-7z M20 12h2v7h-4v-7z M18 19v3h-6',
  calendar: 'M4 5h16v16H4z M8 2v6 M16 2v6 M4 10h16',
  chart: 'M4 20V10 M10 20V4 M16 20v-7 M22 20H2',
  box: 'M3 7l9-5 9 5v11l-9 5-9-5z M3 7l9 5 9-5 M12 12v11',
  book: 'M4 3h15v18H4z M8 7h7 M8 11h7',
  arrow: 'M5 12h14 M13 6l6 6-6 6',
  edit: 'M12 20h9 M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z',
  more: 'M5 12h.01 M12 12h.01 M19 12h.01',
  check: 'M5 12l4 4L19 6',
  spark: 'M12 2l3 7 7 3-7 3-3 7-3-7-7-3 7-3z',
};
const ico = (k) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[k] || paths.box}"/></svg>`;
let state = {
  // PORTAL-CLIENTE: hoy solo 'admin' o 'employee'. Las ramas state.role === 'client' son un
  // esqueleto inactivo del Portal Cliente, con el cliente fijo en id 1. Antes de activarlo,
  // ver "Portal Cliente (pendiente)" en src/backend/ARCHITECTURE.md.
  role: authSession.role === 'ADMIN' ? 'admin' : 'employee',
  page: 'home',
  search: '',
  filter: 'Todos',
  period: 'week',
  view: 'cards',
};
const menus = [
  ['home', 'Resumen', 'home'],
  ['employees', 'Empleados', 'people'],
  ['clients', 'Clientes', 'clients'],
  ['support', 'Centro de atención', 'support'],
  ['calendar', 'Agenda y licencias', 'calendar'],
  ['products', 'Productos y contratos', 'box'],
  ['tasks', 'Mis tareas', 'check'],
  ['reports', 'Reportes', 'chart'],
  ['users', 'Usuarios y permisos', 'people'],
  ['settings', 'Configuración', 'box'],
];
let toastTimer;
function toast(msg) {
  clearTimeout(toastTimer);
  $('#toast').textContent = msg;
  $('#toast').classList.add('show');
  toastTimer = setTimeout(() => $('#toast').classList.remove('show'), 4500);
}
function nav(p) {
  if (!allowed().includes(p)) {
    state.page = p;
    render();
    return;
  }
  if (p === 'reports' && typeof rp !== 'undefined') rp.data = null;
  state.page = p;
  const route = Object.entries(privateRoutes).find(([, value]) => value === p)?.[0];
  if (route) history.pushState({}, '', '/' + route);
  state.search = '';
  state.filter = 'Todos';
  render();
  $('#sidebar').classList.remove('open');
}
function heading(title, sub, action = '') {
  return `<div class="heading"><div><div class="eyebrow">${state.role === 'client' ? 'Tu institución, conectada' : 'VitaDev · Espacio de trabajo'}</div><h1>${title}</h1><p class="sub">${sub}</p></div>${action}</div>`;
}
const btn = (txt, act, primary = false) =>
  `<button class="button ${primary ? 'primary' : ''}" data-action="${act}">${txt}</button>`;
function stat(label, val, note, icon) {
  return `<div class="stat"><div class="stat-top">${label}${ico(icon)}</div><div class="stat-value">${val}</div><small>${note}</small></div>`;
}
function modal(title, body) {
  $('#modalContent').innerHTML =
    `<div class="modal-head"><h2>${title}</h2><button class="icon" data-close aria-label="Cerrar">×</button></div>${body}`;
  if (!$('#modal').open) $('#modal').showModal();
}
function search() {
  modal(
    'Buscar en VitaDev',
    `<input id="global-search" type="search" style="width:100%" placeholder="Nombre, institución o solicitud…" aria-label="Búsqueda global"><div id="search-results"><p class="sub">Buscá por nombre o número de solicitud.</p></div>`,
  );
  $('#global-search').focus();
}
$('#searchButton').onclick = search;
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    search();
  }
});
$('#theme').onclick = () => document.body.classList.toggle('dark');
$('#menu').onclick = () => $('#sidebar').classList.toggle('open');
// PORTAL-CLIENTE: reemplazar el 1 fijo por el cliente de la sesión.
$('#profile').onclick = () =>
  state.role === 'client' ? clientDetail(1) : employeeDetail(currentEmployeeId());
$('#modal').addEventListener('click', (e) => {
  if (e.target === $('#modal')) $('#modal').close();
});
// Caches de transporte: se reemplazan por respuestas del backend; no contienen semillas.
let employees = [],
  clients = [],
  tickets = [],
  leaves = [];
const currentEmployeeId = () => authSession?.employeeId || null;
const employeePermission = (permission) =>
  can(permission === 'support' ? 'requests.viewAssigned' : 'clients.view');
const allowed = () => [
  'home',
  'settings',
  ...(authSession?.employeeId ? ['employees'] : []),
  ...(can('employees.view') ? ['employees'] : []),
  ...(can('clients.view') ? ['clients', 'products'] : []),
  ...(can('requests.viewAssigned') || can('requests.viewQueue') ? ['support'] : []),
  ...(can('tasks.viewAssigned') ? ['tasks'] : []),
  ...(can('leaves.viewOwn') || can('leaves.manage') ? ['calendar'] : []),
  ...(can('reports.view') ? ['reports'] : []),
  ...(can('users.view') ? ['users'] : []),
];
// PORTAL-CLIENTE: reemplazar el 1 fijo por el cliente de la sesión.
const visibleTickets = () =>
  state.role === 'client'
    ? tickets.filter((t) => t.clientId === 1)
    : state.role === 'employee'
      ? tickets.filter((t) => employeePermission('support') && t.agentId === currentEmployeeId())
      : tickets;
const badge = (s) => uiBadge(s);
function sidebar() {}
function home() {
  return heading('Inicio', 'Cargando registros…');
}
function employeesPage() {
  return heading('Equipo', 'Cargando registros…');
}
function clientsPage() {
  return heading('Clientes', 'Cargando registros…');
}
function support() {
  return heading('Solicitudes', 'Cargando registros…');
}
function calendar() {
  return heading('Licencias', 'Cargando registros…');
}
function products() {
  return heading('Productos y servicios', 'Cargando registros…');
}
function reports() {
  return heading('Reportes', 'Cargando registros…');
}
function action() {
  toast('El módulo todavía está cargando.');
}
function employeeDetail(id) {
  if (state.role === 'employee' && id === currentEmployeeId()) nav('employees');
}
function clientDetail() {}
function ticketDetail() {}
function render() {
  if (!authSession || !authLoaded) return;
  sidebar();
  if (
    !allowed().includes(state.page) &&
    !(
      state.page === 'support' &&
      typeof desk !== 'undefined' &&
      desk.view === 'detail' &&
      desk.data.tasks.some((t) => t.ticket === desk.id && t.owner === currentEmployeeId())
    )
  ) {
    $('#app').innerHTML =
      heading('Acceso restringido', 'No tenés permisos para acceder a esta sección.') +
      '<button class="button" data-nav="home">Volver al inicio</button>';
    return;
  }
  $('#crumb').textContent = menus.find((m) => m[0] === state.page)?.[1] || 'Inicio';
  const pages = {
    home,
    employees: employeesPage,
    clients: clientsPage,
    support,
    calendar,
    products,
    reports,
    tasks: employeeTasksPage,
    users: () => usersPage(),
    settings: () => settingsPage(),
  };
  $('#app').innerHTML = (pages[state.page] || home)();
  $('#profile').innerHTML = personImage(
    // PORTAL-CLIENTE: reemplazar el 1 fijo por el cliente de la sesión.
    state.role === 'client'
      ? clients.find((c) => c.id === 1)
      : employees.find((e) => e.id === currentEmployeeId()),
    'small',
    state.role === 'client' ? 'company' : 'employee',
  );
}
document.addEventListener('click', (e) => {
  for (const [attr, fn] of [
    ['nav', nav],
    ['action', action],
    ['employee', (id) => employeeDetail(Number(id))],
    ['client', (id) => clientDetail(Number(id))],
    ['ticket', (id) => ticketDetail(Number(id))],
  ]) {
    const b = e.target.closest('[data-' + attr + ']');
    if (b) {
      e.preventDefault();
      fn(b.dataset[attr]);
    }
  }
  if (e.target.closest('[data-close]')) $('#modal').close();
});
document.addEventListener('input', (e) => {
  if (e.target.id !== 'global-search') return;
  const q = e.target.value.toLowerCase(),
    out = [];
  if (state.role === 'admin' || employeePermission('crm'))
    out.push(
      ...clients
        .filter((c) => c.name.toLowerCase().includes(q))
        .map((c) => `<p><button class="link" data-client="${c.id}">${esc(c.name)}</button></p>`),
    );
  out.push(
    ...visibleTickets()
      .filter((t) => `${t.id} ${t.title}`.toLowerCase().includes(q))
      .map(
        (t) =>
          `<p><button class="link" data-ticket="${t.id}">#${t.id} ${esc(t.title)}</button></p>`,
      ),
  );
  $('#search-results').innerHTML = q
    ? out.join('') || '<p>Sin coincidencias.</p>'
    : '<p>Buscá por nombre o solicitud.</p>';
});

// Al volver a la ventana se refrescan las solicitudes, como máximo una vez por minuto.
let deskFocusAt = Date.now();
window.addEventListener('focus', () => {
  if (typeof desk === 'undefined' || desk.busy || Date.now() - deskFocusAt < 60000) return;
  deskFocusAt = Date.now();
  hdLoad(false).then(() => render());
});
window.addEventListener('popstate', () => {
  state.page = privateRoutes[location.pathname.slice(1)] || 'home';
  render();
});
