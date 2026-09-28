"""Lectura nativa PostgreSQL para la adaptación progresiva del backend.

No modifica el proveedor de la aplicación ni usa SQLite como intermediario.
Las respuestas conservan la forma que consumen los módulos existentes.
"""

import copy
from datetime import date, datetime
from decimal import Decimal


def scalar(value):
    if isinstance(value, Decimal):
        return str(value)
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def payload(row, mapping):
    result = copy.deepcopy(row.get("extra_data") or {})
    for column, key in mapping.items():
        value = scalar(row[column])
        # El frontend utiliza cadenas vacías para los campos opcionales de formularios.
        result[key] = "" if value is None and isinstance(result.get(key), str) else value
    result["id"] = row["id"]
    if "version" in row:
        result["version"] = row["version"]
    return result


class PostgresRepository:
    def __init__(self, connection, schema="vitadev"):
        self.connection = connection
        self.schema = schema

    def rows(self, table):
        from psycopg import sql
        from psycopg.rows import dict_row

        allowed = {
            "employees",
            "employee_skills",
            "users",
            "permissions",
            "permission_profiles",
            "profile_permissions",
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
        }
        if table not in allowed:
            raise ValueError("Tabla no permitida")
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                sql.SQL("SELECT * FROM {}.{}").format(
                    sql.Identifier(self.schema), sql.Identifier(table)
                )
            )
            return cursor.fetchall()

    def employees(self):
        skills = self.rows("employee_skills")
        result = []
        for row in self.rows("employees"):
            item = payload(
                row,
                {
                    "email": "email",
                    "legajo": "legajo",
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
            )
            item["name"] = item["firstName"] + " " + item["lastName"]
            item["skills"] = [
                r["skill"]
                for r in sorted(skills, key=lambda r: r["position"])
                if r["employee_id"] == row["id"]
            ]
            result.append(item)
        return sorted(result, key=lambda r: r["id"])

    def access_policy(self):
        profiles = self.rows("permission_profiles")
        links = self.rows("profile_permissions")
        return {
            "permissions": sorted(r["code"] for r in self.rows("permissions")),
            "profiles": {
                r["code"]: sorted(
                    p["permission_code"] for p in links if p["profile_code"] == r["code"]
                )
                for r in profiles
            },
            "profileLabels": {r["code"]: r["label"] for r in profiles},
        }

    def report_sources(self):
        data = {"employees": self.employees()}
        mappings = {
            "clients": (
                "clients",
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
            "contacts": (
                "contacts",
                {
                    "client_id": "clientId",
                    "first_name": "firstName",
                    "last_name": "lastName",
                    "email": "email",
                    "position": "position",
                    "phone": "phone",
                    "role": "role",
                    "status": "status",
                    "is_principal": "principal",
                },
            ),
            "catalog": (
                "products",
                {
                    "name": "name",
                    "description": "description",
                    "product_type": "type",
                    "status": "status",
                },
            ),
            "subscriptions": (
                "subscriptions",
                {
                    "client_id": "clientId",
                    "product_id": "productId",
                    "plan": "plan",
                    "status": "status",
                    "start_date": "start",
                },
            ),
            "contracts": (
                "contracts",
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
            "requests": (
                "requests",
                {
                    "client_id": "clientId",
                    "subscription_id": "subscriptionId",
                    "contact_id": "contactId",
                    "title": "title",
                    "description": "description",
                    "status": "status",
                    "priority": "priority",
                    "request_type": "type",
                    "queue": "queue",
                    "agent_employee_id": "agentId",
                },
            ),
            "tasks": (
                "tasks",
                {
                    "request_id": "ticket",
                    "client_id": "client",
                    "owner_employee_id": "owner",
                    "title": "title",
                    "status": "status",
                    "priority": "priority",
                    "due_date": "due",
                    "done": "done",
                },
            ),
            "leaves": (
                "leaves",
                {
                    "employee_id": "employee",
                    "leave_type": "type",
                    "start_date": "start",
                    "end_date": "end",
                    "days": "days",
                    "status": "status",
                    "reason": "reason",
                    "created_by_label": "createdBy",
                    "resolved_at": "resolvedAt",
                    "resolved_by_label": "resolvedBy",
                    "resolution_comment": "resolutionComment",
                },
            ),
        }
        for key, (table, mapping) in mappings.items():
            data[key] = [
                payload(row, {**mapping, "created_at": "createdAt", "updated_at": "updatedAt"})
                for row in self.rows(table)
            ]
        for key, table in [("plans", "product_plans"), ("configFields", "product_options")]:
            rows = self.rows(table)
            for product in data["catalog"]:
                product[key] = [
                    r["name"]
                    for r in sorted(rows, key=lambda r: r["position"])
                    if r["product_id"] == product["id"]
                ]
        options = self.rows("subscription_options")
        contract_links = self.rows("contract_subscriptions")
        for item in data["subscriptions"]:
            item["configuration"] = [
                r["option_name"]
                for r in sorted(options, key=lambda r: r["position"])
                if r["subscription_id"] == item["id"]
            ]
        for item in data["contracts"]:
            item["subscriptionIds"] = [
                r["subscription_id"]
                for r in sorted(contract_links, key=lambda r: r["position"])
                if r["contract_id"] == item["id"]
            ]
        audit = self.rows("audit_entries")
        data["importedClients"] = {
            r["client_id"]
            for r in audit
            if r["source_table"] == "activity" and r["action"] == "Registro inicial importado"
        }
        data["events"] = [
            {
                **(r["metadata"] or {}),
                "id": r["source_id"],
                "request_id": r["request_id"],
                "action": r["action"],
                "reference": r["reference"],
                "actor": r["actor_label"],
                "created_at": scalar(r["occurred_at"]),
                "actorUserId": r["actor_user_id"],
                "actorEmployeeId": r["actor_employee_id"],
            }
            for r in audit
            if r["source_table"] == "desk_events"
        ]
        return data
