import _isolation  # noqa: F401  Debe ir antes que el backend.
import os

os.environ["NEXO_TEST_MODE"] = "1"
import sys, tempfile, os, threading, json, urllib.request, urllib.error, unittest, base64, gc
from pathlib import Path

root = Path.cwd()
tmp = tempfile.TemporaryDirectory()
os.environ["NEXO_TEAM_DATA"] = tmp.name + "/team"
os.environ["NEXO_CRM_DATA"] = tmp.name + "/crm"
os.environ["NEXO_LEAVE_DATA"] = tmp.name + "/leaves"
sys.path.insert(0, str(root / "src/backend"))
import leave_server as lv

lv.team.init()
lv.desk.init()
lv.init()
server = lv.team.ThreadingHTTPServer(("127.0.0.1", 0), lv.Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}"


def call(path="", data=None, role="admin"):
    req = urllib.request.Request(
        base + "/api/absences" + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json", "X-Nexo-Client": "team", "X-Nexo-View": role},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def item(id):
    return next(r for r in call()[1]["items"] if r["id"] == id)


class Tests(unittest.TestCase):
    def test_01_seed_and_privacy(self):
        d = call()[1]
        self.assertEqual(len(d["items"]), 2)
        self.assertEqual(item(1)["days"], 9)
        self.assertEqual(item(2)["type"], "Permiso personal")
        self.assertEqual(call(role="employee")[1]["items"], [])
        self.assertEqual(call(role="client")[0], 403)
        p = call("/availability")[1]["periods"][0]
        self.assertNotIn("reason", p)
        self.assertNotIn("attachment", p)

    def test_02_dates_and_overlap(self):
        d = dict(
            employee=3,
            type="Vacaciones",
            start="2026-09-15",
            end="2026-09-14",
            reason="",
            attachment="",
        )
        self.assertEqual(call(data=d)[0], 422)
        d["end"] = "2026-09-20"
        self.assertEqual(call(data=d)[0], 422)
        d["start"] = "2026-09-19"
        self.assertEqual(call(data=d)[0], 201)

    def test_03_employee_forced_identity(self):
        code, r = call(
            data=dict(
                employee=3,
                type="Permiso personal",
                start="2026-10-01",
                end="2026-10-03",
                reason="Comentario privado",
                status="Aprobada",
            ),
            role="employee",
        )
        self.assertEqual(code, 201)
        self.assertEqual(r["item"]["employee"], 1)
        self.assertEqual(r["item"]["status"], "Pendiente")
        self.assertEqual(r["item"]["days"], 3)
        id = r["item"]["id"]
        self.assertEqual(
            call("/" + str(id) + "/approve", dict(version=1, confirm=True), role="employee")[0], 403
        )

    def test_04_approve_cancel_availability(self):
        r = item(2)
        self.assertEqual(call("/2/approve", dict(version=r["version"], confirm=False))[0], 422)
        self.assertEqual(
            call("/2/approve", dict(version=r["version"], confirm=True, comment="Acordado"))[0], 200
        )
        self.assertTrue(any(p["employee"] == 2 for p in call("/availability")[1]["periods"]))
        self.assertEqual(call("/2/cancel", dict(version=2, confirm=True), role="employee")[0], 403)
        self.assertEqual(
            call("/2/cancel", dict(version=2, confirm=True, comment="Cambio de fechas"))[0], 200
        )
        self.assertFalse(any(p["employee"] == 2 for p in call("/availability")[1]["periods"]))
        self.assertEqual(item(2)["resolvedBy"], "Administración local · sin autenticación")
        self.assertTrue(item(2)["cancelledAt"])

    def test_05_reject_and_conflict(self):
        r = next(r for r in call()[1]["items"] if r["employee"] == 1)
        path = "/" + str(r["id"])
        self.assertEqual(
            call(path + "/reject", dict(version=r["version"], confirm=True, comment=""))[0], 422
        )
        self.assertEqual(
            call(
                path + "/reject", dict(version=r["version"], confirm=True, comment="Revisar fechas")
            )[0],
            200,
        )
        self.assertEqual(call(path + "/approve", dict(version=r["version"], confirm=True))[0], 409)

    def test_06_cancel_own_pending(self):
        code, r = call(
            data=dict(type="Estudio / Examen", start="2026-11-01", end="2026-11-01"),
            role="employee",
        )
        self.assertEqual(code, 201)
        self.assertEqual(
            call(
                "/" + str(r["item"]["id"]) + "/cancel",
                dict(version=1, confirm=True),
                role="employee",
            )[0],
            200,
        )

    def test_07_reopen_and_file_privacy(self):
        lv.init()
        self.assertEqual(item(2)["status"], "Cancelada")
        self.assertTrue(call()[1]["events"])
        self.assertEqual(call("/1/attachment", role="employee")[0], 403)
        self.assertEqual(call("/files", dict(name="test.exe", base64="ZmFrZQ=="))[0], 422)


try:
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
finally:
    server.shutdown()
    server.server_close()
    gc.collect()
    tmp.cleanup()
sys.exit(not result.wasSuccessful())
