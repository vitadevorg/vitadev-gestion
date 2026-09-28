from contextlib import closing

"""Conversión determinista del modelo SQLite al esquema PostgreSQL; no escribe en origen."""
import json, sqlite3
from collections import OrderedDict
from pathlib import Path

try:
    from .inspect_sqlite import DATABASES, inspect, ROOT
except ImportError:
    from inspect_sqlite import DATABASES, inspect, ROOT


def nullable(value):
    return None if value == "" else value


def read_source(work):
    data = {}
    for database, relative in DATABASES.items():
        with closing(
            sqlite3.connect((work / relative).resolve().as_uri() + "?mode=ro", uri=True)
        ) as c:
            c.row_factory = sqlite3.Row
            for (name,) in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall():
                if not name.replace("_", "").isalnum():
                    raise ValueError("Tabla inesperada")
                data[database, name] = [dict(r) for r in c.execute("SELECT * FROM " + name)]
    return data


def convert(data, policy):
    tables = OrderedDict(
        (name, [])
        for name in [
            "roles",
            "permissions",
            "permission_profiles",
            "profile_permissions",
            "employees",
            "employee_skills",
            "users",
            "sessions",
            "login_attempts",
            "attachments",
            "clients",
            "contacts",
            "products",
            "product_plans",
            "product_options",
            "subscriptions",
            "subscription_options",
            "contracts",
            "contract_subscriptions",
            "requests",
            "request_attachments",
            "comments",
            "comment_attachments",
            "tasks",
            "leaves",
            "audit_entries",
        ]
    )

    def put(table, row):
        tables[table].append(row)

    def fields(p, mapping):
        return {column: nullable(p.get(key)) for column, key in mapping.items()}

    def base(row, p):
        return {"id": row["id"], "version": row.get("version", 1), "extra_data": p}

    def dates(p):
        return fields(p, {"created_at": "createdAt", "updated_at": "updatedAt"})

    def attachment(value, scope, prefix=None):
        if not value:
            return None, None
        if prefix and not value.startswith(prefix):
            raise ValueError("Ruta de adjunto incompatible: " + scope)
        return scope, value.rsplit("/", 1)[-1]

    for role in ["ADMIN", "EMPLOYEE"]:
        put("roles", {"code": role})
    for permission in policy["permissions"]:
        put("permissions", {"code": permission})
    for profile, permissions in policy["profiles"].items():
        put("permission_profiles", {"code": profile, "label": policy["profileLabels"][profile]})
        for permission in permissions:
            put("profile_permissions", {"profile_code": profile, "permission_code": permission})
    for r in data["team", "employees"]:
        p = json.loads(r["payload"])
        put(
            "employees",
            {
                **base(r, p),
                **dates(p),
                "email": r["email"],
                "legajo": r["legajo"],
                **fields(
                    p,
                    {
                        "first_name": "firstName",
                        "last_name": "lastName",
                        "position": "role",
                        "area": "area",
                        "dni": "dni",
                        "birth_date": "birthDate",
                        "phone": "phone",
                        "manager_id": "managerId",
                        "hire_date": "hireDate",
                        "work_modality": "modality",
                        "labor_status": "laborStatus",
                        "availability": "availability",
                        "photo_path": "photo",
                    },
                ),
            },
        )
        for i, skill in enumerate(p.get("skills", [])):
            put("employee_skills", {"employee_id": r["id"], "position": i, "skill": skill})
    for r in data["team", "users"]:
        if r["permissionProfile"] not in policy["profiles"]:
            raise ValueError("Perfil desconocido en usuario " + str(r["id"]))
        put(
            "users",
            {
                "id": r["id"],
                "email": r["email"],
                "password_hash": r["passwordHash"],
                "role_code": r["role"],
                "status": r["status"],
                "employee_id": r["employeeId"],
                "profile_code": r["permissionProfile"],
                "last_login_at": r["lastLoginAt"],
                "created_at": r["createdAt"],
                "updated_at": r["updatedAt"],
                "legacy_permissions": json.loads(r["permissions"]),
                "legacy_last_access": r["lastAccess"],
            },
        )
    for r in data["team", "sessions"]:
        put(
            "sessions",
            fields(
                r,
                {
                    "token_hash": "tokenHash",
                    "user_id": "userId",
                    "csrf": "csrf",
                    "expires_at": "expiresAt",
                    "last_seen": "lastSeen",
                    "idle_seconds": "idleSeconds",
                },
            ),
        )
    for r in data["team", "login_attempts"]:
        put("login_attempts", {"key": r["key"], "count": r["count"], "expires_at": r["expiresAt"]})
    for database, table, scope, folder, prefix in [
        ("crm", "files", "crm", "crm-data/files", ""),
        ("crm", "desk_files", "request", "crm-data/files", "desk-"),
        ("leave", "absence_files", "leave", "leave-data/files", ""),
    ]:
        for r in data[database, table]:
            put(
                "attachments",
                {
                    "scope": scope,
                    "id": r["id"],
                    "name": r["name"],
                    "mime": r["mime"],
                    "storage_path": folder + "/" + prefix + r["id"],
                    "owner_employee_id": r.get("owner"),
                },
            )
    records = {r["id"]: r for r in data["crm", "records"]}
    for r in records.values():
        p = json.loads(r["payload"])
        common = {**base(r, p), **dates(p)}
        kind = r["kind"]
        if kind == "clients":
            put(
                "clients",
                {
                    **common,
                    **fields(
                        p,
                        {
                            "name": "name",
                            "legal_name": "legalName",
                            "cuit": "cuit",
                            "organization_type": "organizationType",
                            "country": "country",
                            "province": "province",
                            "city": "city",
                            "address": "address",
                            "postal_code": "postalCode",
                            "owner_employee_id": "owner",
                            "status": "status",
                            "logo_path": "logo",
                            "since": "since",
                        },
                    ),
                },
            )
        elif kind == "contacts":
            put(
                "contacts",
                {
                    **common,
                    **fields(
                        p,
                        {
                            "client_id": "clientId",
                            "first_name": "firstName",
                            "last_name": "lastName",
                            "email": "email",
                            "position": "position",
                            "phone": "phone",
                            "role": "role",
                            "status": "status",
                        },
                    ),
                    "is_principal": p.get("principal", False),
                },
            )
        elif kind == "catalog":
            put(
                "products",
                {
                    **common,
                    **fields(
                        p,
                        {
                            "name": "name",
                            "description": "description",
                            "product_type": "type",
                            "status": "status",
                        },
                    ),
                },
            )
            for key, table in [("plans", "product_plans"), ("configFields", "product_options")]:
                for i, name in enumerate(p.get(key, [])):
                    put(table, {"product_id": r["id"], "name": name, "position": i})
        elif kind == "subscriptions":
            put(
                "subscriptions",
                {
                    **common,
                    **fields(
                        p,
                        {
                            "client_id": "clientId",
                            "product_id": "productId",
                            "plan": "plan",
                            "status": "status",
                            "start_date": "start",
                        },
                    ),
                },
            )
            for i, name in enumerate(p.get("configuration", [])):
                put(
                    "subscription_options",
                    {
                        "subscription_id": r["id"],
                        "product_id": p["productId"],
                        "option_name": name,
                        "position": i,
                    },
                )
        elif kind == "contracts":
            scope, id = attachment(p.get("document"), "crm", "/api/crm/files/")
            put(
                "contracts",
                {
                    **common,
                    **fields(
                        p,
                        {
                            "client_id": "clientId",
                            "number": "number",
                            "status": "status",
                            "signed_date": "signed",
                            "start_date": "start",
                            "end_date": "end",
                            "renewal": "renewal",
                            "period": "period",
                            "currency": "currency",
                            "amount": "amount",
                            "notes": "notes",
                        },
                    ),
                    "document_scope": scope,
                    "document_id": id,
                },
            )
            for i, sid in enumerate(p.get("subscriptionIds", [])):
                put(
                    "contract_subscriptions",
                    {
                        "contract_id": r["id"],
                        "subscription_id": sid,
                        "client_id": p["clientId"],
                        "position": i,
                    },
                )
        else:
            raise ValueError("Tipo comercial no soportado: " + str(kind))
    for r in data["crm", "desk_requests"]:
        p = json.loads(r["payload"])
        put(
            "requests",
            {
                **base(r, p),
                **dates(p),
                "client_id": r["client_id"],
                "subscription_id": r["subscription_id"],
                "contact_id": r["contact_id"],
                **fields(
                    p,
                    {
                        "title": "title",
                        "description": "description",
                        "status": "status",
                        "priority": "priority",
                        "request_type": "type",
                        "queue": "queue",
                        "agent_employee_id": "agentId",
                    },
                ),
            },
        )
        for i, value in enumerate(p.get("attachments", [])):
            scope, id = attachment(value, "request", "/api/desk/files/")
            put(
                "request_attachments",
                {"request_id": r["id"], "scope": scope, "attachment_id": id, "position": i},
            )
    for r in data["crm", "desk_comments"]:
        put(
            "comments",
            {
                "id": r["id"],
                "request_id": r["request_id"],
                "body": r["text"],
                "actor_user_id": r["actorUserId"],
                "actor_employee_id": r["actorEmployeeId"],
                "actor_label": r["actor"],
                "created_at": r["created_at"],
                "extra_data": r,
            },
        )
        for i, value in enumerate(json.loads(r["attachments"])):
            scope, id = attachment(value, "request", "/api/desk/files/")
            put(
                "comment_attachments",
                {"comment_id": r["id"], "scope": scope, "attachment_id": id, "position": i},
            )
    for r in data["crm", "desk_tasks"]:
        p = json.loads(r["payload"])
        put(
            "tasks",
            {
                "id": r["id"],
                "request_id": r["request_id"],
                **dates(p),
                **fields(
                    p,
                    {
                        "client_id": "client",
                        "owner_employee_id": "owner",
                        "title": "title",
                        "status": "status",
                        "priority": "priority",
                        "due_date": "due",
                    },
                ),
                "done": p["done"],
                "extra_data": p,
            },
        )
    for r in data["leave", "absences"]:
        p = json.loads(r["payload"])
        scope, id = attachment(p.get("attachment"), "leave")
        put(
            "leaves",
            {
                **base(r, p),
                **dates(p),
                "employee_id": r["employee"],
                "start_date": r["start"],
                "end_date": r["end"],
                "status": r["status"],
                **fields(
                    p,
                    {
                        "leave_type": "type",
                        "days": "days",
                        "reason": "reason",
                        "created_by_label": "createdBy",
                        "resolved_at": "resolvedAt",
                        "resolved_by_label": "resolvedBy",
                        "resolution_comment": "resolutionComment",
                    },
                ),
                "attachment_scope": scope,
                "attachment_id": id,
            },
        )
    for database, table, relation, source in [
        ("team", "employee_audit", "employee_id", "employee_id"),
        ("team", "user_audit", "user_id", "entityId"),
        ("crm", "activity", "client_id", "client_id"),
        ("crm", "desk_events", "request_id", "request_id"),
        ("leave", "absence_events", "leave_id", "absence_id"),
    ]:
        for r in data[database, table]:
            put(
                "audit_entries",
                {
                    "source_table": table,
                    "source_id": r["id"],
                    "action": r["action"],
                    "actor_user_id": r["actorUserId"],
                    "actor_employee_id": r["actorEmployeeId"],
                    "actor_label": r.get("actor"),
                    "entity_type": r.get("entityType"),
                    "entity_id": r.get("entityId"),
                    relation: r[source],
                    "occurred_at": r.get("timestamp") or r.get("created_at"),
                    "reference": r.get("reference"),
                    "comment": r.get("comment"),
                    "changed_fields": json.loads(r["fields"]) if "fields" in r else None,
                    "metadata": r,
                },
            )
    return tables


def prepare(work):
    report = inspect(work)
    if report["issues"]:
        raise ValueError(
            "El inventario detectó incompatibilidades; revisá el informe antes de exportar."
        )
    policy = json.loads((ROOT / "src/access-policy.json").read_text(encoding="utf-8"))
    return convert(read_source(work), policy)
