# Escrituras PostgreSQL de VitaDev

Esta etapa mantiene los controladores Python, las rutas HTTP y sus validaciones. No cambia el frontend. La migración definitiva y el cambio de proveedor de la instalación habitual no se ejecutan con las pruebas.

## Inventario de escrituras

| Origen SQLite | Operaciones conservadas | Destino PostgreSQL |
|---|---|---|
| employees, employee_audit | Alta, edición, habilidades, responsables, desactivación y cambios de versión | employees, employee_skills, audit_entries |
| users, sessions, login_attempts, user_audit | Alta/edición/desactivación de cuentas, hashes scrypt, sesiones, actividad de sesión, logout, revocación, intentos de login y auditoría | users, sessions, login_attempts, audit_entries; roles/permisos/perfiles relacionales |
| records: clients/contacts | Alta/edición de clientes, contacto inicial atómico, contacto principal y estados | clients, contacts |
| records: catalog/subscriptions/contracts | Productos/servicios, planes, opciones, contrataciones, contratos y relaciones | products, product_plans, product_options, subscriptions, subscription_options, contracts, contract_subscriptions |
| files, desk_files, absence_files | Registro de adjuntos y propietario de adjuntos de licencias; deduplicación por hash | attachments, con clave compuesta scope/id |
| activity | Historial comercial | audit_entries |
| desk_requests, desk_events | Alta, asignación/reasignación, prioridad, transiciones, fechas de resolución/cierre y versiones | requests, request_attachments, audit_entries |
| desk_comments | Comentarios internos, autor autenticado y adjuntos | comments, comment_attachments |
| desk_tasks | Creación y estado de tareas, sin reasignar automáticamente la solicitud | tasks; versión e historial de la solicitud asociada |
| absences, absence_events | Solicitar, aprobar, rechazar, cancelar, evitar superposiciones y registrar resolución | leaves, audit_entries |

Las fotografías y el contenido binario de los adjuntos siguen en las carpetas locales existentes. Su almacenamiento no era SQLite y no se agrega Supabase Storage.

## Adaptación y transacciones

- `postgres_backend.py` conserva el contrato interno utilizado por los controladores (`execute`, resultados por nombre/índice, identificador insertado y contextos de transacción). Admite las sentencias de esos controladores y rechaza las escrituras no implementadas. No usa SQLite como intermediario.
- Las escrituras se convierten con `transform.convert`, la misma conversión preparada para la migración. Se guardan en las tablas normalizadas y se sincronizan las tablas de relaciones dentro de la misma transacción.
- `postgres_model.py` genera 17 vistas de lectura `legacy_*` para que los controladores mantengan sus respuestas. Las columnas normales y las relaciones prevalecen sobre `extra_data`; el JSON conserva campos históricos que no tienen un modelo adicional definido.
- La preparación v2 agrega esas vistas y una secuencia global para los IDs comerciales, manteniendo el espacio de IDs de `records`. Conserva las 27 tablas de v1. Las vistas usan `security_invoker`; no habilitan acceso público ni la Data API.
- `BEGIN IMMEDIATE` adquiere un bloqueo asesor transaccional por esquema. Las escrituras automáticas también lo adquieren. La comprobación de versión, las validaciones de superposición y las escrituras quedan serializadas hasta commit/rollback, incluso entre distintos procesos del backend.
- El último administrador se comprueba dentro de la transacción. En modo PostgreSQL, una cuenta vinculada a un empleado inactivo no cuenta como otro administrador capaz de acceder.
- La auditoría toma usuario y empleado del contexto autenticado de la petición. El cambio y su auditoría se confirman juntos. Las respuestas HTTP de éxito esperan la confirmación de las transacciones de escritura.
- Los errores de integridad conservan la respuesta de conflicto de los controladores existentes. No se borran físicamente empleados o usuarios con historial.
- Las conexiones se reutilizan después de terminar su transacción; el pool no comparte una conexión activa entre peticiones.
- Se configuran señales TCP de mantenimiento para detectar conexiones perdidas; el soporte depende del sistema operativo, según la [documentación de libpq](https://www.postgresql.org/docs/17/libpq-connect.html). Una escritura cuya confirmación falla no se reintenta automáticamente, para evitar duplicarla.

## Selección de proveedor

El backend y el migrador cargan el `.env` privado de la raíz. Las variables del entorno del proceso tienen prioridad. No se expanden comandos ni variables dentro del archivo.

| Variable | Uso |
|---|---|
| VITADEV_DATABASE | `sqlite` por defecto; `postgres` selecciona el nuevo adaptador |
| VITADEV_DB_SCHEMA | `vitadev` por defecto; los tests usan `vitadev_test_<uuid>` |
| SUPABASE_DB_URL | Conexión PostgreSQL privada, directa o Session pooler |
| SUPABASE_SSLROOTCERT | Certificado CA para TLS con `verify-full` |

El backend PostgreSQL exige versiones de esquema 1 y 2 existentes. No crea automáticamente tablas ni registros de ejemplo al arrancar. No hay fallback silencioso a SQLite si PostgreSQL falla.

Dependencias del modo PostgreSQL:

```powershell
python -m pip install -r src/backend/requirements.txt -r src/backend/migrations/requirements.txt
```

## Verificación reproducible

```powershell
python tests/run_sqlite_suite.py
python tests/run_postgres_suite.py
```

El segundo comando crea fixtures en SQLite temporal, las carga en esquemas PostgreSQL desechables y ejecuta las mismas suites HTTP. Cada esquema se elimina al finalizar; el esquema definitivo `vitadev` no se modifica. Las tres bases SQLite originales se verifican mediante hashes antes y después de la ejecución. Las cuentas y datos creados por las pruebas pertenecen solo a esas fixtures.

`test_postgres_flow.py` incluye login real, gestión de Equipo y Usuarios, cliente/contacto, producto/contratación/contrato, solicitud, comentario, tarea, licencia, reportes y logout. Prohíbe `sqlite3.connect` durante el flujo y verifica las tablas PostgreSQL desde otra conexión. También comprueba rollback con auditoría, concurrencia, FK, preservación de información histórica y protección del último administrador.

Los resultados de cada ejecución quedan en `work/sqlite-test-results` y `work/postgres-test-results`. No se incluyen credenciales en el código ni se agregan las carpetas privadas al repositorio.

## Límite de esta etapa

La instalación habitual conserva SQLite hasta un corte explícito. El corte posterior requiere detener el backend, respaldar bases y archivos, repetir el inventario, ejecutar la transferencia transaccional al esquema vacío y verificar el inicio en modo PostgreSQL antes de reabrir el acceso.

Después de aceptar escrituras reales en PostgreSQL no basta volver a cambiar una variable para regresar a SQLite: hay que reconciliar los datos nuevos. No se habilitan escrituras simultáneas en ambos proveedores.
