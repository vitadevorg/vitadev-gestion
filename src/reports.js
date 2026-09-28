/* Análisis de solo lectura. Una consulta y un período para toda la vista. */
const rp = {
  start: '',
  end: '',
  preset: '30',
  client: '',
  product: '',
  data: null,
  busy: false,
  error: '',
  sequence: 0,
  all: false,
};
const rpISO = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
function rpPeriod(p) {
  const end = new Date(),
    start = new Date();
  if (p === '7' || p === '30') start.setDate(start.getDate() - Number(p) + 1);
  if (p === 'month') start.setDate(1);
  if (p === 'previous') {
    start.setMonth(start.getMonth() - 1, 1);
    end.setDate(0);
  }
  rp.start = rpISO(start);
  rp.end = rpISO(end);
  rp.preset = p;
}
rpPeriod('30');
const rpQuery = () =>
  new URLSearchParams({
    start: rp.start,
    end: rp.end,
    ...(rp.client ? { client: rp.client } : {}),
    ...(rp.product ? { product: rp.product } : {}),
  });
const rpValid = () =>
  rp.start &&
  rp.end &&
  rp.start <= rp.end &&
  (new Date(rp.end) - new Date(rp.start)) / 86400000 <= 3652;
async function rpLoad() {
  if (!rpValid()) return;
  const n = ++rp.sequence;
  rp.busy = true;
  rp.error = '';
  render();
  try {
    const response = await fetch('/api/reports?' + rpQuery(), {
      headers: { 'X-Nexo-View': state.role },
    });
    const body = await response.json();
    if (!response.ok)
      throw Error(Object.values(body.errors || {}).join(' ') || 'No se pudo cargar el reporte.');
    if (n === rp.sequence) rp.data = body;
  } catch (e) {
    if (n === rp.sequence) {
      rp.error = e.message;
      rp.data = null;
    }
  } finally {
    if (n === rp.sequence) {
      rp.busy = false;
      if (state.page === 'reports') render();
    }
  }
}
const rpNumber = (v, suffix = '') =>
  v == null ? '—' : new Intl.NumberFormat('es-AR', { maximumFractionDigits: 1 }).format(v) + suffix;
const rpEmpty = () => '<p class="rp-empty">No hay datos suficientes para este período.</p>';
const rpRows = (rows) =>
  rows.length
    ? `<dl class="rp-rows">${rows.map(([name, value]) => `<div><dt>${esc(name)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>`
    : rpEmpty();
const rpBars = (rows) =>
  rows.length
    ? `<div class="rp-bars">${rows.map((r) => `<div><span>${esc(r.name)}</span><b>${r.value}${r.percent != null ? ` <small>(${rpNumber(r.percent, '%')})</small>` : ''}</b><meter min="0" max="${Math.max(1, ...rows.map((v) => v.value))}" value="${r.value}" aria-label="${esc(r.name)}"></meter></div>`).join('')}</div>`
    : rpEmpty();
function rpChart(r) {
  if (!r.series.some((b) => b.received || b.resolved)) return rpEmpty();
  const max = Math.max(1, ...r.series.flatMap((b) => [b.received, b.resolved])),
    w = 680 / r.series.length;
  return `<p class="sub">Azul: recibidas · Gris: resueltas · Agrupación por ${r.group}</p><svg class="rp-chart" viewBox="0 0 740 210" role="img" aria-label="Solicitudes recibidas y resueltas por ${r.group}">${[0, 0.5, 1].map((f) => `<line x1="40" y1="${175 - f * 140}" x2="730" y2="${175 - f * 140}" stroke="#dce3ec"/><text x="4" y="${180 - f * 140}">${rpNumber(max * f)}</text>`).join('')}${r.series.map((b, i) => `<g><title>${esc(b.start)} al ${esc(b.end)}: ${b.received} recibidas, ${b.resolved} resueltas</title>${['received', 'resolved'].map((key, j) => `<rect x="${45 + i * w + j * w * 0.38}" y="${175 - (b[key] / max) * 140}" width="${w * 0.3}" height="${(b[key] / max) * 140}" fill="${j ? '#9cafc9' : '#2865c7'}"/>`).join('')}${i % Math.max(1, Math.ceil(r.series.length / 9)) === 0 ? `<text x="${45 + i * w}" y="198">${b.label}</text>` : ''}</g>`).join('')}</svg><details><summary>Ver datos del gráfico</summary>${crTable(
    ['Período', 'Recibidas', 'Resueltas'],
    r.series.map(
      (b) =>
        `<tr><td>${esc(b.start)} al ${esc(b.end)}</td><td>${b.received}</td><td>${b.resolved}</td></tr>`,
    ),
  )}</details>`;
}
reports = function () {
  const r = rp.data,
    k = r?.kpis;
  return (
    heading(
      'Reportes',
      'Análisis de la operación y desempeño de VitaDev.',
      `<button class="button primary" data-rp="pdf" ${!r || rp.busy || !rpValid() ? 'disabled' : ''}>Exportar PDF</button>`,
    ) +
    `<div class="rp"><form id="rp-filter" class="rp-filter"><label>Período<select id="rp-preset">${[
      ['7', 'Últimos 7 días'],
      ['30', 'Últimos 30 días'],
      ['month', 'Este mes'],
      ['previous', 'Mes anterior'],
      ['custom', 'Personalizado'],
    ]
      .map(([v, t]) => `<option value="${v}" ${rp.preset === v ? 'selected' : ''}>${t}</option>`)
      .join(
        '',
      )}</select></label><label>Desde<input id="rp-start" type="date" required value="${rp.start}"></label><label>Hasta<input id="rp-end" type="date" required value="${rp.end}"></label><label>Cliente<select id="rp-client"><option value="">Todos los clientes</option>${crm.data.clients.map((c) => `<option value="${c.id}" ${rp.client == c.id ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select></label><label>Producto / servicio<select id="rp-product"><option value="">Todos los productos</option>${crm.data.catalog.map((c) => `<option value="${c.id}" ${rp.product == c.id ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select></label><button class="button" ${rp.busy || !rpValid() ? 'disabled' : ''}>Actualizar</button></form>${!rpValid() ? '<p class="rp-error" role="alert">Ingresá ambas fechas, en orden, para un período de hasta diez años.</p>' : ''}${rp.error ? `${visualState('error', '<button class="button" data-visual-retry="reports">Reintentar</button>')}` : ''}${rp.busy ? '<p role="status">Calculando reporte…</p>' : ''}${
      !r
        ? ''
        : `<p class="rp-scope">${esc(r.start)} al ${esc(r.end)} · ${esc(r.clientLabel)} · ${esc(r.productLabel)}</p><div class="rp-kpis">${[
            ['Clientes activos', k.active, '', null],
            ['Solicitudes recibidas', k.received, '', k.receivedChange],
            ['Tasa de resolución', k.rate, '%', k.rateChange],
            ['Tiempo medio de resolución', k.minutes, ' min', k.minutesChange],
          ]
            .map(
              ([title, value, unit, change], i) =>
                `<section><h2>${title}</h2><strong>${rpNumber(value, unit)}</strong><p>${change == null ? 'Sin datos comparativos' : `${change > 0 ? '+' : ''}${rpNumber(change, i === 1 ? '%' : i === 2 ? ' puntos' : ' min')} frente al período anterior`}</p></section>`,
            )
            .join(
              '',
            )}</div><section class="rp-section"><h2>Recibidas vs. resueltas</h2>${rpChart(r)}<p class="sub">${k.resolved} resueltas / ${k.received} recibidas. La resolución puede incluir pendientes de períodos anteriores.</p></section><div class="rp-grid"><section class="rp-section"><h2>Estado de solicitudes</h2><p class="sub">Estado al cierre de las ${r.activityCount} solicitudes con actividad en el período.</p>${rpRows(Object.entries(r.states))}</section><section class="rp-section"><h2>Solicitudes por producto / servicio</h2>${rpBars(r.products)}</section><section class="rp-section"><h2>Clientes con mayor actividad</h2>${rpRows((rp.all ? r.topClients : r.topClients.slice(0, 5)).map((c) => [c.name, c.value]))}${r.topClients.length > 5 ? `<button class="button" data-rp="all">${rp.all ? 'Ver principales' : 'Ver todos'}</button>` : ''}</section><section class="rp-section"><h2>Evolución de clientes</h2>${rpRows(
            [
              ['Registrados al inicio', rpNumber(r.clients.atStart)],
              ['Nuevos en el período', rpNumber(r.clients.new)],
              ['Activos al corte disponible', rpNumber(r.clients.active)],
            ],
          )}<p class="sub">No se reconstruyen estados comerciales sin historial.</p></section><section class="rp-section"><h2>Clientes por producto / servicio</h2>${rpBars(r.clientProducts)}</section><section class="rp-section"><h2>Disponibilidad del equipo</h2>${rpRows(Object.entries(r.availability))}<p class="sub">${r.snapshot ? 'Corte actual. Las licencias aprobadas vigentes determinan “De licencia”.' : 'Sin historial de disponibilidad para este cierre.'}</p></section></div><section class="rp-section"><h2>Carga operativa del equipo</h2><p class="sub">Trabajo activo asociado a solicitudes con actividad en el período. No representa productividad individual.</p>${
            r.team.length
              ? crTable(
                  ['Empleado', 'Solicitudes abiertas', 'Tareas activas'],
                  r.team.map(
                    (e) =>
                      `<tr><td>${crPerson(e.id)}</td><td>${e.support}</td><td>${e.tasks}</td></tr>`,
                  ),
                )
              : rpEmpty()
          }</section><section class="rp-section"><h2>Atención requerida</h2>${r.alerts.length ? r.alerts.map((a, i) => `<button class="rp-alert" data-rp="alert" data-index="${i}"><span>${esc(a.text)}</span><b>${a.count} →</b></button>`).join('') : `<p class="rp-empty">${r.snapshot ? 'No se detectan alertas con los datos y filtros disponibles.' : 'Las alertas operativas requieren un período que incluya hoy.'}</p>`}</section><details class="rp-method"><summary>Alcance y calidad de los datos</summary><p>${r.imported} solicitudes importadas con actividad. Comparación: ${r.previousStart} al ${r.previousEnd}.</p>${r.notes.map((n) => `<p>${esc(n)}</p>`).join('')}</details>`
    }</div>`
  );
};
document.addEventListener('change', (e) => {
  if (!e.target.closest('#rp-filter')) return;
  const key = e.target.id.replace('rp-', '');
  if (key === 'preset') {
    if (e.target.value !== 'custom') rpPeriod(e.target.value);
    else rp.preset = 'custom';
  } else {
    rp[key] = e.target.value;
    if (key === 'start' || key === 'end') rp.preset = 'custom';
  }
  ++rp.sequence;
  rp.busy = false;
  rp.data = null;
  render();
  if (rpValid() && !rp.busy) rpLoad();
});
document.addEventListener('submit', (e) => {
  if (e.target.id === 'rp-filter') {
    e.preventDefault();
    rpLoad();
  }
});
document.addEventListener('click', async (e) => {
  const b = e.target.closest('[data-rp]');
  if (!b) return;
  const op = b.dataset.rp;
  if (op === 'all') {
    rp.all = !rp.all;
    render();
  }
  if (op === 'alert') {
    const a = rp.data.alerts[Number(b.dataset.index)];
    if (a.module === 'calendar') nav('calendar');
    else {
      const d = document.createElement('dialog');
      d.className = 'rp-drill';
      d.innerHTML = `<h2>${esc(a.text)}</h2>${a.ids.map((id) => `<button class="button" data-request="${id}">Ver solicitud #${id}</button>`).join('')}<form method="dialog"><button class="button">Cerrar</button></form>`;
      document.body.append(d);
      d.addEventListener('click', (e) => {
        if (e.target.dataset.request) {
          d.close();
          hdShow(e.target.dataset.request);
        }
      });
      d.addEventListener('close', () => d.remove());
      d.showModal();
    }
  }
  if (op === 'pdf') {
    b.disabled = true;
    try {
      const response = await fetch('/api/reports/pdf?' + rpQuery(), {
        headers: { 'X-Nexo-View': 'admin' },
      });
      if (!response.ok) throw Error();
      const url = URL.createObjectURL(await response.blob()),
        a = document.createElement('a');
      a.href = url;
      a.download = `VitaDev-Nexo-${rp.start}-${rp.end}.pdf`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast('Reporte PDF generado.');
    } catch {
      toast('No se pudo exportar el PDF. Volvé a intentar.');
    } finally {
      b.disabled = false;
    }
  }
});
const rpBaseRender = render;
render = function () {
  rpBaseRender();
  if (
    state.page === 'reports' &&
    can('reports.view') &&
    !rp.data &&
    !rp.busy &&
    !rp.error &&
    rpValid()
  )
    rpLoad();
};
if (state.page === 'reports') render();

document.addEventListener('nexo:data-changed', () => {
  rp.data = null;
});
