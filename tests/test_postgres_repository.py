"""Contrato de reconstrucción de DTO; validación PostgreSQL real en el lanzador privado."""

import _isolation  # noqa: F401  Debe ir antes que el backend.
import unittest, json, copy
from datetime import date
import test_migration as fixture
import report_server as reports
from postgres_repository import PostgresRepository


class MemoryRows(PostgresRepository):
    def __init__(self, tables):
        self.tables = tables

    def rows(self, table):
        return copy.deepcopy(self.tables[table])


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tables = fixture.transform.prepare(fixture.work)
        self.repo = MemoryRows(self.tables)

    def test_report_equivalence(self):
        original = reports.analyze(reports.sources(), date(2026, 1, 1), date(2026, 12, 31))
        migrated = reports.analyze(reports.sources(self.repo), date(2026, 1, 1), date(2026, 12, 31))
        original.pop("generatedAt")
        migrated.pop("generatedAt")
        self.assertEqual(original, migrated)

    def test_columns_override_stale_json(self):
        row = self.tables["employees"][0]
        row["first_name"] = "Nombre actualizado"
        row["extra_data"]["firstName"] = "Anterior"
        self.tables["employee_skills"] = [
            {"employee_id": row["id"], "position": 0, "skill": "PostgreSQL"}
        ]
        employee = self.repo.employees()[0]
        self.assertEqual(employee["firstName"], "Nombre actualizado")
        self.assertEqual(employee["skills"], ["PostgreSQL"])

    def test_access_policy(self):
        expected = json.loads((fixture.ROOT / "src/access-policy.json").read_text(encoding="utf-8"))
        actual = self.repo.access_policy()
        self.assertEqual(actual["profileLabels"], expected["profileLabels"])
        self.assertEqual(
            {k: set(v) for k, v in actual["profiles"].items()},
            {k: set(v) for k, v in expected["profiles"].items()},
        )

    def test_no_credentials_in_operational_report_sources(self):
        data = self.repo.report_sources()
        self.assertNotIn("users", data)
        self.assertNotIn("sessions", data)


if __name__ == "__main__":
    unittest.main()
