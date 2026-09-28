"""Flujo HTTP autenticado y garantías transaccionales en un esquema desechable.

Ejecutar mediante run_postgres_suite.py, nunca sobre vitadev.
"""

import _isolation  # noqa: F401  Debe ir antes que el backend.
import os, sys, unittest, json, sqlite3
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if os.environ.get("VITADEV_DATABASE") != "postgres" or not os.environ.get(
    "VITADEV_DB_SCHEMA", ""
).startswith("vitadev_test_"):
    raise SystemExit("Esta prueba requiere el ejecutor de esquemas desechables.")


def no_sqlite(*args, **kwargs):
    raise AssertionError("El backend PostgreSQL intentó abrir SQLite")


sqlite3.connect = no_sqlite
import test_auth as fixture

s = fixture.s


class Flow(unittest.TestCase):
    def setUp(self):
        self.client = fixture.Client()
        self.assertEqual(self.client.login()[0], 200)

    def call(self, path, data=None, code=200, method=None, client=None):
        status, result = (client or self.client).call(path, data, method)
        self.assertEqual(status, code, (path, result))
        return result

    def test_01_authenticated_business_flow(self):
        # Equipo y acceso: el puesto sigue siendo independiente del perfil de acceso.
        employee = self.call("/api/team")["employees"][0].copy()
        employee.update(
            firstName="Prueba",
            lastName="Integración",
            legajo="PG-FLOW",
            email="flow-employee@test.invalid",
            managerId=None,
        )
        employee = self.call("/api/team", employee, 201)["employee"]
        employee = self.call(
            "/api/team/" + str(employee["id"]), {**employee, "phone": "123456"}, method="PUT"
        )["employee"]
        user = self.call(
            "/api/users",
            dict(
                email=employee["email"],
                password="Nexo-test-password-2026",
                employeeId=employee["id"],
                role="EMPLOYEE",
                permissionProfile="SUPPORT",
                status="ACTIVE",
            ),
            201,
        )["user"]
        worker = fixture.Client()
        self.assertEqual(worker.login(employee["email"])[0], 200)
        self.call("/api/users", code=403, client=worker)
        # Cliente, contacto, servicio, contratación y contrato relacionados.
        customer = self.call(
            "/api/crm/clients",
            dict(
                name="Cliente de prueba transaccional",
                legalName="Empresa de prueba",
                cuit="30000000120",
                organizationType="Empresa",
                country="Argentina",
                province="Tucumán",
                city="Capital",
                owner=1,
                status="Activo",
                logo="",
                primaryContact=dict(
                    firstName="Contacto", lastName="Prueba", email="contact@test.invalid"
                ),
            ),
            201,
        )["record"]
        customer = self.call(
            "/api/crm/clients/" + str(customer["id"]),
            {**customer, "city": "Ciudad actualizada"},
            method="PUT",
        )["record"]
        contact = next(
            c for c in self.call("/api/crm")["contacts"] if c["clientId"] == customer["id"]
        )
        product = self.call(
            "/api/crm/catalog",
            dict(
                name="Servicio de prueba PG",
                description="Prueba aislada",
                type="Servicio",
                status="Activo",
                plans=["Base"],
                configFields=["Soporte"],
            ),
            201,
        )["record"]
        subscription = self.call(
            "/api/crm/subscriptions",
            dict(
                clientId=customer["id"],
                productId=product["id"],
                plan="Base",
                status="Activo",
                start=date.today().isoformat(),
                configuration=["Soporte"],
            ),
            201,
        )["record"]
        self.call(
            "/api/crm/contracts",
            dict(
                clientId=customer["id"],
                number="PG-FLOW-CTR",
                subscriptionIds=[subscription["id"]],
                status="Vigente",
                start=date.today().isoformat(),
                end=(date.today() + timedelta(days=365)).isoformat(),
                renewal="Manual",
                period="Mensual",
                currency="ARS",
                amount="100.00",
            ),
            201,
        )
        request = self.call(
            "/api/desk/requests",
            dict(
                clientId=customer["id"],
                subscriptionId=subscription["id"],
                contactId=contact["id"],
                title="Prueba autenticada completa",
                description="Verificar persistencia relacional",
                type="Consulta",
                priority="Media",
                attachments=[],
            ),
            201,
        )["request"]
        path = "/api/desk/requests/" + str(request["id"])
        request = self.call(
            path + "/update",
            dict(
                version=request["version"],
                agentId=employee["id"],
                status=s.team.REQUEST.IN_PROGRESS,
            ),
        )["request"]
        request = self.call(
            path + "/comments",
            dict(version=request["version"], text="Comentario autenticado", attachments=[]),
            client=worker,
        )["request"]
        request = self.call(
            path + "/tasks",
            dict(
                version=request["version"],
                title="Verificar servicio",
                owner=employee["id"],
                priority="Media",
                due="",
            ),
        )["request"]
        task = next(t for t in self.call("/api/desk")["tasks"] if t["ticket"] == request["id"])
        request = self.call(
            path + "/task-status",
            dict(version=request["version"], taskId=task["id"], done=True),
            client=worker,
        )["request"]
        self.call(
            path + "/update", dict(version=request["version"], status=s.team.REQUEST.RESOLVED)
        )
        leave = self.call(
            "/api/absences",
            dict(
                employee=1,
                type="Vacaciones",
                start=date.today().isoformat(),
                end=(date.today() + timedelta(days=1)).isoformat(),
                reason="",
                attachment="",
            ),
            201,
            client=worker,
        )["item"]
        self.assertEqual(leave["employee"], employee["id"])
        self.call(
            "/api/absences/" + str(leave["id"]) + "/approve",
            dict(version=leave["version"], confirm=True),
        )
        periods = self.call("/api/absences/availability")["periods"]
        self.assertTrue(
            any(
                p["employee"] == employee["id"] and p["status"] == s.team.LEAVE.APPROVED
                for p in periods
            )
        )
        report = self.call(
            "/api/reports?start=" + date.today().isoformat() + "&end=" + date.today().isoformat()
        )
        self.assertGreaterEqual(report["kpis"]["received"], 1)
        self.assertGreaterEqual(report["kpis"]["resolved"], 1)
        # Verificar tablas reales desde otra conexión, no solamente la respuesta HTTP.
        with s.team.connect() as c:
            stored = c.raw.execute(
                "SELECT t.done,t.owner_employee_id,r.client_id,r.subscription_id FROM tasks t JOIN requests r ON r.id=t.request_id WHERE t.id=%s",
                (task["id"],),
            ).fetchone()
            self.assertEqual(stored, (True, employee["id"], customer["id"], subscription["id"]))
            actor = c.raw.execute(
                "SELECT actor_user_id FROM comments WHERE request_id=%s", (request["id"],)
            ).fetchone()[0]
            self.assertEqual(actor, user["id"])
            events = c.execute(
                "SELECT * FROM user_audit WHERE entityId=?", (user["id"],)
            ).fetchall()
            self.assertTrue(events)
            self.assertTrue(all(isinstance(json.loads(e["metadata"]), dict) for e in events))
            self.assertTrue(all(e["timestamp"].endswith("+00:00") for e in events))
        self.call("/api/auth/logout", {}, client=worker)
        self.call("/api/auth/me", code=401, client=worker)

    def test_02_rollback_includes_audit(self):
        with s.team.connect() as c:
            before = c.execute("SELECT * FROM employees WHERE id=1").fetchone()
            count = c.execute("SELECT count(*) FROM employee_audit").fetchone()[0]
        with self.assertRaises(RuntimeError):
            with s.team.connect() as c:
                c.execute("BEGIN IMMEDIATE")
                payload = json.loads(before["payload"])
                payload["phone"] = "ROLLBACK"
                c.execute(
                    "UPDATE employees SET payload=?,version=version+1 WHERE id=?",
                    (json.dumps(payload), 1),
                )
                c.execute(
                    "INSERT INTO employee_audit(employee_id,action,fields,created_at,actor) VALUES(?,?,?,?,?)",
                    (1, "Prueba revertida", "[]", s.team.now(), "Prueba"),
                )
                raise RuntimeError("Reversión intencional")
        with s.team.connect() as c:
            self.assertEqual(c.execute("SELECT * FROM employees WHERE id=1").fetchone(), before)
            self.assertEqual(c.execute("SELECT count(*) FROM employee_audit").fetchone()[0], count)

    def test_03_concurrent_versions_and_leave_overlap(self):
        clients = [fixture.Client(), fixture.Client()]
        for c in clients:
            self.assertEqual(c.login()[0], 200)
        employee = self.call("/api/team")["employees"][0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    c.call, "/api/team/1", {**employee, "phone": "concurrent-" + str(i)}, "PUT"
                )
                for i, c in enumerate(clients)
            ]
            self.assertEqual(sorted(f.result()[0] for f in futures), [200, 409])
        start = (date.today() + timedelta(days=500)).isoformat()
        data = dict(employee=1, type="Vacaciones", start=start, end=start, reason="", attachment="")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(c.call, "/api/absences", data) for c in clients]
            self.assertEqual(sorted(f.result()[0] for f in futures), [201, 422])

    def test_04_native_fk_and_historical_fields(self):
        import psycopg

        with self.assertRaises(psycopg.IntegrityError):
            with s.team.connect() as c:
                c.raw.execute("UPDATE requests SET contact_id=999999 WHERE id=1042")
        with s.team.connect() as c:
            c.lock()
            c.raw.execute(
                'UPDATE employees SET extra_data=extra_data||\'{"historicalField":{"value":1}}\'::jsonb WHERE id=1'
            )
        employee = self.call("/api/team")["employees"][0]
        self.call("/api/team/1", {**employee, "phone": "historical-test"}, method="PUT")
        with s.team.connect() as c:
            self.assertEqual(
                c.raw.execute(
                    "SELECT extra_data->'historicalField' FROM employees WHERE id=1"
                ).fetchone()[0],
                {"value": 1},
            )

    def test_05_concurrent_last_admin_accounts(self):
        second = s.auth.save_user(
            dict(
                email="second-admin@test.invalid",
                password="Nexo-test-password-2026",
                employeeId=None,
                role="ADMIN",
                permissionProfile="ADMINISTRATOR",
                status="ACTIVE",
            )
        )
        with s.team.connect() as c:
            first = s.auth.public(c.execute("SELECT * FROM users WHERE id=1").fetchone(), c)

        def disable(user):
            try:
                s.auth.save_user({**user, "status": "DISABLED"}, user["id"])
                return 200
            except s.team.Validation as e:
                return e.status

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(disable, [first, second])), [200, 422])
        # Restablecer la cuenta de la fixture para el último escenario.
        s.auth.save_user({**first, "status": "ACTIVE"}, first["id"])
        s.auth.save_user({**second, "status": "DISABLED"}, second["id"])

    def test_06_concurrent_last_admin_employees(self):
        second = s.auth.save_user(
            dict(
                email="linked-admin@test.invalid",
                password="Nexo-test-password-2026",
                employeeId=4,
                role="ADMIN",
                permissionProfile="ADMINISTRATOR",
                status="ACTIVE",
            )
        )
        other = fixture.Client()
        self.assertEqual(other.login(second["email"])[0], 200)
        employees = {e["id"]: e for e in self.call("/api/team")["employees"]}

        def deactivate(pair):
            client, id = pair
            return client.call(
                "/api/team/" + str(id) + "/deactivate",
                dict(version=employees[id]["version"], reason="Prueba concurrente"),
            )[0]

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(
                sorted(pool.map(deactivate, [(self.client, 1), (other, 4)])), [200, 422]
            )
        with s.team.connect() as c:
            self.assertTrue(s.team.pg.other_active_admin(c, 0))


if __name__ == "__main__":
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Flow)
        )
    finally:
        fixture.server.shutdown()
        fixture.server.server_close()
    sys.exit(not result.wasSuccessful())
