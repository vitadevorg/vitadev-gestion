# Migración a Supabase — estado real al 14/09/2026

**Estado: conexión TLS y carga transaccional de prueba verificadas en Supabase; adaptación del runtime y migración definitiva pendientes.** El usuario confirmó la validación remota y su reversión completa. El backend sigue usando SQLite y la autenticación actual. No se modificó el frontend ni el diseño. No se eliminaron ni vaciaron bases.

## 1. Inventario actual

Se inspeccionaron las tres bases y sus 17 tablas, columnas, JSON, claves declaradas y relaciones verificadas por las APIs:

| Base | Tablas |
|---|---|
| work/team-data/team.sqlite3 | employees, employee_audit, users, sessions, login_attempts, user_audit |
| work/crm-data/crm.sqlite3 | records, activity, files, desk_requests, desk_events, desk_comments, desk_tasks, desk_files |
| work/leave-data/leaves.sqlite3 | absences, absence_events, absence_files |

`records` contiene cinco tipos: clients, contacts, catalog, subscriptions y contracts. Muchas relaciones están dentro de payload JSON y no tienen FK entre bases. Los adjuntos físicos y fotografías cargadas se guardan en carpetas locales, fuera de SQLite.

El inventario técnico está en `outputs/Inventario-SQLite.json`. Solo contiene nombres de campos, tipos, conteos y diagnósticos; no exporta correos, contraseñas, hashes o sesiones.

APIs que deben conservarse: `/api/auth/login`, `/api/auth/me`, `/api/auth/logout`; `/api/users`, `/api/users/{id}`, `/api/users/policy`; `/api/team`, fotos, auditoría, modificación y desactivación; `/api/crm` y operaciones comerciales/archivos; `/api/desk` y solicitudes, asignaciones, estados, comentarios, archivos y tareas; `/api/absences`, disponibilidad, aprobación, rechazo, cancelación y adjuntos; `/api/reports` y exportación PDF. Sus controladores Python y sus formatos JSON aún no fueron conmutados.

## 2. Esquema validado en Supabase, sin creación permanente

Archivo: `src/backend/migrations/001_supabase.sql`. Un esquema privado `vitadev`, con 27 tablas:

- Control: schema_migrations.
- Identidad: roles, permissions, permission_profiles, profile_permissions, users, sessions, login_attempts.
- Personal: employees, employee_skills.
- Comercial: clients, contacts, products, product_plans, product_options, subscriptions, subscription_options, contracts, contract_subscriptions.
- Operación: requests, request_attachments, comments, comment_attachments, tasks, leaves.
- Documentación y trazabilidad: attachments, audit_entries.

Se conservan IDs bigint. Las cuentas usan employee_id; no copian datos personales del empleado. Contratos y contrataciones tienen tabla de relación. Las solicitudes enlazan cliente, contratación, contacto y agente. Las tareas enlazan solicitud, cliente y empleado. Las claves compuestas impiden vincular una solicitud o contrato con una contratación de otra organización. La auditoría conserva el origen y el ID del evento, evitando colisiones entre bases.

Los campos relacionales salen del JSON. `extra_data` conserva el payload original durante esta transición para verificar que no se perdió información, incluidas estructuras históricas cuya normalización no está definida. No debe convertirse en una segunda fuente editable cuando se implemente el repositorio PostgreSQL.

El esquema no se expone a la Data API. Se revocan permisos públicos y se habilita RLS sin políticas públicas. La futura conexión del backend necesitará privilegios definidos expresamente. No se usan Supabase Auth, anon key ni service_role key. No hay un producto hardcodeado en el esquema o convertidor.

## 3. Herramientas preparadas

- `inspect_sqlite.py`: apertura de SQLite en modo solo lectura, inventario y validación de referencias entre bases. Bloquea exportación ante referencias inválidas o archivos registrados faltantes.
- `transform.py`: conversión determinista al modelo relacional; preserva IDs, versiones, relaciones, hashes y datos originales. Las fechas ausentes siguen siendo nulas; no se inventan fechas de recepción, importes ni identidades históricas.
- `migrate_supabase.py`: por defecto ejecuta solamente simulación. La opción `--apply --source-stopped` requiere conexión configurada y servicio detenido. Bloquea escrituras de origen durante la copia, crea respaldos SQLite, exige un esquema de destino inexistente y realiza DDL/carga/verificaciones dentro de una transacción PostgreSQL. Una falla revierte el destino. Nunca elimina el origen ni cambia el runtime automáticamente.
- `migrations/requirements.txt`: dependencia opcional psycopg, separada del backend actual.
- `.env.example` y `.gitignore`: configuración documentada y exclusión de archivos locales de secretos.
- `tests/test_migration.py`: pruebas locales de conversión y seguridad del proceso.

El usuario ejecutó la validación en Supabase con TLS verify-full: DDL, FK y carga de los registros actuales pasaron. La transacción se revirtió y se comprobó que no quedó el esquema vitadev. Se agregó un repositorio de lectura nativa (`postgres_repository.py`) y un punto de inyección en Reportes; cuatro pruebas locales de contrato y nueve de Reportes pasaron, al igual que el build. El lanzador `validar-supabase.cmd` ahora incluye una comparación de Reportes y permisos contra PostgreSQL; esta comprobación adicional todavía requiere ejecución en la sesión de Windows del usuario, que puede descifrar las credenciales guardadas. No se cambió el proveedor activo.

## 4. Datos migrados y SQLite restante

**Datos persistentes en Supabase: cero.** Se crearon y cargaron las tablas temporalmente durante la validación exitosa; todo se revirtió. No se realizó el corte definitivo.

La simulación de los datos actuales prepara: 6 empleados, 1 usuario, 2 clientes, 1 producto, 2 contrataciones, 3 solicitudes, 2 tareas, 2 licencias y 33 eventos de auditoría. También prepara roles/perfiles/permisos, habilidades y metadatos de sesión existentes. No hay contactos, contratos, comentarios ni adjuntos registrados en esta instalación al inspeccionarla. La simulación se guarda únicamente como conteos en `outputs/Simulacion-Supabase.json`.

Todos los módulos continúan utilizando las tres bases SQLite. Los archivos físicos continuarán en sus carpetas durante la primera transferencia de base de datos; no se agregó Supabase Storage. Los hashes scrypt permanecen intactos: no se exige migración a Supabase Auth ni se recuperan contraseñas originales.

## 5. Incompatibilidades y decisiones pendientes

1. No basta sustituir sqlite3.connect. Deben reemplazarse `?`, PRAGMA, executescript, lastrowid, INSERT OR IGNORE y las funciones/triggers de auditoría SQLite por repositorios PostgreSQL y RETURNING.
2. `BEGIN IMMEDIATE` serializa escrituras en SQLite. PostgreSQL necesita transacciones y bloqueos adecuados para operaciones como reservar licencias, mantener el último administrador y respetar versiones. No se debe traducir ese comando ignorando su semántica.
3. Los IDs de `records` eran globales para varios tipos. Los repositorios deberán reconstruir las mismas respuestas públicas desde las tablas separadas y usar FK tipadas.
4. Las fechas históricas vacías y contactos ausentes en solicitudes importadas son datos incompletos legítimos; el esquema admite NULL, sin completarlos automáticamente.
5. Capacitación/certificaciones del perfil carecen de un modelo tabular definido en los registros presentes. Se conservan en extra_data hasta una definición explícita.
6. La fuente vigente de permisos del runtime sigue siendo access-policy.json. Su tabla equivalente queda preparada, pero no debe activarse una edición independiente de ambos lugares.
7. La vuelta a SQLite después de admitir escrituras en PostgreSQL no es un simple cambio de variable: exige reconciliar esos cambios. El primer corte debe hacerse en mantenimiento y verificarse antes de reabrir escrituras.

## 6. Secuencia restante

1. Completado: proyecto Supabase, conexión Session pooler y certificado TLS configurados.
2. Completado: controlador PostgreSQL instalado y verificado en la sesión del usuario.
3. Completado: esquema, FK y transferencia transaccional de prueba, con reversión. Pendiente: comparación remota de las lecturas del repositorio y pruebas de permisos de acceso para el rol de ejecución.
4. Implementar la capa de repositorios PostgreSQL conservando los controladores y respuestas actuales; adaptar y ejecutar todas las suites contra PostgreSQL.
5. Detener el backend, respaldar bases y carpetas de archivos, transferir y verificar datos/IDs/relaciones/secuencias.
6. Activar el backend PostgreSQL y ejecutar Login, permisos, Equipo, Clientes, Solicitudes, tareas, Licencias y Reportes de punta a punta.
7. Reabrir operación solamente después de comprobar el resultado. Mantener SQLite como respaldo sin escrituras paralelas.

No se añadió una variable de conmutación del runtime que prometa un soporte PostgreSQL todavía inexistente.

## 7. Variables y comandos

- `SUPABASE_DB_URL`: DSN PostgreSQL del panel Connect, no la URL HTTP del proyecto. La contraseña debe estar codificada para URL y almacenada únicamente en el entorno del backend.
- `SUPABASE_SSLROOTCERT`: ruta al certificado CA correspondiente. La conexión se prepara con sslmode=verify-full y prepared statements desactivados.
- No se necesitan keys de la API de Supabase para una conexión directa PostgreSQL.

El archivo `.env.example` es una plantilla. El comando del migrador carga ahora el `.env` privado de la raíz mediante `database_config.py`; las variables existentes del proceso tienen prioridad. Solo se admiten SUPABASE_DB_URL y SUPABASE_SSLROOTCERT, sin expansión de comandos. Esta configuración no conmuta el backend operativo a PostgreSQL.

Simulación sin Supabase:

```powershell
python src/backend/migrations/inspect_sqlite.py --output outputs/Inventario-SQLite.json
python src/backend/migrations/migrate_supabase.py
python tests/test_migration.py
```

Después de contar con destino y completar las validaciones anteriores:

```powershell
python -m pip install -r src/backend/migrations/requirements.txt
python src/backend/migrations/migrate_supabase.py --apply --source-stopped
```

Ese comando transfiere datos; **no convierte por sí solo el backend actual a PostgreSQL**.

Referencia consultada: [conexiones PostgreSQL de Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres). Para un backend persistente, usar conexión directa o Session pooler y verificar TLS.

## 8. Resultados de pruebas locales

- 10 pruebas de preparación/conversión aprobadas: preservación de IDs y campos históricos, nulos, hashes/sesiones, detección de huérfanos, rutas reales de archivos, rechazo de tipos desconocidos y ausencia de escrituras durante la simulación.
- 8 suites existentes de SQLite aprobadas: 65 ejecuciones de casos de Equipo, Clientes, Solicitudes, Licencias, Reportes y estabilidad (incluyen copias históricas de algunas suites).
- 13 pruebas de autenticación aprobadas sobre SQLite.
- Build del frontend correcto. No hubo cambios visuales.
- SQL, driver, carga transaccional y equivalencia de Reportes/permisos: validados previamente en Supabase con reversión. APIs operativas de escritura sobre PostgreSQL: pendientes.
- Configuración privada: 4 pruebas aprobadas; migración: 10; contrato del repositorio: 4, ejecutadas nuevamente en esta etapa.
