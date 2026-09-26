# Revisión técnica — VitaDev Nexo

## Problemas y correcciones
- Retirados los CRUD, formularios y listeners antiguos de app.js e interface.js que convivían con Equipo, CRM, Mesa de Ayuda y Licencias. La presentación reutiliza los módulos persistidos.
- Eliminados los arrays de entidades demo del frontend, tareas personales paralelas, controles de jornada, horarios y reuniones ficticias, series ilustrativas y porcentajes de carga.
- Mis tareas consulta desk_tasks. Completar o reabrir una tarea modifica el mismo registro que muestra Solicitudes. No se crean tareas de relleno en instalaciones nuevas; las tareas ya persistidas se conservan con su historial.
- Corregidas la sobrescritura de resolvedAt al cambiar la prioridad, la actualización de disponibilidad en Inicio y las conexiones SQLite de Equipo que quedaban abiertas.

## Estados y fuentes definitivas
src/domain.json define solicitudes, prioridades, licencias, estado laboral, disponibilidad y tareas. El build genera domain.js; Python utiliza domain.py. Los identificadores simbólicos de solicitudes son NEW, IN_PROGRESS, WAITING_CLIENT, RESOLVED y CLOSED. Por compatibilidad con datos y API existentes, sus valores persistidos son las etiquetas españolas canónicas; no existe un segundo campo paralelo de estado. Las etiquetas antiguas se normalizan mediante migración explícita.

- Equipo: employees en team.sqlite3.
- Clientes, contactos, catálogo, contrataciones y contratos: records en crm.sqlite3.
- Solicitudes, tareas, comentarios y eventos: tablas desk_* en crm.sqlite3.
- Licencias: absences y absence_events en leaves.sqlite3.
- Reportes: lectura de esas fuentes, sin métricas de relleno.

Los arrays del navegador son cachés de respuestas. Las relaciones utilizan IDs: clientId, subscriptionId, agentId, owner, ticket, employee y managerId. Se retiró la búsqueda de personas por su nombre para ilustrar actividad. Una licencia aprobada vigente modifica la disponibilidad derivada, no el estado laboral.

## Empleado, usuarios y auditoría
La navegación de desarrollo incluye Mis tareas, Mis licencias y Mi perfil; Mis solicitudes corresponde a Soporte. CRM queda limitado al contexto Comercial o administrativo. Desarrollo consulta el contexto de las solicitudes vinculadas a sus tareas. El selector temporal permite elegir explícitamente al empleado de prueba por ID.

Esto NO es autorización segura: el selector y los encabezados locales son manipulables. Se preparó users, separado de employees, con id, email, role, status, employeeId, permissions y lastAccess. No se crearon cuentas ficticias ni contraseñas. Se conserva la configuración de acceso laboral para una futura migración explícita.

La auditoría conserva el historial y agrega actorUserId, actorEmployeeId, entityType, entityId, timestamp y metadata. Los actores quedan nulos cuando no hay una identidad autenticada; no se inventan atribuciones personales.

## Conservación y siguiente etapa
No se agregaron módulos, Login, Portal Cliente, IA, facturación ni control horario. Se conservaron assets, registros, adjuntos, historial comercial y exportación PDF. Capacitación no aparece como módulo independiente; se conserva la formación del perfil y el tipo de solicitud del cliente.

Antes de migrar se respaldaron las bases en work/backups. El ZIP contiene código y pruebas, no las bases de trabajo ni esos respaldos.

Pendiente: autenticación real, sesiones, permisos en cada endpoint, vinculación de cuentas con empleados y actores autenticados en auditoría. No publicar esta aplicación como servicio seguro sin esa etapa. Los históricos que no pueden reconstruirse se indican como insuficientes, sin inventar valores.

## Verificación
Build y suites API de Equipo, Clientes, Solicitudes, Licencias, Reportes y estabilidad, incluidas las copias existentes en work. Pruebas de navegador de CRUD, asignación, estados, comentarios, adjuntos, tareas, licencias, filtros, PDF y responsive.

La integración verifica la tarea de Lucas en ambas vistas, la licencia asociada a su ID, aprobación persistida, estado laboral Activo con disponibilidad De licencia y resolución contabilizada en Reportes. Las pruebas usan bases aisladas.
