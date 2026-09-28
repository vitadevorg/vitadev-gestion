"""Adaptador del contrato SQL interno hacia PostgreSQL normalizado.

Solo admite las operaciones usadas por los controladores existentes. No ejecuta
DDL SQLite ni recurre a SQLite. Los parámetros nunca se interpolan en SQL.
"""

import json, os, re, sqlite3, sys, threading, queue
from contextvars import ContextVar
from pathlib import Path
from database_config import load_environment, connection_options
from postgres_model import SIMPLE, AUDITS, FILES, KINDS, PAYLOADS, schema_name, views
from identity import principal
from domain import LABOR

_pool = queue.LifoQueue(maxsize=16)
_pool_key = None
_pool_lock = threading.Lock()
_active = ContextVar("postgres_transactions", default=())


def before_response():
    # Ninguna respuesta de éxito debe adelantarse a la confirmación del servidor.
    for c in reversed(_active.get()):
        if c.locked:
            c.commit()


def enabled():
    value = os.environ.get("VITADEV_DATABASE", "sqlite")
    if value not in ("sqlite", "postgres"):
        raise ValueError("VITADEV_DATABASE debe ser sqlite o postgres")
    return value == "postgres"


def native():
    import psycopg
    from psycopg import sql

    global _pool_key
    schema = schema_name(os.environ.get("VITADEV_DB_SCHEMA", "vitadev"))
    # Las suites nunca escriben en el esquema operativo configurado en .env.
    if os.environ.get("NEXO_TEST_SUITE") == "1" and not schema.startswith("vitadev_test_"):
        raise RuntimeError("Las pruebas solo pueden usar esquemas vitadev_test_*.")
    url, options = connection_options()
    key = (url, tuple(options.items()), schema)
    with _pool_lock:
        if key != _pool_key:
            while not _pool.empty():
                _pool.get_nowait().close()
            _pool_key = key
        try:
            c = _pool.get_nowait()
        except queue.Empty:
            c = None
    if c is None or c.closed:
        c = psycopg.connect(url, **options)
        c.execute(sql.SQL("SET search_path TO {},pg_catalog").format(sql.Identifier(schema)))
        c.execute("SET timezone TO 'UTC'")
        c.execute("SET statement_timeout TO '30s'")
        c.execute("SET lock_timeout TO '15s'")
        c.commit()
        # Lecturas sin transacción: con Supabase remoto cada COMMIT cuesta ~200 ms de ida y vuelta.
        # Las escrituras abren una transacción explícita en Connection.lock().
        c.autocommit = True
    return c


def ensure_ready():
    with connect() as c:
        versions = {r[0] for r in c.raw.execute("SELECT version FROM schema_migrations")}
        if not {1, 2} <= versions:
            raise RuntimeError(
                "Falta preparar el esquema PostgreSQL v2. No se ejecutan semillas automáticamente."
            )


def connect():
    return Connection(native())


def warm(count=6):
    """Abre conexiones en paralelo al iniciar: cada conexión nueva a Supabase tarda ~3 s y la
    primera carga de la aplicación hace varias peticiones simultáneas."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(count) as pool:
        opened = list(pool.map(lambda _: native(), range(count)))
    for raw in opened:
        try:
            _pool.put_nowait(raw)
        except queue.Full:
            raw.close()


def other_active_admin(connection, excluded):
    for user in connection.execute(
        "SELECT * FROM users WHERE role='ADMIN' AND status='ACTIVE' AND id<>?", (excluded,)
    ):
        if user["employeeId"] is None:
            return True
        employee = connection.execute(
            "SELECT * FROM employees WHERE id=?", (user["employeeId"],)
        ).fetchone()
        if employee and json.loads(employee["payload"])["laborStatus"] == LABOR.ACTIVE:
            return True
    return False


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Result:
    def __init__(self, rows=(), lastrowid=None, rowcount=None):
        self.rows = list(rows)
        self.position = 0
        self.lastrowid = lastrowid
        self.rowcount = len(self.rows) if rowcount is None else rowcount

    def fetchone(self):
        if self.position == len(self.rows):
            return None
        item = self.rows[self.position]
        self.position += 1
        return item

    def fetchall(self):
        result = self.rows[self.position :]
        self.position = len(self.rows)
        return result

    def __iter__(self):
        return iter(self.fetchall())


def translate(query):
    # SQL fijo de los controladores; literales de texto se mantienen intactos.
    chunks = re.split("('(?:''|[^'])*')", query)
    for i in range(0, len(chunks), 2):
        part = chunks[i].replace("?", "%s")
        part = re.sub(
            r"\b(FROM|JOIN)\s+([a-z_]+)\b",
            lambda m: m[1] + " legacy_" + m[2] + " AS " + m[2] if m[2] in views() else m[0],
            part,
            flags=re.I,
        )
        part = re.sub(
            r"(\b\w+)\s*=\s*(%s)\s+COLLATE NOCASE", r"lower(\1)=lower(\2)", part, flags=re.I
        )
        for name in [
            "employeeId",
            "permissionProfile",
            "passwordHash",
            "lastAccess",
            "lastLoginAt",
            "createdAt",
            "updatedAt",
            "tokenHash",
            "userId",
            "expiresAt",
            "lastSeen",
            "idleSeconds",
            "actorUserId",
            "actorEmployeeId",
            "entityId",
            "entityType",
            "end",
        ]:
            part = re.sub(r"\b" + name + r"\b", '"' + name + '"', part)
        chunks[i] = part
    return "".join(chunks)


class Connection:
    def __init__(self, raw):
        self.raw = raw
        self.locked = False
        self.closed = False

    def __enter__(self):
        self.token = _active.set((*_active.get(), self))
        return self

    def __exit__(self, kind, value, tb):
        try:
            if kind:
                self.rollback()
            else:
                self.commit()
        finally:
            _active.reset(self.token)
            self.close()

    def in_transaction(self):
        from psycopg.pq import TransactionStatus

        return self.raw.info.transaction_status != TransactionStatus.IDLE

    def commit(self):
        if self.locked:
            self.raw.execute("COMMIT")
        self.locked = False

    def rollback(self):
        if self.in_transaction():
            self.raw.execute("ROLLBACK")
        self.locked = False

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.in_transaction():
                self.raw.execute("ROLLBACK")
            _pool.put_nowait(self.raw)
        except Exception:
            self.raw.close()

    def lock(self):
        # Primera escritura: abre la transacción y toma el bloqueo en un solo viaje a la base.
        if not self.locked:
            self.raw.execute(
                "BEGIN; SELECT pg_advisory_xact_lock(hashtextextended(current_schema()||':writes',0))"
            )
            self.locked = True

    def select_many(self, queries):
        """Varias lecturas en un solo viaje a la base (modo pipeline de PostgreSQL)."""
        from psycopg.rows import dict_row

        cursors = []
        with self.raw.pipeline():
            for query, params in queries:
                cursor = self.raw.cursor(row_factory=dict_row)
                cursor.execute(translate(query.strip().rstrip(";")), tuple(params))
                cursors.append(cursor)
        return [[Row(row) for row in cursor.fetchall()] for cursor in cursors]

    def execute(self, query, params=()):
        import psycopg

        try:
            return self._execute(query.strip().rstrip(";"), tuple(params))
        except psycopg.IntegrityError:
            raise sqlite3.IntegrityError("Restricción relacional PostgreSQL") from None

    def _execute(self, q, p):
        from psycopg.rows import dict_row

        if q.upper().startswith("SELECT "):
            with self.raw.cursor(row_factory=dict_row) as cursor:
                cursor.execute(translate(q), p)
                return Result(Row(row) for row in cursor.fetchall())
        if q.upper() == "BEGIN IMMEDIATE":
            self.lock()
            return Result()
        self.lock()
        insert = re.fullmatch(
            r"INSERT( OR IGNORE)? INTO (\w+)\s*(?:\(([^)]+)\))?\s*VALUES\s*\(([^)]+)\)(.*)", q, re.I
        )
        if insert:
            _, table, columns, values, tail = insert.groups()
            if table not in set(SIMPLE) | set(PAYLOADS) | set(AUDITS) | set(FILES) | {
                "records",
                "desk_comments",
            }:
                raise NotImplementedError("Escritura no soportada")
            if columns:
                columns = [v.strip() for v in columns.split(",")]
            elif table in SIMPLE:
                columns = list(SIMPLE[table])
            elif table in FILES:
                columns = ["id", "name", "mime"] + (["owner"] if table == "absence_files" else [])
            else:
                raise NotImplementedError("INSERT requiere columnas explícitas")
            params = iter(p)
            row = {
                column: self.value(value.strip(), params, {})
                for column, value in zip(columns, values.split(","))
            }
            if len(columns) != len(values.split(",")):
                raise ValueError("Cantidad de columnas inválida")
            if tail.strip():
                if (
                    table != "login_attempts"
                    or tail.strip() != "ON CONFLICT(key) DO UPDATE SET count=count+1"
                ):
                    raise NotImplementedError("Conflicto no soportado")
                self.raw.execute(
                    "INSERT INTO login_attempts(key,count,expires_at) VALUES(%s,%s,%s) ON CONFLICT(key) DO UPDATE SET count=login_attempts.count+1",
                    (row["key"], row["count"], row["expiresAt"]),
                )
                return Result(rowcount=1)
            id = self.store(table, row, False, ignore=bool(insert[1]))
            return Result(lastrowid=id, rowcount=1)
        update = re.fullmatch(r"UPDATE (\w+) SET (.+) WHERE (.+)", q, re.I)
        if update:
            table, assignments, where = update.groups()
            parts = [x.strip().split("=", 1) for x in assignments.split(",")]
            n = sum(value.count("?") for _, value in parts)
            rows = self.execute("SELECT * FROM " + table + " WHERE " + where, p[n:]).fetchall()
            for old in rows:
                values = iter(p[:n])
                new = dict(old)
                for column, value in parts:
                    new[column.strip()] = self.value(value.strip(), values, old)
                self.store(table, new, True)
            return Result(rowcount=len(rows))
        delete = re.fullmatch(r"DELETE FROM (sessions|login_attempts)(?: WHERE (.+))?", q, re.I)
        if delete:
            table, where = delete.groups()
            mapping = SIMPLE[table]
            pk = next(iter(mapping))
            rows = self.execute(
                "SELECT * FROM " + table + (" WHERE " + where if where else ""), p
            ).fetchall()
            from psycopg import sql

            for row in rows:
                self.raw.execute(
                    sql.SQL("DELETE FROM {} WHERE {}=%s").format(
                        sql.Identifier(table), sql.Identifier(mapping[pk])
                    ),
                    (row[pk],),
                )
            return Result(rowcount=len(rows))
        raise NotImplementedError("Operación SQL interna no soportada en PostgreSQL")

    @staticmethod
    def value(expression, params, old):
        if expression == "?":
            return next(params)
        if expression.upper() == "NULL":
            return None
        if re.fullmatch(r"-?\d+", expression):
            return int(expression)
        if expression.startswith("'") and expression.endswith("'"):
            return expression[1:-1].replace("''", "'")
        if expression.endswith("+1") and expression[:-2] in old:
            return old[expression[:-2]] + 1
        raise NotImplementedError("Expresión de escritura no soportada")

    def write(self, table, row, update=False, pk="id", ignore=False):
        from psycopg import sql
        from psycopg.types.json import Jsonb

        values = {
            k: (
                Jsonb(v)
                if k in {"extra_data", "metadata", "changed_fields", "legacy_permissions"}
                and v is not None
                else v
            )
            for k, v in row.items()
        }
        if update:
            columns = [k for k in values if k != pk]
            query = sql.SQL("UPDATE {} SET {} WHERE {}=%s").format(
                sql.Identifier(table),
                sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(k)) for k in columns),
                sql.Identifier(pk),
            )
            self.raw.execute(query, [values[k] for k in columns] + [values[pk]])
        else:
            columns = list(values)
            query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(table),
                sql.SQL(",").join(map(sql.Identifier, columns)),
                sql.SQL(",").join(sql.Placeholder() for _ in columns),
            )
            if ignore:
                query += sql.SQL(" ON CONFLICT DO NOTHING")
            self.raw.execute(query, [values[k] for k in columns])

    def next_id(self, table):
        if table == "records":
            return self.raw.execute("SELECT nextval('records_id_seq')").fetchone()[0]
        return self.raw.execute(
            "SELECT nextval(pg_get_serial_sequence(%s,'id'))", (table,)
        ).fetchone()[0]

    def store(self, table, row, update, ignore=False):
        from psycopg import sql

        if table in SIMPLE:
            mapping = SIMPLE[table]
            defaults = {}
            if table == "users":
                defaults = dict(
                    permissions="[]",
                    lastAccess=None,
                    lastLoginAt=None,
                    passwordHash=None,
                    permissionProfile="EMPLOYEE",
                    createdAt=None,
                    updatedAt=None,
                )
            row = {**defaults, **row}
            if table == "users" and not row.get("id"):
                row["id"] = self.next_id("users")
            native = {
                column: (
                    json.loads(row[key])
                    if key == "permissions" and isinstance(row.get(key), str)
                    else row[key]
                )
                for key, column in mapping.items()
                if key in row
            }
            self.write(table, native, update, pk=next(iter(mapping.values())))
            return row.get("id")
        if table in FILES:
            scope, prefix = FILES[table]
            self.write(
                "attachments",
                dict(
                    id=row["id"],
                    scope=scope,
                    name=row["name"],
                    mime=row["mime"],
                    storage_path=prefix + row["id"],
                    owner_employee_id=row.get("owner"),
                ),
                ignore=ignore,
            )
            return row["id"]
        if table in AUDITS:
            return self.audit(table, row)
        native_table = (
            KINDS[row["kind"]]
            if table == "records"
            else "comments" if table == "desk_comments" else PAYLOADS[table][0]
        )
        if not row.get("id"):
            row["id"] = self.next_id("records" if table == "records" else native_table)
        row.setdefault("version", 1)
        if table == "desk_requests":
            row.setdefault("contact_id", None)
        if table == "desk_comments":
            actor = principal.get() or {}
            row.update(
                actorUserId=actor.get("id"),
                actorEmployeeId=actor.get("employeeId"),
                actor=(actor.get("employee") or {}).get("name")
                or actor.get("email")
                or row["actor"],
            )
        if update and "payload" in row:
            previous = self.raw.execute(
                sql.SQL("SELECT extra_data FROM {} WHERE id=%s").format(
                    sql.Identifier(native_table)
                ),
                (row["id"],),
            ).fetchone()
            if previous:
                row["payload"] = json.dumps(
                    {**previous[0], **json.loads(row["payload"])}, ensure_ascii=False
                )
        # Reutiliza la conversión auditada de la migración: mismas columnas y FK.
        from migrations.transform import convert

        data = {
            ("team", "employees"): [],
            ("team", "users"): [],
            ("team", "sessions"): [],
            ("team", "login_attempts"): [],
            ("team", "employee_audit"): [],
            ("team", "user_audit"): [],
            ("crm", "records"): [],
            ("crm", "activity"): [],
            ("crm", "files"): [],
            ("crm", "desk_requests"): [],
            ("crm", "desk_comments"): [],
            ("crm", "desk_tasks"): [],
            ("crm", "desk_events"): [],
            ("crm", "desk_files"): [],
            ("leave", "absences"): [],
            ("leave", "absence_events"): [],
            ("leave", "absence_files"): [],
        }
        database = "team" if table == "employees" else "leave" if table == "absences" else "crm"
        data[database, table] = [row]
        converted = convert(data, {"permissions": [], "profiles": {}, "profileLabels": {}})
        # Principal único: la lógica existente reemplaza al anterior dentro de la operación.
        if native_table == "contacts" and converted["contacts"][0]["is_principal"]:
            self.raw.execute(
                "UPDATE contacts SET is_principal=false,version=version+1 WHERE client_id=%s AND id<>%s AND is_principal",
                (converted["contacts"][0]["client_id"], row["id"]),
            )
        self.write(native_table, converted[native_table][0], update)
        children = {
            "employees": [("employee_skills", "employee_id")],
            "products": [("product_plans", "product_id"), ("product_options", "product_id")],
            "subscriptions": [("subscription_options", "subscription_id")],
            "contracts": [("contract_subscriptions", "contract_id")],
            "requests": [("request_attachments", "request_id")],
            "comments": [("comment_attachments", "comment_id")],
        }
        for child, fk in children.get(native_table, []):
            # Catálogos se sincronizan por diferencia: no borrar opciones referenciadas.
            if child in ("product_plans", "product_options"):
                names = [r["name"] for r in converted[child]]
                self.raw.execute(
                    sql.SQL("DELETE FROM {} WHERE {}=%s AND NOT(name=ANY(%s))").format(
                        sql.Identifier(child), sql.Identifier(fk)
                    ),
                    (row["id"], names),
                )
                for r in converted[child]:
                    self.raw.execute(
                        sql.SQL(
                            "INSERT INTO {} (product_id,name,position) VALUES(%s,%s,%s) ON CONFLICT(product_id,name) DO UPDATE SET position=excluded.position"
                        ).format(sql.Identifier(child)),
                        (r["product_id"], r["name"], r["position"]),
                    )
            else:
                self.raw.execute(
                    sql.SQL("DELETE FROM {} WHERE {}=%s").format(
                        sql.Identifier(child), sql.Identifier(fk)
                    ),
                    (row["id"],),
                )
                for r in converted[child]:
                    self.write(child, r)
        return row["id"]

    def audit(self, table, row):
        legacy, column, entity = AUDITS[table]
        actor = principal.get() or {}
        id = self.raw.execute(
            "SELECT COALESCE(max(source_id),0)+1 FROM audit_entries WHERE source_table=%s", (table,)
        ).fetchone()[0]
        stamp = row.get("created_at") or row.get("timestamp")
        uid = actor.get("id", row.get("actorUserId"))
        eid = actor.get("employeeId", row.get("actorEmployeeId"))
        label = (actor.get("employee") or {}).get("name") or actor.get("email") or row.get("actor")
        metadata = {
            **row,
            "id": id,
            "actorUserId": uid,
            "actorEmployeeId": eid,
            "entityType": entity,
            "entityId": row[legacy],
            "timestamp": stamp,
        }
        if "actor" in row:
            metadata["actor"] = label
        self.write(
            "audit_entries",
            dict(
                source_table=table,
                source_id=id,
                action=row["action"],
                actor_user_id=uid,
                actor_employee_id=eid,
                actor_label=label,
                entity_type=entity,
                entity_id=row[legacy],
                **{column: row[legacy]},
                occurred_at=stamp,
                reference=row.get("reference"),
                comment=row.get("comment"),
                changed_fields=json.loads(row["fields"]) if "fields" in row else None,
                metadata=metadata,
            ),
        )
        return id
