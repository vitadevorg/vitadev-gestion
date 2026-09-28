// Assets suministrados. Las fotografías y los logos mantienen sus proporciones.
const ASSETS = {
  brand: 'assets/brand/vitadev-logo.png',
  avatar: 'assets/avatars/default-avatar.png',
  company: 'assets/clients/default-company.png',
};
function personImage(record, size = 'small', type = 'employee') {
  const company = type === 'company',
    fallback = company ? ASSETS.company : ASSETS.avatar;
  const src = (company ? record?.logo : record?.photo) || fallback;
  return `<img class="real-avatar ${company ? 'company-logo' : ''} ${size === 'large' ? 'avatar-large' : ''}" src="${esc(src)}" alt="${esc(record?.name || (company ? 'Institución' : 'Empleado'))}" width="${size === 'large' ? 88 : 40}" height="${size === 'large' ? 88 : 40}" data-image-fallback="${fallback}">`;
}
function eventImage() {
  return '<span class="activity-icon">' + ico('check') + '</span>';
}
document.addEventListener(
  'error',
  (event) => {
    const img = event.target;
    if (img.tagName !== 'IMG' || !img.dataset.imageFallback) return;
    const fallback = img.dataset.imageFallback;
    delete img.dataset.imageFallback;
    img.src = fallback;
  },
  true,
);

const visualStates = {
  requests: ['no-requests', 'No hay solicitudes', 'Las nuevas solicitudes aparecerán acá.'],
  tasks: ['no-tasks', 'No hay tareas', 'Las tareas asignadas aparecerán acá.'],
  clients: ['no-clients', 'No hay clientes', 'Los clientes registrados aparecerán acá.'],
  leaves: ['no-leaves', 'No hay licencias', 'Las solicitudes de licencia aparecerán acá.'],
  results: [
    'no-results',
    'No encontramos resultados',
    'Probá modificando la búsqueda o los filtros.',
  ],
  error: [
    'error-loading',
    'No pudimos cargar la información',
    'Ocurrió un problema al obtener los datos.',
  ],
};
function visualState(kind, action = '', title = '', description = '') {
  const v = visualStates[kind];
  return `<section class="visual-state" role="${kind === 'error' ? 'alert' : 'status'}"><img src="assets/empty-states/${v[0]}.png" alt="" width="180" height="160"><h3>${esc(title || v[1])}</h3><p>${esc(description || v[2])}</p>${action}</section>`;
}

function tableEmpty(headers) {
  if (headers[0] === 'Cliente')
    return visualState(
      crm.data.clients.length ? 'results' : 'clients',
      crm.data.clients.length ? crButton('Limpiar filtros', 'clear') : '',
    );
  if (headers[0] === 'Solicitud')
    return visualState(
      desk.data.requests.some(hdCanView) ? 'results' : 'requests',
      desk.data.requests.some(hdCanView) ? hdBtn('Limpiar filtros', 'clear') : '',
    );
  if (headers.includes('Período') && headers[0] === 'Empleado')
    return visualState(
      lv.items.length ? 'results' : 'leaves',
      lv.items.length ? lvBtn('Limpiar filtros', 'clear') : '',
    );
  return crEmpty('No hay registros para mostrar.');
}

document.addEventListener('click', (e) => {
  if (e.target.closest('[data-visual-retry=reports]')) rpLoad();
});
