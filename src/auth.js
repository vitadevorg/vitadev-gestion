// La identidad solo proviene de /api/auth/me. No hay tokens en localStorage.
let authSession = null,
  authLoaded = false;
const can = (permission) => !!authSession?.permissions.includes(permission);
const authFetch = window.fetch.bind(window);
window.fetch = async function (input, options = {}) {
  const url = new URL(typeof input === 'string' ? input : input.url, location.href);
  if (url.origin === location.origin && url.pathname.startsWith('/api/')) {
    const headers = new Headers(options.headers || {});
    if (authSession?.csrfToken) headers.set('X-CSRF-Token', authSession.csrfToken);
    options = { ...options, headers, cache: 'no-store' };
  }
  const response = await authFetch(input, options);
  if (response.status === 401 && authLoaded && url.pathname !== '/api/auth/login') {
    authSession = null;
    location.replace('/login');
  }
  return response;
};
const authEscape = (s) =>
  String(s ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
async function authRequest(path, data) {
  const response = await fetch(path, {
    method: data === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Nexo-Client': 'team' },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  const body = await response.json();
  if (!response.ok) throw body;
  return body;
}
function loginPage() {
  document.body.classList.add('auth-locked');
  document.querySelector('#auth-root').innerHTML =
    `<main class="login-panel"><div class="login-brand"><img src="assets/brand/vitadev-logo.png" alt="VitaDev"></div><h1>Bienvenido</h1><p>Accedé a tu espacio de trabajo.</p><form id="login-form" novalidate><label for="login-email">Correo electrónico *</label><input id="login-email" name="email" type="email" required autocomplete="username" aria-describedby="login-email-error"><small id="login-email-error" class="field-error"></small><label for="login-password">Contraseña *</label><div class="password-control"><input id="login-password" name="password" type="password" required maxlength="128" autocomplete="current-password" aria-describedby="login-password-error"><button type="button" id="login-reveal" aria-label="Mostrar contraseña" aria-pressed="false">Mostrar</button></div><small id="login-password-error" class="field-error"></small><label class="login-remember"><input id="login-remember" type="checkbox"> Recordarme</label><p id="login-error" class="field-error" role="alert"></p><button class="button primary" id="login-submit">Iniciar sesión</button><button class="link" id="login-forgot" type="button">¿Olvidaste tu contraseña?</button><p id="login-recovery" role="status"></p></form><small class="login-footer">Acceso seguro · VitaDev</small></main>`;
  document.querySelector('#login-reveal').onclick = (e) => {
    const input = document.querySelector('#login-password'),
      show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    e.target.textContent = show ? 'Ocultar' : 'Mostrar';
    e.target.setAttribute('aria-label', show ? 'Ocultar contraseña' : 'Mostrar contraseña');
    e.target.setAttribute('aria-pressed', String(show));
  };
  document.querySelector('#login-forgot').onclick = () =>
    (document.querySelector('#login-recovery').textContent =
      'La recuperación por correo no está disponible en este entorno. Contactá al administrador para gestionar tu acceso.');
  document.querySelector('#login-form').onsubmit = async (e) => {
    e.preventDefault();
    const email = document.querySelector('#login-email'),
      password = document.querySelector('#login-password'),
      button = document.querySelector('#login-submit');
    if (button.disabled) return;
    const emailError =
        !email.value.trim() || !email.validity.valid ? 'Ingresá un correo válido.' : '',
      passwordError = !password.value ? 'Ingresá tu contraseña.' : '';
    document.querySelector('#login-email-error').textContent = emailError;
    document.querySelector('#login-password-error').textContent = passwordError;
    if (emailError || passwordError) {
      (emailError ? email : password).focus();
      return;
    }
    button.disabled = true;
    button.textContent = 'Ingresando…';
    document.querySelector('#login-error').textContent = '';
    try {
      const result = await authRequest('/api/auth/login', {
        email: email.value.trim(),
        password: password.value,
        remember: document.querySelector('#login-remember').checked,
      });
      authSession = result.user;
      password.value = '';
      location.replace('/inicio');
    } catch (error) {
      document.querySelector('#login-error').textContent = Object.values(
        error.errors || { _form: 'No pudimos conectar con VitaDev. Intentá nuevamente.' },
      ).join(' ');
      button.disabled = false;
      button.textContent = 'Iniciar sesión';
    }
  };
  document.querySelector('#login-email').focus();
}
const privateRoutes = {
  inicio: 'home',
  equipo: 'employees',
  clientes: 'clients',
  solicitudes: 'support',
  licencias: 'calendar',
  reportes: 'reports',
  usuarios: 'users',
  tareas: 'tasks',
};
async function authStart() {
  try {
    authSession = (await authRequest('/api/auth/me')).user;
  } catch {
    loginPage();
    return;
  }
  const scripts = [
    'app.js',
    'employee.js',
    'interface.js',
    'team.js',
    'crm.js',
    'helpdesk.js',
    'leave.js',
    'reports.js',
    'users.js',
  ];
  try {
    for (const src of scripts)
      await new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src;
        script.onload = resolve;
        script.onerror = reject;
        document.body.append(script);
      });
    authLoaded = true;
    document.body.classList.remove('auth-locked');
    document.querySelector('#auth-root').innerHTML = '';
    state.page = privateRoutes[location.pathname.slice(1)] || 'home';
    render();
  } catch {
    document.querySelector('#auth-root').innerHTML =
      '<p>No se pudo iniciar VitaDev. Recargá la página para volver a intentar.</p>';
  }
}
window.addEventListener('pageshow', (e) => {
  if (e.persisted) location.reload();
});
window.addEventListener('focus', async () => {
  if (authLoaded) {
    try {
      authSession = (await authRequest('/api/auth/me')).user;
      render();
    } catch {
      location.replace('/login');
    }
  }
});
authStart();
