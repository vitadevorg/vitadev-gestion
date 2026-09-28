import _isolation  # noqa: F401  Debe ir antes que el backend.
import os

os.environ["NEXO_TEST_MODE"] = "1"
import sys, tempfile, os, threading, json, urllib.request, urllib.error, unittest, io, base64
from pathlib import Path

root = Path.cwd()
tmp = tempfile.TemporaryDirectory()
os.environ["NEXO_TEAM_DATA"] = tmp.name + "/team"
os.environ["NEXO_CRM_DATA"] = tmp.name + "/crm"
sys.path.insert(0, str(root / "src/backend"))
import crm_server as crm

crm.team.init()
crm.init()
server = crm.team.ThreadingHTTPServer(("127.0.0.1", 0), crm.Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}/api/crm"


def call(path="", data=None, method="POST"):
    req = urllib.request.Request(
        url + path,
        data=json.dumps(data).encode() if data is not None else None,
        method=method if data is not None else "GET",
        headers={"Content-Type": "application/json", "X-Nexo-Client": "team"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def cuit(n):
    v = "30" + str(n).zfill(8)
    check = 11 - sum(int(x) * w for x, w in zip(v, [5, 4, 3, 2, 7, 6, 5, 4, 3, 2])) % 11
    return v + str(0 if check == 11 else 9 if check == 10 else check)


def client(n):
    return dict(
        name="Prueba " + str(n),
        legalName="Empresa Prueba",
        cuit=cuit(n),
        organizationType="Empresa",
        country="Argentina",
        province="Tucumán",
        city="Capital",
        owner=1,
        status="Prospecto",
        logo="",
        primaryContact=dict(firstName="Nombre", lastName="Apellido", email="test@example.com"),
    )


class Tests(unittest.TestCase):
    def test_01_seed(self):
        code, d = call()
        self.assertEqual(code, 200)
        self.assertEqual(len(d["clients"]), 2)
        self.assertEqual(len(d["catalog"]), 1)
        self.assertEqual(d["contracts"], [])

    def test_02_cuit_and_atomic_contact(self):
        d = client(123)
        d["cuit"] = "123"
        code, r = call("/clients", d)
        self.assertEqual(code, 422)
        self.assertIn("cuit", r["errors"])
        d = client(123)
        d["primaryContact"]["email"] = "bad"
        code, r = call("/clients", d)
        self.assertEqual(code, 422)
        self.assertEqual(len(call()[1]["clients"]), 2)

    def test_03_create_duplicate_conflict(self):
        code, r = call("/clients", client(123))
        self.assertEqual(code, 201)
        d = r["record"]
        self.assertEqual(call("/clients", client(123))[0], 422)
        d["name"] = "Nombre actualizado"
        self.assertEqual(call("/clients/" + str(d["id"]), d, "PUT")[0], 200)
        self.assertEqual(call("/clients/" + str(d["id"]), d, "PUT")[0], 409)

    def test_04_catalog_subscription(self):
        code, r = call(
            "/catalog",
            dict(
                name="Consultoría",
                description="Servicio de software",
                type="Servicio",
                status="Activo",
                plans=["Inicial"],
                configFields=["Asesoramiento"],
            ),
        )
        self.assertEqual(code, 201)
        pid = r["record"]["id"]
        d = dict(
            clientId=1,
            productId=pid,
            plan="Inicial",
            status="Activo",
            start="2026-09-11",
            configuration=["Asesoramiento"],
        )
        self.assertEqual(call("/subscriptions", d)[0], 201)
        d["configuration"] = ["Turnos"]
        self.assertEqual(call("/subscriptions", d)[0], 422)

    def test_05_contract_dates_relations(self):
        all = call()[1]
        sid = next(s["id"] for s in all["subscriptions"] if s["clientId"] == 1)
        other = next(s["id"] for s in all["subscriptions"] if s["clientId"] == 2)
        d = dict(
            clientId=1,
            number="CTR-TEST",
            subscriptionIds=[sid],
            status="Vigente",
            start="2026-09-11",
            end="2026-09-10",
            renewal="Manual",
            period="Mensual",
            currency="ARS",
            amount="100.00",
        )
        self.assertEqual(call("/contracts", d)[0], 422)
        d["end"] = "2027-09-11"
        d["subscriptionIds"] = [other]
        self.assertEqual(call("/contracts", d)[0], 422)
        d["subscriptionIds"] = [sid]
        self.assertEqual(call("/contracts", d)[0], 201)
        self.assertEqual(call("/contracts", d)[0], 422)

    def test_06_principal(self):
        contacts = []
        for n in ["Uno", "Dos"]:
            code, r = call(
                "/contacts",
                dict(
                    clientId=1,
                    firstName=n,
                    lastName="Apellido",
                    email="test@example.com",
                    status="Activo",
                    principal=True,
                ),
            )
            self.assertEqual(code, 201)
            contacts.append(r["record"])
        self.assertEqual(
            sum(p["principal"] for p in call()[1]["contacts"] if p["clientId"] == 1), 1
        )

    def test_07_files(self):
        self.assertEqual(
            call(
                "/files",
                dict(
                    name="falso.pdf",
                    kind="document",
                    base64=base64.b64encode(b"%PDF-false").decode(),
                ),
            )[0],
            422,
        )
        from pypdf import PdfWriter

        stream = io.BytesIO()
        w = PdfWriter()
        w.add_blank_page(width=200, height=200)
        w.write(stream)
        raw = stream.getvalue()
        code, r = call(
            "/files",
            dict(
                name="Contrato firmado.pdf", kind="document", base64=base64.b64encode(raw).decode()
            ),
        )
        self.assertEqual(code, 201)
        with urllib.request.urlopen(url.replace("/api/crm", "") + r["url"]) as response:
            self.assertEqual(response.read(), raw)

    def test_08_lifecycle_history(self):
        d = call()[1]["clients"][0]
        self.assertEqual(
            call(
                "/clients/1",
                {**d, "status": "Finalizado", "lifecycle": True, "confirm": False},
                "PUT",
            )[0],
            422,
        )
        self.assertEqual(
            call(
                "/clients/1",
                {**d, "status": "Finalizado", "lifecycle": True, "confirm": True},
                "PUT",
            )[0],
            200,
        )
        all = call()[1]
        self.assertTrue(any(s["clientId"] == 1 for s in all["subscriptions"]))
        self.assertTrue(any(a["client_id"] == 1 for a in all["activity"]))

    def test_09_reopen_database(self):
        crm.init()
        self.assertTrue(any(c["name"] == "Nombre actualizado" for c in call()[1]["clients"]))


try:
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
finally:
    server.shutdown()
    server.server_close()
    import gc

    gc.collect()
    tmp.cleanup()
sys.exit(not result.wasSuccessful())
