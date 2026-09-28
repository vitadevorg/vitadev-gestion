import _isolation  # noqa: F401  Debe ir antes que el backend.
import os

os.environ["NEXO_TEST_MODE"] = "1"
import sys, unittest, io
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/backend"))
import report_server as r


class Reports(unittest.TestCase):
    def setUp(self):
        self.d = {
            "clients": [
                dict(id=1, name="Cliente", status="Activo", createdAt="2026-01-01", imported=True)
            ],
            "catalog": [dict(id=2, name="Producto")],
            "subscriptions": [dict(id=3, clientId=1, productId=2, status="Activo")],
            "requests": [],
            "events": [],
            "tasks": [],
            "employees": [dict(id=1, name="Ana", laborStatus="Activo", availability="Disponible")],
            "leaves": [dict(employee=1, status="Aprobada", start="2026-09-10", end="2026-09-15")],
        }
        self.add(1, "2026-09-01T12:00:00+00:00", "2026-09-02T12:00:00+00:00")
        self.add(2, "2026-09-11T12:00:00+00:00", "2026-09-12T12:00:00+00:00")

    def add(self, id, created, resolved=None, imported=False):
        self.d["requests"].append(
            dict(
                id=id,
                clientId=1,
                subscriptionId=3,
                createdAt=created,
                status="Resuelta" if resolved else "Nueva",
                priority="Media",
                agentId=1,
            )
        )
        self.d["events"].append(
            dict(
                request_id=id,
                action="Solicitud importada" if imported else "Solicitud creada",
                reference="",
                created_at=created,
            )
        )
        if resolved:
            self.d["events"].append(
                dict(
                    request_id=id,
                    action="Estado actualizado",
                    reference="Resuelta",
                    created_at=resolved,
                )
            )

    def report(self, **kw):
        return r.analyze(
            self.d, date(2026, 9, 11), date(2026, 9, 12), today=date(2026, 9, 12), **kw
        )

    def test_calculations(self):
        k = self.report()["kpis"]
        self.assertEqual(k["received"], 1)
        self.assertEqual(k["rate"], 100)
        self.assertEqual(k["minutes"], 1440)

    def test_imports(self):
        self.add(3, "2026-09-11T12:00:00+00:00", imported=True)
        a = self.report()
        self.assertEqual(a["kpis"]["received"], 1)
        self.assertEqual(a["imported"], 1)

    def test_filters(self):
        self.assertEqual(self.report(client=1, product=2)["kpis"]["received"], 1)
        self.d["catalog"].append(dict(id=9, name="Otro"))
        self.assertEqual(self.report(product=9)["kpis"]["received"], 0)

    def test_timezone(self):
        self.assertEqual(r.day("2026-09-11T01:00:00+00:00"), date(2026, 9, 10))

    def test_historical(self):
        a = r.analyze(self.d, date(2026, 9, 1), date(2026, 9, 2), today=date(2026, 9, 12))
        self.assertIsNone(a["kpis"]["active"])
        self.assertEqual(a["availability"], {})

    def test_leave(self):
        self.assertEqual(self.report()["availability"]["De licencia"], 1)

    def test_no_comparison(self):
        self.assertIsNone(self.report()["kpis"]["receivedChange"])

    def test_comparison(self):
        self.add(3, "2026-09-09T12:00:00+00:00", "2026-09-10T12:00:00+00:00")
        self.assertEqual(self.report()["kpis"]["receivedChange"], 0)

    def test_pdf(self):
        from pypdf import PdfReader

        raw = r.pdf_report(self.report())
        self.assertTrue(raw.startswith(b"%PDF"))
        text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(raw)).pages)
        self.assertIn("2026-09-11 al 2026-09-12", text)
        self.assertIn("1440", text)


if __name__ == "__main__":
    unittest.main()
