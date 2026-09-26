# Integración visual de VitaDev

## Resultado

El nombre visible del sistema es VitaDev. Se integraron los 21 archivos oficiales del ZIP, conservando exactamente sus bytes: no se generaron imágenes, no se modificaron rostros y no se recortaron logos. El favicon usa su recurso dedicado.

## Recursos y usos

- `brand/vitadev-logo.png`: Login, sobre fondo claro.
- `brand/vitadev-logo-white.png`: sidebar oscuro, sin repetir logo e isotipo.
- `brand/vitadev-icon.png`: indicador compacto de inicio de la aplicación.
- `brand/favicon.png`: favicon PNG del documento.
- Fotografías de Aylen, Claudio, Juan, Karen, Gabriel y Ramiro: registros de empleados, reutilizados por los componentes de personas en Equipo, perfil, header, Usuarios, solicitudes y tareas.
- `avatars/default-avatar.png`: personas sin fotografía y recuperación ante una imagen rota.
- `clients/sanatorio9dejulio.jpeg`: cliente Sanatorio 9 de Julio, listado, ficha y solicitudes relacionadas.
- `clients/default-company.png`: empresas sin logo y recuperación ante imagen rota. Nunca se usa avatar de persona como logo.
- `clients/hospitalitaliano.png` y `clients/sanatoriomodelo.png`: disponibles para sus organizaciones cuando se registren; no se crearon clientes ficticios adicionales para mostrarlos.

Se normalizaron exclusivamente nombres de archivo: defaultavatar → default-avatar, defaultcompany → default-company, no-request → no-requests y no-task → no-tasks. Se conservó JPEG como JPEG.

## Personas y administradora

Se reemplazaron los cuatro registros de ejemplo conservando sus IDs y relaciones: 1 Aylen Agüero, 2 Claudio Moya, 3 Juan Romero, 4 Karen Petriczkowicz. Se incorporaron Gabriel Lazarte (5) y Ramiro Vides (6). La cuenta administradora existente está vinculada mediante employeeId=1 a Aylen. Su contraseña y rol se conservaron; no se duplicó la foto en Usuario.

Los puestos, fechas y demás información laboral son datos de ejemplo que deben revisarse. Los correos de ejemplo se identifican con example.invalid; la cuenta existente de Aylen conserva su correo real. No se inventaron DNI, teléfonos ni fechas de nacimiento. Se conservaron copias SQLite previas en work/backups/visual-assets, excluidas del ZIP.

## Estados y feedback

Componente común `visualState`: imagen decorativa, título y descripción en HTML y acción opcional. Distingue solicitudes, tareas, clientes y licencias vacías; búsqueda sin resultados; error real con Reintentar. Los indicadores de carga no muestran ilustraciones de error ni estados vacíos anticipados.

Los estados se conectaron en Clientes, Solicitudes, Mis tareas, Licencias, búsquedas de Equipo/Usuarios y errores de Equipo, Clientes, Solicitudes, Licencias, Reportes y Usuarios. Los estados de tablas vacías se muestran fuera de la tabla para evitar recortes en móvil. Los paneles sin un recurso específico conservan un mensaje de texto adecuado, sin reutilizar una imagen semánticamente incorrecta.

Toasts con región accesible, mensajes de licencia aprobada/rechazada/cancelada y temporizador único para que una notificación anterior no oculte la siguiente. Se mantuvieron las confirmaciones mediante diálogos existentes, sin introducir alerts ni confirms nativos.

## Archivos modificados

`src/assets/**`, `assets.js`, `index.html`, `theme.css`, `auth.css`, `auth.js`, `app.js`, `interface.js`, `employee.js`, `team.js`, `crm.js`, `helpdesk.js`, `leave.js`, `reports.js`, `users.js`; integración de datos en `src/backend/team-seed.json`, `team_server.py`, `crm_server.py`, textos de marca en backend; `build.js`, `README.md`, lanzador `iniciar-vitadev.cmd` y pruebas afectadas por el cambio autorizado de nombres/cantidad.

El build elimina archivos obsoletos de dist. Toda edición funcional se hizo en src. Los identificadores internos de cookies, encabezados y rutas existentes se mantienen para no romper sesiones o integraciones; no son el nombre visible del producto.

## Verificación

- Build correcto y sintaxis JavaScript validada.
- Ocho suites de API existentes aprobadas (65 ejecuciones de casos).
- Trece pruebas de autenticación aprobadas.
- Flujos de navegador aprobados: acceso, Clientes, Solicitudes, Licencias, Reportes y sincronización de tareas/perfil. Se comprobaron escritorio, móvil y consola.
- Prueba visual específica: marca, fotografía desde employeeId, vacío, búsqueda, carga, error y seis ilustraciones conectadas.
- Los 21 recursos se verificaron byte por byte contra el ZIP original y mediante HTTP desde el build.

El ZIP de distribución excluye bases de datos, sesiones, contraseñas, adjuntos privados y respaldos. La cuenta existente de Aylen permanece en esta instalación; no se exporta como una credencial predeterminada.
