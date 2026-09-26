# VitaDev

Sistema local de gestión de empleados, clientes, solicitudes y licencias, con reportes y acceso por cuenta autenticada. Esta versión integra la segunda etapa: Login, sesiones, Usuarios y permisos. No incluye Portal Cliente.

## Puesta en marcha

1. Disponer de Node.js y Python 3.11 o superior en PATH.
2. Instalar dependencias: `python -m pip install -r src/backend/requirements.txt`.
3. Ejecutar `crear-administrador.cmd` una sola vez y definir el correo y la contraseña del primer administrador. No hay credenciales predeterminadas.
4. Ejecutar `iniciar-vitadev.cmd`. Construye el frontend e inicia `src/backend/auth_server.py`.
5. Abrir http://127.0.0.1:4173/login.

Desde Equipo se puede crear una cuenta vinculada al empleado. Crear un empleado no crea automáticamente credenciales. Los roles y permisos provienen de la cuenta, sin selector manual de vistas.

## Desarrollo y organización

Editar exclusivamente `src/`. `dist/` es salida generada por `node build.js`; el build verifica la sintaxis JavaScript. `desarrollar.cmd` observa cambios; el backend se inicia por separado.

- `src/backend/auth_server.py`: punto de entrada integrado.
- `src/backend/auth.py`, `src/access-policy.json`: identidad, sesiones y permisos.
- `src/auth.js`, `src/auth.css`, `src/users.js`: Login y gestión de acceso.
- `src/team.js`, `crm.js`, `helpdesk.js`, `leave.js`, `reports.js`: módulos existentes.
- `src/assets/`: logos y fotografías originales.
- `src/domain.json`: estados compartidos por frontend y backend.

Ver [informe de autenticación](src/backend/AUTHENTICATION.md) para rutas, permisos, archivos modificados, pruebas y límites. No iniciar servidores antiguos por separado ni usar un servidor estático para operar los módulos.

## Persistencia

SQLite almacena empleados, usuarios, sesiones, clientes, solicitudes, tareas, licencias e historial. Las bases y los adjuntos locales están en `work/team-data`, `work/crm-data` y `work/leave-data`. Respaldar esas tres carpetas con el servidor detenido. El ZIP no incluye estas bases, sesiones ni archivos privados.

Los datos iniciales son pocos registros de ejemplo. Las tareas se relacionan con solicitudes, clientes y empleados mediante identificadores. La desactivación conserva historial. Licencias deriva la disponibilidad de períodos aprobados, sin alterar el estado laboral.

Reportes usa registros persistidos y exporta PDF. No reconstruye historia que no fue registrada. El módulo independiente Capacitación está retirado; se conserva la formación en el perfil del empleado.

## Verificación

Ejecutar `python tests/test_auth.py`, `python tests/test_crm_api.py`, `python tests/test_helpdesk_api.py`, `python tests/test_leave_api.py`, `python tests/test_reports.py` y `python tests/test_stability.py`. Las pruebas usan almacenamiento aislado. Las regresiones de dominio activan un modo exclusivo de pruebas; el servidor normal lo rechaza.

## Alcance operativo

Las contraseñas se protegen con scrypt y las sesiones con cookies HttpOnly. El backend aplica autorización y CSRF. No hay registro público ni recuperación por correo implementada; el administrador puede gestionar las credenciales desde Usuarios.

El servidor escucha en 127.0.0.1. Antes de desplegarlo para acceso remoto, configurar HTTPS, proxy privado, cookie Secure, origen autorizado y respaldos. Los detalles están en el informe de autenticación.
