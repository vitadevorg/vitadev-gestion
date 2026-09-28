import _isolation  # noqa: F401  Debe ir antes que el backend.
import os

os.environ["NEXO_TEST_MODE"] = "1"
import importlib.util, tempfile, os, json, unittest, urllib.request, urllib.error, threading, sys
from pathlib import Path

temp = tempfile.TemporaryDirectory()
os.environ["NEXO_TEAM_DATA"] = temp.name
spec = importlib.util.spec_from_file_location(
    "team_server", Path("src/backend/team_server.py").resolve()
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.init()
server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
origin = f"http://127.0.0.1:{server.server_port}"


def req(path="", data=None, method=None):
    r = urllib.request.Request(
        origin + "/api/team" + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json", "X-Nexo-Client": "team"},
        method=method or ("POST" if data is not None else "GET"),
    )
    try:
        with urllib.request.urlopen(r) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


class TeamTests(unittest.TestCase):
    def test_01_seed(self):
        status, res = req()
        self.assertEqual(status, 200)
        self.assertEqual(len(res["employees"]), 6)
        self.assertFalse(res["accessEnforcement"])

    def test_02_required(self):
        status, res = req("", {})
        self.assertEqual(status, 422)
        self.assertIn("legajo", res["errors"])

    def test_03_unique(self):
        e = req()[1]["employees"][0]
        e["id"] = None
        status, res = req("", e)
        self.assertEqual(status, 422)
        self.assertIn("email", res["errors"])
        self.assertIn("legajo", res["errors"])

    def test_04_dependent_role(self):
        e = req()[1]["employees"][0]
        e["role"] = "Puesto arbitrario"
        status, res = req("/1", e, "PUT")
        self.assertEqual(status, 422)
        self.assertIn("role", res["errors"])

    def test_05_cycle(self):
        e = req()[1]["employees"][0]
        e["managerId"] = 2
        status, res = req("/1", e, "PUT")
        self.assertEqual(status, 422)
        self.assertIn("managerId", res["errors"])

    def test_06_create_reload_update(self):
        e = req()[1]["employees"][0].copy()
        e.update(
            firstName="Prueba",
            lastName="Persistencia",
            email="persist@example.com",
            legajo="TEST-01",
            managerId=None,
        )
        status, res = req("", e)
        self.assertEqual(status, 201)
        employee = res["employee"]
        self.assertEqual(req()[1]["employees"][-1]["name"], "Prueba Persistencia")
        employee["phone"] = "123456"
        status, res = req("/" + str(employee["id"]), employee, "PUT")
        self.assertEqual(status, 200)
        status, res = req("/" + str(employee["id"]), employee, "PUT")
        self.assertEqual(status, 409)

    def test_07_disable_keeps_history(self):
        employee = req()[1]["employees"][3]
        status, res = req(
            "/4/deactivate", {"version": employee["version"], "reason": "Prueba controlada"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(res["employee"]["laborStatus"], "Inactivo")
        self.assertFalse(res["employee"]["access"]["enabled"])
        self.assertTrue(req("/4/audit")[1]["events"])

    def test_08_access_separate(self):
        e = req()[1]["employees"][1]
        status, res = req(
            "/2/access",
            {"version": e["version"], "access": {"enabled": True, "role": "Supervisor"}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(res["employee"]["role"], e["role"])
        self.assertEqual(res["employee"]["access"]["role"], "Supervisor")

    def test_09_invalid_photo(self):
        status, res = req("/photos", {"base64": "ZmFrZQ=="})
        self.assertEqual(status, 422)
        self.assertIn("photo", res["errors"])

    def test_10_origin(self):
        request = urllib.request.Request(
            origin + "/api/team",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "X-Nexo-Client": "team",
                "Origin": "https://example.com",
            },
        )
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(request)
        self.assertEqual(e.exception.code, 403)


if __name__ == "__main__":
    try:
        result = unittest.main(exit=False).result
    finally:
        server.shutdown()
        server.server_close()
        temp.cleanup()
    sys.exit(not result.wasSuccessful())
