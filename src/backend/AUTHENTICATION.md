# Segunda etapa: autenticación y autorización de VitaDev Nexo

## Puesta en marcha
1. Instalar las dependencias de src/backend/requirements.txt y disponer de Node.js y Python.
2. Ejecutar crear-administrador.cmd una sola vez. Pide correo y contraseña de 12 a 128 caracteres mediante getpass; no imprime ni guarda la contraseña original. No hay cuenta ni clave predeterminada.
3. Ejecutar iniciar-nexo.cmd y abrir http://127.0.0.1:4173/login.
4. Entrar como administrador. En Equipo, abrir un empleado y utilizar Crear acceso; esto crea solamente Usuario con employeeId.

El administrador inicial puede existir sin empleado vinculado. El modelo permite employeeId nulo; las cuentas EMPLOYEE requieren un empleado activo. Las credenciales de los archivos de prueba pertenecen exclusivamente a bases temporales y nunca se cargan en la base normal.

## Implementación
- auth.py: esquema de acceso, hash, sesiones, política de autorización, validaciones y filtrado de datos.
- auth_server.py: servidor integrado, Login/Me/Logout, administración de usuarios y alta inicial local.
- identity.py: auditoría con actorUserId y actorEmployeeId autenticados, sin eliminar eventos previos.
- access-policy.json: tres perfiles (Administrador, Soporte y Empleado) y permisos concretos compartidos. El área solo sugiere el perfil al crear acceso; no autoriza operaciones.
- auth.js/auth.css: Login, restauración de identidad, carga protegida del frontend y estados de error.
- users.js: Usuarios, Roles y permisos, detalle, creación desde Equipo, modificación, desactivación/reactivación y menú de sesión.
- Integraciones limitadas en app.js, interface.js, team.js, helpdesk.js, leave.js, reports.js y los servidores existentes. No se rehízo su lógica funcional.

## Contraseñas y sesiones
Las contraseñas usan scrypt de hashlib con sal aleatoria de 16 bytes, N=131072, r=8, p=1 y salida de 32 bytes. Solo se guarda el hash codificado. No hay contraseñas ni tokens de autenticación en localStorage. El formulario permite definir una contraseña inicial o cambiarla con users.manage; no simula invitaciones ni envíos de correo.

La sesión usa un token aleatorio de 256 bits. En SQLite se almacena su SHA-256, no el token original. La cookie es HttpOnly y SameSite=Strict; Secure se activa con NEXO_COOKIE_SECURE=1 para HTTPS. Cada petición vuelve a validar estado del usuario y empleado. Se rota la sesión al ingresar; cambiar permisos, contraseña o estado revoca las sesiones de esa cuenta.

Sin Recordarme: vencimiento absoluto de 8 horas, inactividad de 2 horas y cookie de sesión. Con Recordarme: 30 días absolutos, 7 días de inactividad y cookie persistente. Logout elimina la sesión del servidor y limpia la página; HTML y respuestas privadas utilizan no-store. Las mutaciones verifican origen y token CSRF. Se limitan los intentos de Login por dirección y correo.

Referencias técnicas consultadas: [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) y [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

## Autorización
Los roles iniciales son ADMIN y EMPLOYEE; CLIENT no puede crearse todavía. No se implementó Portal Cliente. La interfaz oculta acciones sin permiso y protege navegación manual, incluido /reportes. El servidor valida todas las rutas /api/*; no confía en X-Nexo-View ni X-Nexo-Employee para determinar identidad.

Equipo exige permiso de gestión para cambios y limita los datos personales a la propia cuenta cuando no existe employees.view. CRM entrega al empleado solamente el contexto de clientes/productos/contactos de sus solicitudes o tareas, excluyendo contratos e historial comercial. Solicitudes y archivos se filtran por asignación; tareas solo pueden actualizarse por su responsable o administración. Licencias obtiene el empleado de la sesión y restringe creación, cancelación, aprobación y adjuntos. Reportes y Usuarios requieren sus permisos específicos. Las rutas desconocidas se rechazan; DELETE de usuarios no elimina historial.

No se puede desactivar o degradar al último administrador activo, ni desactivar a su empleado. La cuenta puede desactivarse/reactivarse sin borrar empleados, solicitudes, tareas o auditoría. El usuario almacena datos de acceso; nombre, puesto, área y fotografía se consultan en Equipo mediante employeeId y no se duplican en users.

## Demostración, pruebas y límites
Se retiró el selector de vistas del funcionamiento normal. Las regresiones de dominio existentes usan NEXO_TEST_MODE explícitamente en bases aisladas; el lanzador normal rechaza esa variable. Las pruebas de autenticación y navegador utilizan cuentas reales de prueba con cookies y autorización activas.

Se agregaron pruebas de Login inválido, desactivación, sesión, expiración, logout, CSRF/origen, cookies, permisos y suplantación de encabezados, creación y unicidad de acceso, reactivación, actualización de datos de Equipo y protección del último administrador. La prueba de navegador crea acceso para Marcos desde Equipo y recorre Login, F5, rutas denegadas, desactivación/reactivación y logout/atrás; revisa escritorio y móvil.

Pendiente: recuperación por email con tokens y expiración, MFA si se requiere, despliegue HTTPS y endurecimiento operativo del servidor. El servidor actual escucha únicamente en loopback; no debe exponerse por HTTP a una red pública. Para un despliegue HTTPS usar proxy adecuado, Secure y NEXO_PUBLIC_ORIGIN, manteniendo el backend privado. No se añadió Login social, registro público, chat, nómina ni funciones nuevas fuera del acceso.

## Resultado de verificación — 13/09/2026
- Build correcto: sintaxis JavaScript validada y salida dist generada desde src.
- Autenticación: 13 pruebas aprobadas, incluyendo lectura concurrente de identidad y cambio de cuenta.
- Regresiones de API: 8 suites aprobadas, con 65 ejecuciones de casos (incluye las copias existentes de CRM y Solicitudes).
- Navegador: flujos aprobados de autenticación, Clientes, Solicitudes, Licencias, Reportes, sincronización de tareas/Equipo y navegación por perfil. Sin errores JavaScript en estos recorridos; comprobados escritorio, móvil y exportación PDF.
- Corregida una conexión SQLite anidada que podía bloquear consultas simultáneas de identidad. Se reutiliza la conexión de la operación.
- Corregido el cierre del formulario de licencias para esperar la actualización de los datos antes de mostrar el resultado.
- La fixture de pruebas exige rutas de almacenamiento explícitas y rechaza las bases normales. No se incluyen cuentas de prueba en los datos de trabajo ni en el ZIP.
- Verificados los ocho assets originales servidos desde el build y el rechazo 401 de las APIs privadas sin sesión.
- El servidor de entrada reserva el puerto de forma exclusiva en Windows para impedir dos versiones escuchando simultáneamente.
- El paquete incluye código fuente, build, backend, dependencias declaradas, documentación y pruebas; excluye bases locales, sesiones, adjuntos privados y respaldos.

La base local queda sin cuentas predeterminadas: el primer administrador debe crearse mediante crear-administrador.cmd.
