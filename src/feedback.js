// Retroalimentación de interfaz compartida por todos los módulos, con el lenguaje visual de SAMSA:
// avisos con ícono y color, confirmaciones antes de crear o modificar, celebración de altas y
// progreso visible mientras se guardan cambios. Se carga después de app.js y reemplaza toast().

const FEEDBACK_ICONS = {
  success: '<path d="M20 6 9 17l-5-5"/>',
  warning:
    '<path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>',
  danger:
    '<path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>',
  error: '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
};
const SUCCESS_DURATION_MS = 2500;
const feedbackIcon = (kind) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${FEEDBACK_ICONS[kind] || FEEDBACK_ICONS.info}</svg>`;

// ---------- Avisos (toasts) ----------
const feedbackStack = document.createElement('div');
feedbackStack.className = 'fb-stack';
feedbackStack.setAttribute('aria-live', 'polite');
document.body.append(feedbackStack);

function notify(kind, title, message = '') {
  const item = document.createElement('div');
  item.className = 'fb-toast fb-' + kind;
  item.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  item.innerHTML = `<span class="fb-toast-icon">${feedbackIcon(kind)}</span><div><strong>${esc(title)}</strong>${message ? `<p>${esc(message)}</p>` : ''}</div><button type="button" class="fb-toast-close" aria-label="Cerrar aviso">×</button>`;
  const remove = () => {
    item.classList.add('fb-leaving');
    setTimeout(() => item.remove(), 200);
  };
  item.querySelector('button').onclick = remove;
  feedbackStack.append(item);
  while (feedbackStack.children.length > 3) feedbackStack.firstElementChild.remove();
  setTimeout(remove, kind === 'error' ? 7000 : 4500);
}

// Compatibilidad con las llamadas existentes: el tipo se deduce del texto si no se indica.
toast = function (msg, kind) {
  const text = String(msg ?? '');
  kind ||= /^(No se pudo|Error|No tenés)/i.test(text)
    ? 'error'
    : /^(Esperá|Cargando)/i.test(text)
      ? 'info'
      : 'success';
  notify(kind, text);
};

// ---------- Confirmaciones ----------
// tone: 'warning' (crear/modificar, naranja en SAMSA), 'danger' (irreversible, rojo), 'info'.
// details: [etiqueta, valor] que resumen lo que se va a guardar; notes: advertencias a tener en cuenta.
// irreversible: solo para acciones que de verdad no pueden revertirse desde la aplicación.
function confirmAction({
  tone = 'warning',
  title,
  message = '',
  details = [],
  notes = [],
  confirmLabel = 'Confirmar',
  cancelLabel = 'Revisar',
  irreversible = false,
}) {
  return new Promise((resolve) => {
    const returnFocus = document.activeElement;
    const dialog = document.createElement('dialog');
    dialog.className = 'fb-confirm fb-' + tone;
    dialog.setAttribute('aria-labelledby', 'fb-confirm-title');
    const rows = details.filter(
      ([, value]) => value !== undefined && value !== null && value !== '',
    );
    dialog.innerHTML = `<div class="fb-confirm-icon">${feedbackIcon(tone)}</div><h2 id="fb-confirm-title">${esc(title)}</h2>${irreversible ? '<p class="fb-irreversible">Esta acción no se puede deshacer</p>' : ''}${message ? `<p class="fb-confirm-message">${esc(message)}</p>` : ''}${rows.length ? `<dl class="fb-summary">${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>` : ''}${notes.length ? `<ul class="fb-notes">${notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul>` : ''}<div class="fb-confirm-actions"><button type="button" class="button" data-fb="cancel">${esc(cancelLabel)}</button><button type="button" class="button fb-confirm-go" data-fb="ok">${esc(confirmLabel)}</button></div>`;
    const finish = (value) => {
      dialog.classList.add('fb-leaving');
      setTimeout(() => {
        dialog.close();
        dialog.remove();
        if (returnFocus?.isConnected) returnFocus.focus();
      }, 150);
      resolve(value);
    };
    dialog.addEventListener('cancel', (e) => {
      e.preventDefault();
      finish(false);
    });
    dialog.addEventListener('click', (e) => {
      if (e.target === dialog) finish(false);
      const op = e.target.closest('[data-fb]')?.dataset.fb;
      if (op) finish(op === 'ok');
    });
    document.body.append(dialog);
    dialog.showModal();
    // En acciones irreversibles el foco inicial queda en la opción segura.
    dialog.querySelector(tone === 'danger' ? '[data-fb=cancel]' : '[data-fb=ok]').focus();
  });
}

// ---------- Celebración de altas (SuccessModal de SAMSA) ----------
function celebrate(title, message = '') {
  const dialog = document.createElement('dialog');
  dialog.className = 'fb-celebrate';
  dialog.setAttribute('aria-labelledby', 'fb-celebrate-title');
  dialog.innerHTML = `<div class="fb-confirm-icon fb-check">${feedbackIcon('success')}</div><h2 id="fb-celebrate-title">${esc(title)}</h2>${message ? `<p>${esc(message)}</p>` : ''}`;
  const close = () => {
    if (!dialog.isConnected) return;
    dialog.classList.add('fb-leaving');
    setTimeout(() => {
      dialog.close();
      dialog.remove();
    }, 150);
  };
  dialog.addEventListener('click', close);
  dialog.addEventListener('cancel', close);
  document.body.append(dialog);
  dialog.showModal();
  setTimeout(close, SUCCESS_DURATION_MS);
}

// ---------- Progreso de guardado ----------
// auth.js llama a uiProgress.start() en cada escritura a /api/; el botón que la originó muestra
// un spinner y un indicador global informa qué se está haciendo.
const uiProgress = (() => {
  const bar = document.createElement('div');
  bar.className = 'fb-progress';
  bar.innerHTML =
    '<div class="fb-progress-bar"></div><div class="fb-progress-pill" role="status"><span class="fb-spinner" aria-hidden="true"></span><span class="fb-progress-text"></span></div>';
  document.body.append(bar);
  const text = bar.querySelector('.fb-progress-text');
  let active = 0,
    lastButton = null,
    lastButtonAt = 0,
    slowTimer,
    showTimer;
  // Recuerda el botón que disparó la acción (clic o Enter en un formulario).
  document.addEventListener(
    'click',
    (e) => {
      const b = e.target.closest('button');
      if (b) {
        lastButton = b;
        lastButtonAt = Date.now();
      }
    },
    true,
  );
  document.addEventListener(
    'submit',
    (e) => {
      const b = e.submitter || e.target.querySelector('[type=submit]');
      if (b) {
        lastButton = b;
        lastButtonAt = Date.now();
      }
    },
    true,
  );
  const labelFor = (path, method) => {
    if (/\/(files|photos)$/.test(path)) return 'Subiendo archivo…';
    if (path.endsWith('/pdf')) return 'Generando PDF…';
    if (path.endsWith('/approve')) return 'Aprobando solicitud…';
    if (path.endsWith('/reject')) return 'Rechazando solicitud…';
    if (path.endsWith('/cancel')) return 'Cancelando solicitud…';
    if (path.endsWith('/deactivate')) return 'Desactivando…';
    if (method === 'PUT' || /\/(update|task-status)$/.test(path)) return 'Guardando cambios…';
    return 'Guardando…';
  };
  const warnUnload = (e) => {
    e.preventDefault();
    e.returnValue = '';
  };
  function start(path, method) {
    const button = lastButton?.isConnected && Date.now() - lastButtonAt < 1500 ? lastButton : null;
    lastButton = null;
    if (button) {
      button.classList.add('is-busy');
      button.setAttribute('aria-busy', 'true');
    }
    active++;
    text.textContent = labelFor(path, method);
    // Evita parpadeos en respuestas instantáneas; tras 8 s avisa que la conexión está lenta.
    clearTimeout(showTimer);
    showTimer = setTimeout(() => active && bar.classList.add('show'), 250);
    clearTimeout(slowTimer);
    slowTimer = setTimeout(() => {
      if (active) text.textContent = 'Sigue en curso… la conexión está más lenta de lo habitual.';
    }, 8000);
    if (active === 1) addEventListener('beforeunload', warnUnload);
    let finished = false;
    return () => {
      if (finished) return;
      finished = true;
      button?.classList.remove('is-busy');
      button?.removeAttribute('aria-busy');
      if (--active > 0) return;
      clearTimeout(showTimer);
      clearTimeout(slowTimer);
      bar.classList.remove('show');
      removeEventListener('beforeunload', warnUnload);
    };
  }
  return { start };
})();
