/* Clientes y gestión comercial: módulo aislado, con persistencia propia. */
const crm = {
  loaded: false,
  error: '',
  data: { clients: [], contacts: [], catalog: [], subscriptions: [], contracts: [], activity: [] },
  options: {},
  today: '',
  view: 'list',
  id: null,
  tab: 'Resumen',
  query: '',
  status: '',
  product: '',
  owner: '',
  form: null,
  step: 0,
  errors: {},
  touched: new Set(),
  busy: false,
};
const crmTabs = [
  'Resumen',
  'Contactos',
  'Productos y servicios',
  'Contratos',
  'Solicitudes',
  'Actividad',
];
const cr = (id) => crm.data.clients.find((c) => c.id === Number(id));
const crProduct = (id) => crm.data.catalog.find((p) => p.id === Number(id));
const crEmployee = (id) => employees.find((e) => e.id === Number(id));
const crRelated = (kind, id = crm.id) => crm.data[kind].filter((r) => r.clientId === Number(id));
const crDate = (v) => (v ? teamDate(v) : '—');
const crEmpty = (s) => `<div class="crm-empty">${esc(s)}</div>`;
const crBadge = (s) =>
  `<span class="crm-badge ${['Vencido', 'Suspendido', LABOR.INACTIVE, 'Finalizado'].includes(s) ? 'crm-muted' : s === 'Próximo a vencer' ? 'crm-due' : ''}">${esc(s)}</span>`;
const crButton = (label, op, id = '', primary = false) =>
  `<button type="button" class="button ${primary ? 'primary' : ''}" data-crm="${op}" data-id="${id}">${label}</button>`;
const crPerson = (id) => {
  const e = crEmployee(id);
  return e
    ? `<div class="person">${personImage(e)}<span>${esc(e.name)}</span></div>`
    : 'Sin responsable';
};
const crContractStatus = (c) =>
  ['Vigente', 'Próximo a vencer', 'Vencido'].includes(c.status) && c.end
    ? c.end < crm.today
      ? 'Vencido'
      : Math.ceil((new Date(c.end + 'T12:00:00') - new Date(crm.today + 'T12:00:00')) / 86400000) <=
          30
        ? 'Próximo a vencer'
        : 'Vigente'
    : c.status;
const crRenewal = (id) =>
  crRelated('contracts', id)
    .filter(
      (c) =>
        c.end &&
        c.renewal !== 'Sin renovación' &&
        ['Vigente', 'Próximo a vencer'].includes(crContractStatus(c)),
    )
    .map((c) => c.end)
    .sort()[0] || '';
const crTickets = (id) => tickets.filter((t) => t.clientId === Number(id));
function crTable(headers, rows) {
  if (!rows.length) return tableEmpty(headers);
  return `<div class="table-wrap"><table><thead><tr>${headers.map((h) => `<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${rows.join('') || `<tr><td colspan="${headers.length}">${tableEmpty(headers)}</td></tr>`}</tbody></table></div>`;
}
async function crApi(path = '', data, method = 'POST') {
  const response = await fetch('/api/crm' + path, {
    method: data === undefined ? 'GET' : method,
    headers:
      data === undefined ? {} : { 'Content-Type': 'application/json', 'X-Nexo-Client': 'team' },
    body: data === undefined ? undefined : JSON.stringify(data),
    cache: 'no-store',
  });
  let value;
  try {
    value = await response.json();
  } catch {
    throw {
      errors: {
        _form: 'El servicio de Clientes no está disponible. Tus datos permanecen en el formulario.',
      },
    };
  }
  if (!response.ok) {
    value.status = response.status;
    throw value;
  }
  return value;
}
// Mesa de Ayuda también pide Clientes al iniciar: se comparte la carga inicial en curso en lugar
// de duplicarla. Después de una modificación siempre se piden datos frescos.
let crInitialLoad = null;
function crLoad(draw = true) {
  if (!crm.loaded && crInitialLoad)
    return crInitialLoad.then((ok) => {
      if (draw) render();
      return ok;
    });
  const load = crFetch(draw);
  if (!crm.loaded) crInitialLoad = load.finally(() => (crInitialLoad = null));
  return load;
}
async function crFetch(draw) {
  try {
    const data = await crApi();
    crm.data = data;
    crm.options = data.options;
    crm.today = data.today;
    crm.loaded = true;
    crm.error = '';
    // Compatibilidad con los selectores existentes: conserva IDs y campos heredados.
    clients = data.clients;
  } catch (e) {
    crm.error = e.errors ? Object.values(e.errors).join(' ') : 'No se pudo conectar con Clientes.';
  }
  document.dispatchEvent(new Event('nexo:data-changed'));
  if (draw) render();
  return !crm.error;
}
function crMore(kind, id) {
  const label =
    kind === 'clients'
      ? 'Finalizar relación'
      : kind === 'contacts'
        ? 'Desactivar contacto'
        : 'Finalizar contrato';
  return `<details class="crm-menu"><summary aria-label="Más opciones">${ico('more')}</summary><div>${kind === 'contacts' ? `<button data-crm="principal" data-id="${id}">Marcar como principal</button>` : ''}<button data-crm="finish-${kind}" data-id="${id}">${label}</button></div></details>`;
}
function crSelectFilter(key, label, opts) {
  return `<label>${label}<select data-crm-filter="${key}"><option value="">${label}</option>${opts.map(([value, name]) => `<option value="${esc(value)}" ${String(crm[key]) === String(value) ? 'selected' : ''}>${esc(name)}</option>`).join('')}</select></label>`;
}
function crList() {
  const list = crm.data.clients.filter(
    (c) =>
      [c.name, c.legalName, c.cuit, c.city, c.province]
        .join(' ')
        .toLocaleLowerCase('es')
        .includes(crm.query.toLocaleLowerCase('es')) &&
      (!crm.status || c.status === crm.status) &&
      (!crm.owner || c.owner === Number(crm.owner)) &&
      (!crm.product ||
        crRelated('subscriptions', c.id).some((s) => s.productId === Number(crm.product))),
  );
  return (
    heading(
      'Clientes',
      'Instituciones y organizaciones vinculadas a VitaDev.',
      crButton('Productos y servicios', 'catalog') +
        crButton('+ Nuevo cliente', 'new-clients', '', true),
    ) +
    `<div class="crm-filters"><label>Buscar cliente<input type="search" id="crm-search" value="${esc(crm.query)}" placeholder="Nombre, razón social, CUIT o ubicación"></label>${crSelectFilter(
      'status',
      'Todos los estados',
      crm.options.clientStates.map((v) => [v, v]),
    )}${crSelectFilter(
      'product',
      'Todos los productos/servicios',
      crm.data.catalog.map((p) => [p.id, p.name]),
    )}${crSelectFilter(
      'owner',
      'Todos los responsables',
      employees.map((e) => [e.id, e.name]),
    )}${crButton('Limpiar filtros', 'clear')}</div><div class="crm-list-meta"><span>${list.length} de ${crm.data.clients.length} clientes</span>${crButton('Exportar CSV', 'export')}</div><section class="panel table-panel crm-table-panel">${crTable(
      [
        'Cliente',
        'Estado',
        'Productos / servicios',
        'Responsable VitaDev',
        'Solicitudes abiertas',
        'Próxima renovación',
        '<span class="sr-only">Acciones</span>',
      ],
      list.map((c) => {
        const p = crRelated('subscriptions', c.id)
          .filter((s) => s.status !== 'Finalizado')
          .map((s) => crProduct(s.productId)?.name || 'Producto archivado');
        // El nombre abre la ficha (accesible por teclado) y toda la fila también; las acciones
        // secundarias quedan como botones de ícono del mismo tamaño.
        return `<tr class="crm-row" data-crm-row="${c.id}"><td class="crm-cell-client"><div class="person">${personImage(c, 'small', 'company')}<div><button class="crm-name-link" data-crm="profile" data-id="${c.id}">${esc(c.name)}</button><small>${esc([c.city, c.province].filter(Boolean).join(', '))}</small></div></div></td><td class="crm-cell-status">${crBadge(c.status)}</td><td class="crm-cell-products">${p.length ? esc(p[0]) + (p.length > 1 ? ` <span class="sub">+ ${p.length - 1} más</span>` : '') : '—'}</td><td class="crm-cell-owner">${crPerson(c.owner)}</td><td class="crm-cell-open"><span class="crm-count" title="Solicitudes abiertas">${crTickets(c.id).filter(isOpen).length}</span></td><td class="crm-cell-renewal">${crDate(crRenewal(c.id))}</td><td class="crm-cell-actions"><div class="crm-row-actions"><button class="icon-action" data-crm="edit-clients" data-id="${c.id}" aria-label="Editar ${esc(c.name)}" title="Editar">${ico('edit')}</button>${crMore('clients', c.id)}</div></td></tr>`;
      }),
    )}</section>`
  );
}
function crInfo(items) {
  return `<dl class="crm-info">${items.map(([k, v]) => `<div><dt>${k}</dt><dd>${v === undefined || v === '' ? '—' : esc(v)}</dd></div>`).join('')}</dl>`;
}
function crSummary(c) {
  const p = crRelated('contacts').find((p) => p.principal && p.status === LABOR.ACTIVE);
  return `<div class="crm-columns"><section><h2>Información institucional</h2>${crInfo([
    ['Nombre comercial', c.name],
    ['Razón social', c.legalName],
    ['CUIT', c.cuit],
    ['Tipo de organización', c.organizationType],
    ['Dirección', c.address],
    ['Ciudad', c.city],
    ['Provincia / Estado', c.province],
    ['País', c.country],
    ['Fecha de alta', new Date(c.createdAt).toLocaleDateString('es-AR')],
  ])}${!c.cuit ? '<p class="crm-note">Registro inicial: completá la información fiscal al editar.</p>' : ''}</section><section><h2>Gestión comercial</h2>${crInfo(
    [
      ['Estado', c.status],
      ['Responsable VitaDev', crEmployee(c.owner)?.name],
      ['Cliente desde', crDate(c.since)],
    ],
  )}<h2>Resumen operativo</h2>${crInfo([
    [
      'Productos/servicios activos',
      crRelated('subscriptions').filter((s) => s.status === LABOR.ACTIVE).length,
    ],
    [
      'Contratos vigentes',
      crRelated('contracts').filter((c) =>
        ['Vigente', 'Próximo a vencer'].includes(crContractStatus(c)),
      ).length,
    ],
    ['Solicitudes abiertas', crTickets(c.id).filter(isOpen).length],
    ['Próxima renovación', crDate(crRenewal(c.id))],
  ])}<h2>Contacto principal</h2>${p ? `<p><strong>${esc(p.firstName + ' ' + p.lastName)}</strong></p><p>${esc(p.position)}</p><p>${esc(p.email)}</p><p>${esc(p.phone)}</p>` : crEmpty('Todavía no hay un contacto principal registrado.')}</section></div>`;
}
function crContacts() {
  return `<div class="crm-section-head"><h2>Contactos de la organización</h2>${crButton('+ Nuevo contacto', 'new-contacts', '', true)}</div>${crTable(
    ['Nombre', 'Cargo', 'Correo', 'Teléfono', 'Tipo / rol', 'Estado', 'Acciones'],
    crRelated('contacts').map(
      (p) =>
        `<tr><td><strong>${esc(p.firstName + ' ' + p.lastName)}</strong>${p.principal ? '<small>Contacto principal</small>' : ''}</td><td>${esc(p.position) || '—'}</td><td>${esc(p.email)}</td><td>${esc(p.phone) || '—'}</td><td>${esc(p.role) || '—'}</td><td>${crBadge(p.status)}</td><td><div class="crm-actions">${crButton('Ver / Editar', 'edit-contacts', p.id)}${p.status === LABOR.ACTIVE ? crMore('contacts', p.id) : ''}</div></td></tr>`,
    ),
  )}`;
}
function crSubscriptions() {
  return `<div class="crm-section-head"><h2>Productos y servicios contratados</h2>${crButton('+ Agregar producto o servicio', 'new-subscriptions', '', true)}</div>${crTable(
    [
      'Producto / servicio',
      'Plan',
      'Estado',
      'Inicio',
      'Contrato asociado',
      'Próxima renovación',
      '',
    ],
    crRelated('subscriptions').map((s) => {
      const contracts = crRelated('contracts').filter((c) => c.subscriptionIds.includes(s.id));
      return `<tr><td><strong>${esc(crProduct(s.productId)?.name)}</strong></td><td>${esc(s.plan) || '—'}</td><td>${crBadge(s.status)}</td><td>${crDate(s.start)}</td><td>${contracts.map((c) => `<button class="link" data-crm="edit-contracts" data-id="${c.id}">${esc(c.number)}</button>`).join('<br>') || '—'}</td><td>${crDate(
        contracts
          .filter(
            (c) =>
              c.renewal !== 'Sin renovación' &&
              ['Vigente', 'Próximo a vencer'].includes(crContractStatus(c)),
          )
          .map((c) => c.end)
          .filter(Boolean)
          .sort()[0],
      )}</td><td>${crButton('Ver detalle', 'edit-subscriptions', s.id)}</td></tr>`;
    }),
  )}`;
}
function crDocument(c) {
  return c.document
    ? `<span class="crm-file-name">${esc(c.documentName || 'Contrato PDF')}</span><a class="link" href="${esc(c.document)}" target="_blank" rel="noopener">Ver documento</a> · <a class="link" href="${esc(c.document)}?download=1" download>Descargar</a>`
    : '—';
}
function crContracts() {
  return `<div class="crm-section-head"><h2>Contratos</h2>${crButton('+ Nuevo contrato', 'new-contracts', '', true)}</div>${crRelated('subscriptions').length ? '' : '<p class="crm-note">Agregá primero un producto o servicio contratado para vincular el contrato.</p>'}${crTable(
    [
      'Contrato',
      'Productos / servicios',
      'Estado',
      'Vigencia',
      'Importe / periodicidad',
      'Documento',
      'Acciones',
    ],
    crRelated('contracts').map(
      (c) =>
        `<tr><td><strong>${esc(c.number)}</strong></td><td>${c.subscriptionIds
          .map((id) => crProduct(crm.data.subscriptions.find((s) => s.id === id)?.productId)?.name)
          .filter(Boolean)
          .map(esc)
          .join(
            ', ',
          )}</td><td>${crBadge(crContractStatus(c))}</td><td>${crDate(c.start)}<small>hasta ${crDate(c.end)}</small></td><td>${c.amount !== '' ? new Intl.NumberFormat('es-AR', { style: 'currency', currency: c.currency }).format(Number(c.amount)) : '—'}<small>${esc(c.period)}</small></td><td>${crDocument(c)}</td><td><div class="crm-actions">${crButton('Ver / Editar', 'edit-contracts', c.id)}${c.status !== 'Finalizado' ? crMore('contracts', c.id) : ''}</div></td></tr>`,
    ),
  )}`;
}
function crRequests() {
  return `<h2>Solicitudes del cliente</h2>${crTable(
    [
      'ID / Título',
      'Producto / servicio',
      'Tipo',
      'Prioridad',
      'Estado',
      'Creación',
      'Última actualización',
    ],
    crTickets(crm.id).map(
      (t) =>
        `<tr><td><button class="link" data-ticket="${t.id}">#${t.id} · ${esc(t.title)}</button></td><td>${esc(t.subscriptionId ? crProduct(crm.data.subscriptions.find((s) => s.id === t.subscriptionId)?.productId)?.name || 'Sin relación registrada' : t.product || 'Sin relación registrada')}</td><td>${esc(t.type || 'Sin registrar')}</td><td>${esc(t.priority)}</td><td>${crBadge(t.status)}</td><td>${crDate(t.createdAt?.slice(0, 10))}</td><td>${crDate(t.updatedAt?.slice(0, 10))}</td></tr>`,
    ),
  )}<p class="crm-note">Consulta de las solicitudes existentes. No se asignan empleados desde esta ficha.</p>`;
}
function crActivity() {
  return `<h2>Actividad del cliente</h2><ol class="crm-timeline">${
    crm.data.activity
      .filter((a) => a.client_id === crm.id)
      .map(
        (a) =>
          `<li><time>${esc(new Date(a.created_at).toLocaleString('es-AR'))}</time><strong>${esc(a.action)}</strong><p>${esc(a.reference)}</p><small>${esc(a.actor)}</small></li>`,
      )
      .join('') || crEmpty('Sin actividad registrada.')
  }</ol>`;
}
function crProfile() {
  const c = cr(crm.id);
  if (!c) return crEmpty('Cliente no encontrado.');
  return `${crButton('← Volver a Clientes', 'list')}<div class="crm-profile-head">${personImage(c, 'large', 'company')}<div class="crm-profile-title"><h1>${esc(c.name)}</h1><p>${esc(c.organizationType)} · ${esc(c.city)}, ${esc(c.province)}</p>${crBadge(c.status)}</div><div class="crm-profile-owner"><small>Responsable VitaDev</small>${crPerson(c.owner)}<small>Cliente desde: ${crDate(c.since)}</small></div><div class="crm-actions">${crButton('Editar cliente', 'edit-clients', c.id)}${crMore('clients', c.id)}</div></div><div class="crm-tabs" role="tablist" aria-label="Ficha del cliente">${crmTabs.map((t, i) => `<button role="tab" id="crm-tab-${i}" aria-controls="crm-panel" aria-selected="${crm.tab === t}" tabindex="${crm.tab === t ? 0 : -1}" data-crm="tab" data-id="${i}">${t}</button>`).join('')}</div><section class="crm-profile-body" role="tabpanel" id="crm-panel" aria-labelledby="crm-tab-${crmTabs.indexOf(crm.tab)}">${{ Resumen: () => crSummary(c), Contactos: crContacts, 'Productos y servicios': crSubscriptions, Contratos: crContracts, Solicitudes: crRequests, Actividad: crActivity }[crm.tab]()}</section>`;
}
function crCatalog() {
  return (
    crButton('← Volver a Clientes', 'list') +
    heading(
      'Productos y servicios',
      'Catálogo comercial de VitaDev.',
      crButton('+ Nuevo producto o servicio', 'new-catalog', '', true),
    ) +
    `<section class="panel table-panel">${crTable(
      ['Nombre', 'Descripción', 'Tipo', 'Estado', 'Planes', 'Acciones'],
      crm.data.catalog.map(
        (p) =>
          `<tr><td><strong>${esc(p.name)}</strong></td><td class="crm-description">${esc(p.description)}</td><td>${esc(p.type)}</td><td>${crBadge(p.status)}</td><td>${p.plans.map(esc).join(', ') || 'Sin planes'}</td><td>${crButton('Ver / Editar', 'edit-catalog', p.id)}</td></tr>`,
      ),
    )}</section>`
  );
}
const crField = (key, label, type = 'text', required = false, options = []) => ({
  key,
  label,
  type,
  required,
  options,
});
function crSchemas(kind, d) {
  const f = crField,
    o = crm.options,
    staff = employees
      .filter((e) => e.laborStatus === LABOR.ACTIVE || e.id === d.owner)
      .map((e) => [e.id, e.name]),
    client = [[d.clientId, cr(d.clientId)?.name || 'Cliente']],
    subs = crRelated('subscriptions', d.clientId).map((s) => [
      s.id,
      (crProduct(s.productId)?.name || 'Producto') + (s.plan ? ' · ' + s.plan : '') + ' · #' + s.id,
    ]);
  if (kind === 'clients')
    return [
      [
        'Institución',
        [
          f('logo', 'Logo', 'image'),
          f('name', 'Nombre comercial', 'text', true),
          f('legalName', 'Razón social', 'text', true),
          f('cuit', 'CUIT', 'text', true),
          f('organizationType', 'Tipo de organización', 'select', true, o.organizationTypes),
        ],
      ],
      [
        'Ubicación',
        [
          f('country', 'País', 'text', true),
          f('province', 'Provincia / Estado', 'text', true),
          f('city', 'Ciudad', 'text', true),
          f('address', 'Dirección'),
          f('postalCode', 'Código postal'),
        ],
      ],
      ...(!d.id
        ? [
            [
              'Contacto principal',
              [
                f('primaryContact.firstName', 'Nombre', 'text', true),
                f('primaryContact.lastName', 'Apellido', 'text', true),
                f('primaryContact.position', 'Cargo'),
                f('primaryContact.email', 'Correo', 'email', true),
                f('primaryContact.phone', 'Teléfono', 'tel'),
              ],
            ],
          ]
        : []),
      [
        'Gestión comercial',
        [
          f('owner', 'Responsable VitaDev', 'select', true, staff),
          f(
            'status',
            d.id ? 'Estado' : 'Estado inicial',
            'select',
            true,
            d.id ? o.clientStates : o.clientStates.slice(0, 3),
          ),
          ...(d.id ? [f('since', 'Cliente desde', 'date')] : []),
        ],
      ],
    ];
  if (kind === 'contacts')
    return [
      [
        'Datos del contacto',
        [
          f('firstName', 'Nombre', 'text', true),
          f('lastName', 'Apellido', 'text', true),
          f('position', 'Cargo'),
          f('email', 'Correo', 'email', true),
          f('phone', 'Teléfono', 'tel'),
          f('role', 'Tipo / rol', 'select', false, [
            'Comercial',
            'Administración',
            'Técnico',
            'Dirección',
            'Otro',
          ]),
          f('principal', 'Contacto principal', 'checkbox'),
          f('status', 'Estado', 'select', true, [LABOR.ACTIVE, LABOR.INACTIVE]),
        ],
      ],
    ];
  if (kind === 'catalog')
    return [
      [
        'Información del catálogo',
        [
          f('name', 'Nombre', 'text', true),
          f('description', 'Descripción', 'textarea', true),
          f('type', 'Tipo', 'select', true, o.productTypes),
          f('status', 'Estado', 'select', true, [LABOR.ACTIVE, LABOR.INACTIVE]),
        ],
      ],
      [
        'Planes y configuración',
        [
          f('plans', 'Planes disponibles (uno por línea)', 'lines'),
          f('configFields', 'Opciones configurables de este producto (una por línea)', 'lines'),
        ],
      ],
    ];
  if (kind === 'subscriptions') {
    const p = crProduct(d.productId);
    return [
      [
        'Contratación',
        [
          f(
            'productId',
            'Producto / servicio',
            'select',
            true,
            crm.data.catalog
              .filter((p) => p.status === LABOR.ACTIVE || p.id === d.productId)
              .map((p) => [p.id, p.name]),
          ),
          f('plan', 'Plan', 'select', false, p?.plans || []),
          f('status', 'Estado', 'select', true, o.subscriptionStates),
          f('start', 'Fecha de inicio', 'date', true),
        ],
      ],
      [
        'Configuración del producto',
        [f('configuration', 'Opciones habilitadas', 'multi', false, p?.configFields || [])],
      ],
    ];
  }
  return [
    [
      'Datos del contrato',
      [
        f('number', 'Número de contrato', 'text', true),
        f('clientId', 'Cliente', 'select', true, client),
        f('subscriptionIds', 'Productos / servicios relacionados', 'multi', true, subs),
        f('status', 'Estado', 'select', true, o.contractStates),
      ],
    ],
    [
      'Vigencia',
      [
        f('signed', 'Fecha de firma', 'date'),
        f('start', 'Fecha de inicio', 'date', true),
        f('end', 'Fecha de vencimiento', 'date'),
        f('renewal', 'Tipo de renovación', 'select', true, o.renewals),
      ],
    ],
    [
      'Condiciones comerciales',
      [
        f('amount', 'Importe', 'number'),
        f('currency', 'Moneda', 'select', true, ['ARS', 'USD', 'EUR']),
        f('period', 'Periodicidad', 'select', true, o.periods),
      ],
    ],
    [
      'Documentación y observaciones',
      [f('document', 'Contrato firmado PDF', 'pdf'), f('notes', 'Observaciones', 'textarea')],
    ],
  ];
}
function crValue(d, key) {
  return key.split('.').reduce((v, k) => v?.[k], d) ?? '';
}
function crSet(d, key, value) {
  const parts = key.split('.');
  if (parts.length === 2) {
    d[parts[0]] ||= {};
    d[parts[0]][parts[1]] = value;
  } else d[key] = value;
}
function crCuit(value) {
  const v = String(value).replace(/[-\s]/g, '');
  if (!/^\d{11}$/.test(v) || new Set(v).size === 1) return false;
  let n = 11 - ([5, 4, 3, 2, 7, 6, 5, 4, 3, 2].reduce((s, w, i) => s + Number(v[i]) * w, 0) % 11);
  return (n === 11 ? 0 : n === 10 ? 9 : n) === Number(v[10]);
}
function crValidate() {
  if (!crm.form) return {};
  const { kind, d } = crm.form,
    errors = {};
  for (const [, fields] of crSchemas(kind, d))
    for (const f of fields) {
      const v = crValue(d, f.key);
      if (f.required && (!String(v).trim() || (Array.isArray(v) && !v.length)))
        errors[f.key] = 'Este campo es obligatorio.';
      if (f.type === 'email' && v && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v))
        errors[f.key] = 'Ingresá un correo válido.';
      if (
        ['text', 'textarea', 'tel', 'email'].includes(f.type) &&
        String(v).length > (f.key === 'notes' ? 4000 : f.key === 'description' ? 2000 : 250)
      )
        errors[f.key] = 'El texto supera la longitud permitida.';
    }
  if (kind === 'clients') {
    if (!crCuit(d.cuit)) errors.cuit = 'Ingresá un CUIT válido de 11 dígitos.';
    if (
      crm.data.clients.some(
        (c) => c.id !== d.id && c.cuit && c.cuit === String(d.cuit).replace(/[-\s]/g, ''),
      )
    )
      errors.cuit = 'Ya existe un cliente con este CUIT.';
    if (d.since && d.since > crm.today) errors.since = 'La fecha no puede ser futura.';
  }
  if (kind === 'contracts') {
    if (d.end && d.start && d.end < d.start)
      errors.end = 'El vencimiento no puede ser anterior al inicio.';
    if (d.signed && d.signed > crm.today) errors.signed = 'La fecha de firma no puede ser futura.';
    if (
      d.amount !== '' &&
      (!Number.isFinite(Number(d.amount)) ||
        Number(d.amount) < 0 ||
        !/^\d+(\.\d{1,2})?$/.test(String(d.amount)))
    )
      errors.amount = 'Ingresá un importe positivo con hasta dos decimales.';
    if (
      crm.data.contracts.some(
        (c) => c.id !== d.id && c.number.toLowerCase() === d.number?.trim().toLowerCase(),
      )
    )
      errors.number = 'El número de contrato ya existe.';
  }
  if (
    kind === 'catalog' &&
    crm.data.catalog.some(
      (p) => p.id !== d.id && p.name.toLowerCase() === d.name?.trim().toLowerCase(),
    )
  )
    errors.name = 'Este nombre ya existe en el catálogo.';
  if (
    d.id &&
    ['clients', 'contracts'].includes(kind) &&
    d.status === 'Finalizado' &&
    crm.data[kind].find((r) => r.id === d.id)?.status !== 'Finalizado' &&
    !d.confirm
  )
    errors.confirm = 'Confirmá la finalización para guardar.';
  return { ...errors, ...crm.errors };
}
function crInput(f, d) {
  const value = crValue(d, f.key),
    id = 'cf-' + f.key.replaceAll('.', '-'),
    common = `id="${id}" data-crm-field="${f.key}" aria-describedby="${id}-error" ${f.required ? 'required' : ''}`,
    opts = f.options.map((v) => (Array.isArray(v) ? v : [v, v]));
  let input;
  if (f.type === 'select')
    input = `<select ${common} ${crm.form.kind === 'subscriptions' && d.id && f.key === 'productId' ? 'disabled' : ''}><option value="">Seleccionar…</option>${opts.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(value) ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
  else if (['textarea', 'lines'].includes(f.type))
    input = `<textarea ${common} rows="${f.type === 'lines' ? 5 : 4}">${esc(Array.isArray(value) ? value.join('\n') : value)}</textarea>`;
  else if (f.type === 'checkbox')
    input = `<input ${common} type="checkbox" ${value ? 'checked' : ''}>`;
  else if (f.type === 'multi')
    input = `<div id="${id}" class="crm-checks" role="group" aria-labelledby="${id}-label">${opts.map(([v, l]) => `<label><input type="checkbox" data-crm-multi="${f.key}" value="${esc(v)}" ${(value || []).includes(v) ? 'checked' : ''}>${esc(l)}</label>`).join('') || '<p class="sub">No hay opciones disponibles.</p>'}</div>`;
  else if (['image', 'pdf'].includes(f.type))
    input = `${f.type === 'image' ? personImage({ name: d.name, logo: value }, 'large', 'company') : d.document ? crDocument(d) : ''}<input ${common} type="file" accept="${f.type === 'pdf' ? '.pdf,application/pdf' : 'image/png,image/jpeg,image/webp'}"><small>${f.type === 'pdf' ? 'PDF sin contraseña · hasta 10 MB' : 'PNG, JPEG o WebP · hasta 3 MB. Se conserva el archivo original.'}</small>`;
  else
    input = `<input ${common} type="${f.type}" value="${esc(value)}" ${f.type === 'number' ? 'min="0" step="0.01" inputmode="decimal"' : ''}>`;
  return `<div class="crm-field ${['textarea', 'multi', 'lines', 'pdf', 'image'].includes(f.type) ? 'crm-wide' : ''}">${f.type === 'multi' ? `<span id="${id}-label">${f.label}${f.required ? ' *' : ''}</span>` : `<label for="${id}">${f.label}${f.required ? ' *' : ''}</label>`}${input}<small class="field-error" id="${id}-error" aria-live="polite"></small></div>`;
}
function crFormPage() {
  const { kind, d } = crm.form,
    sections = crSchemas(kind, d),
    titles = {
      clients: 'cliente',
      contacts: 'contacto',
      catalog: 'producto o servicio',
      subscriptions: 'contratación',
      contracts: 'contrato',
    };
  crm.step = Math.min(crm.step, sections.length - 1);
  const section = sections[crm.step];
  return `${crButton('← Volver sin guardar', 'cancel-form')}<div class="crm-section-head"><div><p class="eyebrow">CLIENTES / GESTIÓN COMERCIAL</p><h1>${d.id ? 'Editar' : 'Nuevo'} ${titles[kind]}</h1><p class="sub">${kind === 'clients' ? 'Los productos y contratos se gestionan después del alta.' : kind === 'catalog' ? 'Catálogo compartido por todas las organizaciones.' : esc(cr(d.clientId)?.name || '')}</p></div></div><form id="crm-form" novalidate class="crm-form-shell"><nav class="crm-steps" aria-label="Secciones del formulario">${sections.map(([s], i) => `<button type="button" data-crm="step" data-id="${i}" ${crm.step === i ? 'aria-current="step"' : ''}><span>${i + 1}</span>${s}</button>`).join('')}</nav><div class="crm-form-content"><p class="sub">Los campos con * son obligatorios.</p><h2>${section[0]}</h2><div class="crm-form-grid">${section[1].map((f) => crInput(f, d)).join('')}</div>${d.id && ['clients', 'contracts'].includes(kind) && d.status === 'Finalizado' && crm.data[kind].find((r) => r.id === d.id)?.status !== 'Finalizado' ? `<label class="crm-confirm"><input type="checkbox" data-crm-field="confirm" ${d.confirm ? 'checked' : ''}>Confirmo finalizar la relación y conservar todo el historial.</label><small id="cf-confirm-error" class="field-error"></small>` : ''}<p id="crm-form-error" class="field-error" role="alert"></p></div><div class="crm-form-footer"><span id="crm-save-hint" role="status"></span><div class="crm-actions">${crButton('Cancelar', 'cancel-form')}${crm.step < sections.length - 1 ? crButton('Siguiente sección', 'step', crm.step + 1) : ''}<button type="submit" class="button primary" id="crm-save">Guardar ${titles[kind]}</button></div></div></form>`;
}
function crUpdateErrors() {
  if (!crm.form) return;
  const errors = crValidate();
  for (const [, fields] of crSchemas(crm.form.kind, crm.form.d))
    for (const f of fields) {
      const id = 'cf-' + f.key.replaceAll('.', '-'),
        el = document.getElementById(id),
        err = document.getElementById(id + '-error');
      if (err) err.textContent = crm.touched.has(f.key) ? errors[f.key] || '' : '';
      if (el) el.setAttribute('aria-invalid', String(crm.touched.has(f.key) && !!errors[f.key]));
    }
  const general = $('#crm-form-error');
  if (general) general.textContent = errors._form || '';
  const confirm = $('#cf-confirm-error');
  if (confirm) confirm.textContent = errors.confirm || '';
  const save = $('#crm-save');
  if (save) {
    save.disabled = crm.busy || Object.keys(errors).length > 0;
    save.textContent = crm.busy
      ? 'Guardando…'
      : `Guardar ${{ clients: 'cliente', contacts: 'contacto', catalog: 'producto o servicio', subscriptions: 'contratación', contracts: 'contrato' }[crm.form.kind]}`;
  }
  const hint = $('#crm-save-hint');
  if (hint)
    hint.textContent = crm.busy
      ? 'Procesando…'
      : Object.keys(errors).length
        ? 'Completá y revisá los campos de todas las secciones.'
        : 'Listo para guardar.';
  document
    .querySelectorAll('#crm-form input,#crm-form select,#crm-form textarea,#crm-form button')
    .forEach((el) => {
      if (crm.busy) el.disabled = true;
    });
}
function crOpenForm(kind, id) {
  const old = crm.data[kind].find((r) => r.id === Number(id)),
    defaults = {
      clients: {
        country: 'Argentina',
        status: 'Prospecto',
        logo: ASSETS.company,
        primaryContact: {},
      },
      contacts: { clientId: crm.id, status: LABOR.ACTIVE, principal: false },
      catalog: { type: 'Producto de software', status: LABOR.ACTIVE, plans: [], configFields: [] },
      subscriptions: { clientId: crm.id, status: 'Implementación', configuration: [], plan: '' },
      contracts: {
        clientId: crm.id,
        status: 'Borrador',
        renewal: 'Manual',
        period: 'Mensual',
        currency: 'ARS',
        amount: '',
        subscriptionIds: [],
        document: '',
      },
    };
  crm.form = { kind, d: structuredClone(old || defaults[kind]), returnView: crm.view };
  crm.step = 0;
  crm.errors = {};
  crm.touched = new Set();
  crm.view = 'form';
  render();
  document.querySelector('.crm-form-content input,.crm-form-content select')?.focus();
}
clientsPage = function () {
  if (state.role !== 'admin' && !employeePermission('crm'))
    return heading('Clientes', 'Acceso no disponible para este perfil.');
  let html;
  if (!crm.loaded)
    html =
      heading('Clientes', 'Instituciones y organizaciones vinculadas a VitaDev.') +
      `${crm.error ? visualState('error', crButton('Reintentar', 'retry')) : '<p role="status">Cargando clientes…</p>'}`;
  else
    html =
      crm.view === 'form'
        ? crFormPage()
        : crm.view === 'profile'
          ? crProfile()
          : crm.view === 'catalog'
            ? crCatalog()
            : crList();
  return `<div class="crm-module">${html}</div>`;
};
const oldCrDetail = clientDetail;
clientDetail = function (id) {
  if (state.role !== 'admin' && !employeePermission('crm')) return oldCrDetail(id);
  crm.id = Number(id);
  crm.view = 'profile';
  crm.tab = 'Resumen';
  state.page = 'clients';
  render();
  window.scrollTo(0, 0);
};
const oldCrAction = action;
action = function (value) {
  if (value === 'new-client' && state.role === 'admin') {
    if (crm.loaded) {
      state.page = 'clients';
      crOpenForm('clients');
    } else toast('Esperá a que cargue Clientes.');
    return;
  }
  oldCrAction(value);
};
products = function () {
  if ((state.role === 'admin' || employeePermission('crm')) && crm.loaded)
    return `<div class="crm-module">${crCatalog()}</div>`;
  return (
    heading('Productos y servicios', 'Servicios contratados por la institución.') +
    (crm.loaded
      ? crTable(
          ['Producto', 'Estado'],
          crm.data.subscriptions
            .filter((s) => s.clientId === 1)
            .map(
              (s) =>
                `<tr><td>${esc(crProduct(s.productId)?.name)}</td><td>${esc(s.status)}</td></tr>`,
            ),
        )
      : '<p>Cargando servicios…</p>')
  );
};
const oldCrRender = render;
render = function () {
  oldCrRender();
  if (state.page === 'clients' && state.role === 'admin') {
    $('footer span').textContent = 'Clientes · Guardado persistente en este equipo';
    if (crm.view === 'form') crUpdateErrors();
  }
};
const crDialog = document.createElement('dialog');
crDialog.id = 'crm-confirm-dialog';
crDialog.setAttribute('aria-labelledby', 'crm-confirm-title');
document.body.appendChild(crDialog);
let crPending = null,
  crReturnFocus = null;
function crConfirm(kind, id) {
  const r = crm.data[kind].find((r) => r.id === Number(id));
  if (!r) return;
  crReturnFocus = document.activeElement;
  crPending = { kind, r };
  crDialog.innerHTML = `<h2 id="crm-confirm-title">${kind === 'contacts' ? 'Desactivar contacto' : kind === 'contracts' ? 'Finalizar contrato' : 'Finalizar relación comercial'}</h2><p>${esc(r.name || r.number || r.firstName + ' ' + r.lastName)}</p><p>Se conservarán todos los registros y el historial.${kind === 'clients' ? ' Los contratos y contrataciones conservarán sus estados; revisalos por separado.' : ''}</p><p class="field-error" role="alert" id="crm-confirm-error"></p><div class="crm-actions"><button class="button" data-crm="close-confirm">Cancelar</button><button class="button primary" data-crm="confirm-finish">Confirmar</button></div>`;
  crDialog.showModal();
}
const CR_KIND_LABELS = {
  clients: 'cliente',
  contacts: 'contacto',
  catalog: 'producto/servicio',
  subscriptions: 'contratación',
  contracts: 'contrato',
};
// Advertencia previa: resumen de lo que se crea (con sus consecuencias) o confirmación de edición.
function crConfirmSave(kind, d) {
  const label = CR_KIND_LABELS[kind],
    client = cr(d.clientId)?.name,
    name =
      d.name ||
      d.number ||
      (d.firstName ? d.firstName + ' ' + d.lastName : '') ||
      crProduct(d.productId)?.name ||
      label;
  const previous = d.id ? crm.data[kind]?.find((r) => r.id === d.id) : null;
  const finishing = d.status === 'Finalizado' && previous?.status !== 'Finalizado';
  if (d.id)
    return confirmAction({
      tone: finishing ? 'danger' : 'warning',
      title: finishing ? `¿Finalizar ${name}?` : '¿Guardar los cambios?',
      message: finishing
        ? 'Quedará registrado como finalizado y no admitirá nuevas relaciones comerciales.'
        : `Se actualizará ${label === 'contratación' ? 'la' : 'el'} ${label} ${name}.`,
      notes:
        kind === 'contacts' && d.principal
          ? ['Pasará a ser el contacto principal: el anterior dejará de serlo.']
          : [],
      confirmLabel: finishing ? 'Sí, finalizar' : 'Sí, guardar',
    });
  const details = {
    clients: [
      ['Razón social', d.legalName],
      ['CUIT', d.cuit],
      ['Estado', d.status],
      ['Responsable', crEmployee(d.owner)?.name],
      [
        'Contacto principal',
        [d.primaryContact?.firstName, d.primaryContact?.lastName].join(' ').trim(),
      ],
    ],
    contacts: [
      ['Cliente', client],
      ['Correo', d.email],
      ['Cargo', d.position],
    ],
    catalog: [
      ['Tipo', d.type],
      ['Planes', (d.plans || []).join(', ')],
    ],
    subscriptions: [
      ['Cliente', client],
      ['Plan', d.plan],
      ['Inicio', crDate(d.start)],
      ['Estado', d.status],
    ],
    contracts: [
      ['Cliente', client],
      ['Vigencia', crDate(d.start) + ' → ' + crDate(d.end)],
      ['Importe', d.amount === '' ? '' : `${d.currency} ${d.amount}`],
      ['Renovación', d.renewal],
    ],
  }[kind];
  const notes = {
    clients: ['El CUIT no podrá repetirse en otro cliente.'],
    contacts: d.principal ? ['Será el contacto principal del cliente.'] : [],
    catalog: ['Los planes y opciones que usen contrataciones no podrán quitarse después.'],
    subscriptions: ['El producto de una contratación no puede cambiarse una vez creada.'],
    contracts: [
      'El cliente del contrato no puede cambiarse después.',
      ...(d.document ? [] : ['No adjuntaste el PDF del contrato.']),
    ],
  }[kind];
  return confirmAction({
    title: `¿Crear ${label === 'contratación' ? 'la' : 'el'} ${label} ${name}?`,
    message: 'Revisá los datos antes de registrarlo.',
    details,
    notes,
    confirmLabel: 'Sí, crear',
  });
}
async function crSave() {
  if (crm.busy || Object.keys(crValidate()).length) return;
  if (!(await crConfirmSave(crm.form.kind, crm.form.d))) return;
  crm.busy = true;
  crUpdateErrors();
  const { kind, d } = crm.form;
  try {
    const result = await crApi('/' + kind + (d.id ? '/' + d.id : ''), d, d.id ? 'PUT' : 'POST');
    const wasEdit = !!d.id;
    crm.busy = false;
    crm.form = null;
    crm.id = kind === 'clients' ? result.record.id : d.clientId || crm.id;
    crm.view = kind === 'catalog' ? 'catalog' : 'profile';
    crm.tab =
      {
        clients: 'Resumen',
        contacts: 'Contactos',
        subscriptions: 'Productos y servicios',
        contracts: 'Contratos',
      }[kind] || 'Resumen';
    await crLoad(false);
    render();
    const title = {
      clients: 'Cliente',
      contacts: 'Contacto',
      catalog: 'Producto/servicio',
      subscriptions: 'Contratación',
      contracts: 'Contrato',
    }[kind];
    const female = kind === 'subscriptions';
    if (wasEdit) toast(`${title} ${female ? 'actualizada' : 'actualizado'} correctamente`);
    else if (kind === 'clients' || kind === 'contracts')
      celebrate(`¡${title} ${female ? 'creada' : 'creado'}!`, 'Ya podés verlo en su ficha.');
    else toast(`${title} ${female ? 'creada' : 'creado'} correctamente`);
  } catch (e) {
    crm.busy = false;
    if (e.status === 409) await crLoad(false);
    crm.errors = e.errors || { _form: 'No se pudo guardar. Volvé a intentar.' };
    Object.keys(crm.errors).forEach((k) => crm.touched.add(k));
    const sections = crSchemas(kind, d),
      bad = sections.findIndex(([, fields]) => fields.some((f) => crm.errors[f.key]));
    if (bad >= 0) crm.step = bad;
    render();
  }
}
function crExport() {
  const list = crm.data.clients.filter(
    (c) =>
      [c.name, c.legalName, c.cuit, c.city, c.province]
        .join(' ')
        .toLocaleLowerCase('es')
        .includes(crm.query.toLocaleLowerCase('es')) &&
      (!crm.status || c.status === crm.status) &&
      (!crm.owner || c.owner === +crm.owner) &&
      (!crm.product || crRelated('subscriptions', c.id).some((s) => s.productId === +crm.product)),
  );
  const cell = (v) =>
    '"' +
    String(v ?? '')
      .replace(/^[=+@\t\r-]/, "'$&")
      .replaceAll('"', '""') +
    '"';
  const lines = [
    [
      'Cliente',
      'Razón social',
      'CUIT',
      'Ciudad',
      'Provincia',
      'Estado',
      'Responsable',
      'Próxima renovación',
    ],
    ...list.map((c) => [
      c.name,
      c.legalName,
      c.cuit,
      c.city,
      c.province,
      c.status,
      crEmployee(c.owner)?.name,
      crRenewal(c.id),
    ]),
  ];
  const url = URL.createObjectURL(
    new Blob(['\uFEFF' + lines.map((r) => r.map(cell).join(';')).join('\r\n')], {
      type: 'text/csv;charset=utf-8',
    }),
  );
  const a = document.createElement('a');
  a.href = url;
  a.download = 'clientes-vitadev.csv';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
document.addEventListener('click', async (event) => {
  const b = event.target.closest('[data-crm]');
  if (!b || (state.role !== 'admin' && !employeePermission('crm'))) return;
  event.preventDefault();
  if (crm.busy) return;
  const op = b.dataset.crm,
    id = Number(b.dataset.id);
  if (op.startsWith('new-') || op.startsWith('edit-')) {
    state.page = 'clients';
    crOpenForm(op.slice(op.indexOf('-') + 1), op.startsWith('edit-') ? id : null);
    return;
  }
  if (op.startsWith('finish-')) {
    crConfirm(op.slice(7), id);
    return;
  }
  switch (op) {
    case 'list':
      crm.view = 'list';
      crm.form = null;
      state.page = 'clients';
      render();
      break;
    case 'profile':
      clientDetail(id);
      break;
    case 'catalog':
      crm.view = 'catalog';
      state.page = 'clients';
      render();
      break;
    case 'tab':
      crm.tab = crmTabs[id];
      render();
      document.querySelector('.crm-tabs [aria-selected="true"]')?.focus();
      break;
    case 'step':
      crm.step = id;
      render();
      break;
    case 'cancel-form':
      crm.view = crm.form.returnView;
      crm.form = null;
      render();
      break;
    case 'clear':
      crm.query = crm.status = crm.product = crm.owner = '';
      render();
      break;
    case 'retry':
      await crLoad();
      break;
    case 'export':
      crExport();
      break;
    case 'close-confirm':
      crDialog.close();
      crReturnFocus?.focus();
      break;
    case 'confirm-finish': {
      crm.busy = true;
      b.disabled = true;
      const { kind, r } = crPending;
      try {
        await crApi(
          '/' + kind + '/' + r.id,
          {
            ...r,
            status: kind === 'contacts' ? LABOR.INACTIVE : 'Finalizado',
            confirm: true,
            lifecycle: true,
          },
          'PUT',
        );
        await crLoad(false);
        crDialog.close();
        render();
        toast('Estado actualizado. El historial se conserva.');
      } catch (e) {
        $('#crm-confirm-error').textContent = Object.values(
          e.errors || { _form: 'No se pudo guardar.' },
        ).join(' ');
        b.disabled = false;
      }
      crm.busy = false;
      break;
    }
    case 'principal': {
      const p = crm.data.contacts.find((p) => p.id === id);
      crm.busy = true;
      try {
        await crApi('/contacts/' + id, { ...p, principal: true }, 'PUT');
        await crLoad(false);
        render();
        toast('Contacto principal actualizado');
      } catch (e) {
        toast(Object.values(e.errors || { _form: 'No se pudo actualizar.' }).join(' '));
      }
      crm.busy = false;
      break;
    }
  }
});
function crRead(el) {
  if (!crm.form) return;
  const key = el.dataset.crmField;
  if (!key || el.type === 'file') return;
  let value = el.type === 'checkbox' ? el.checked : el.value;
  if (['owner', 'productId', 'clientId'].includes(key)) value = value ? Number(value) : '';
  if (['plans', 'configFields'].includes(key))
    value = value
      .split('\n')
      .map((v) => v.trim())
      .filter(Boolean);
  crSet(crm.form.d, key, value);
  delete crm.errors[key];
  delete crm.errors._form;
  crm.touched.add(key);
  if (key === 'productId') {
    crm.form.d.plan = '';
    crm.form.d.configuration = [];
    render();
  } else if (key === 'status' && ['clients', 'contracts'].includes(crm.form.kind)) {
    crm.form.d.confirm = false;
    render();
  } else crUpdateErrors();
}
document.addEventListener('input', (event) => {
  const el = event.target;
  if (el.id === 'crm-search') {
    const p = el.selectionStart;
    crm.query = el.value;
    render();
    $('#crm-search').focus();
    $('#crm-search').setSelectionRange(p, p);
  }
  if (el.dataset.crmField && el.type !== 'checkbox' && el.tagName !== 'SELECT') crRead(el);
});
document.addEventListener('change', async (event) => {
  const el = event.target;
  if (el.dataset.crmFilter) {
    crm[el.dataset.crmFilter] = el.value;
    render();
  }
  if (el.dataset.crmMulti && crm.form) {
    const key = el.dataset.crmMulti;
    crm.form.d[key] = [...document.querySelectorAll(`[data-crm-multi="${key}"]:checked`)].map(
      (e) => (key === 'subscriptionIds' ? Number(e.value) : e.value),
    );
    delete crm.errors[key];
    crm.touched.add(key);
    crUpdateErrors();
  }
  if (el.dataset.crmField && el.type !== 'file') crRead(el);
  if (el.dataset.crmField && el.type === 'file' && el.files[0]) {
    const file = el.files[0],
      key = el.dataset.crmField;
    crm.busy = true;
    crUpdateErrors();
    try {
      const base64 = await new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result.split(',')[1]);
        r.onerror = reject;
        r.readAsDataURL(file);
      });
      const data = await crApi('/files', { name: file.name, kind: key, base64 });
      crm.form.d[key] = data.url;
      if (key === 'document') crm.form.d.documentName = data.name;
      delete crm.errors[key];
    } catch (e) {
      crm.errors[key] = Object.values(
        e.errors || { _form: 'No se pudo adjuntar el archivo.' },
      ).join(' ');
      crm.touched.add(key);
    }
    crm.busy = false;
    render();
  }
});
document.addEventListener('submit', (event) => {
  if (event.target.id === 'crm-form') {
    event.preventDefault();
    crSave();
  }
});
document.addEventListener('focusout', (event) => {
  if (event.target.dataset.crmField && crm.form) {
    crm.touched.add(event.target.dataset.crmField);
    crUpdateErrors();
  }
});
document.addEventListener('keydown', (event) => {
  if (
    event.target.matches('.crm-tabs [role="tab"]') &&
    ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)
  ) {
    event.preventDefault();
    let i = crmTabs.indexOf(crm.tab);
    i =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? 5
          : (i + (event.key === 'ArrowRight' ? 1 : 5)) % 6;
    crm.tab = crmTabs[i];
    render();
    document.querySelector('.crm-tabs [aria-selected="true"]')?.focus();
  }
  if (event.key === 'Escape')
    document.querySelectorAll('.crm-menu[open]').forEach((m) => (m.open = false));
});
crDialog.addEventListener('cancel', (event) => {
  if (crm.busy) event.preventDefault();
});
document.addEventListener(
  'toggle',
  (event) => {
    const menu = event.target;
    if (!menu.matches?.('.crm-menu') || !menu.open) return;
    document.querySelectorAll('.crm-menu[open]').forEach((m) => {
      if (m !== menu) m.open = false;
    });
    const p = menu.querySelector('div'),
      r = menu.getBoundingClientRect();
    p.style.left =
      Math.max(8, Math.min(r.right - p.offsetWidth, innerWidth - p.offsetWidth - 8)) + 'px';
    p.style.top = Math.max(8, Math.min(r.bottom + 5, innerHeight - p.offsetHeight - 8)) + 'px';
  },
  true,
);
document.addEventListener('click', (event) =>
  document.querySelectorAll('.crm-menu[open]').forEach((m) => {
    if (!m.contains(event.target)) m.open = false;
  }),
);
// Clic en cualquier parte de la fila abre la ficha (los controles internos mantienen su acción).
document.addEventListener('click', (event) => {
  const row = event.target.closest('[data-crm-row]');
  if (!row || event.target.closest('button, a, input, select, label, details')) return;
  row.querySelector('[data-crm="profile"]')?.click();
});
crLoad();
