"""Ejecuta suites existentes en esquemas desechables de Supabase.

Nunca usa ni elimina el esquema vitadev. Semillas creadas en SQLite temporal,
sin leer/escribir las bases originales. Secretos solo en entorno del proceso.
"""

import os, sys, subprocess, json, tempfile, uuid, hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/backend"))
sys.path.insert(0, str(ROOT / "src/backend/migrations"))
from database_config import load_environment

load_environment()
# Instalaciones locales pueden proporcionar el driver mediante PYTHONPATH.
from migrate_supabase import connect, load
from psycopg import sql


def fixtures():
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "fixture.json"
        code = "import sys,json;sys.path.insert(0,'tests');import test_migration as f;from pathlib import Path;Path(sys.argv[1]).write_text(json.dumps(f.transform.prepare(f.work)),encoding='utf-8')"
        env = {**os.environ, "VITADEV_DATABASE": "sqlite"}
        subprocess.run(
            [sys.executable, "-c", code, str(target)],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
        )
        return json.loads(target.read_text(encoding="utf-8"))


def run(path, tables):
    schema = "vitadev_test_" + uuid.uuid4().hex
    report = ROOT / "work" / "postgres-test-results"
    report.mkdir(exist_ok=True)
    manifest = report / (schema + ".json")
    manifest.write_text(
        json.dumps({"schema": schema, "test": path, "cleaned": False}), encoding="utf-8"
    )
    try:
        with connect() as c:
            load(c, tables, schema)
        env = {**os.environ, "VITADEV_DATABASE": "postgres", "VITADEV_DB_SCHEMA": schema}
        # Unittest usa exit=False en algunas suites: comprobar también su resumen.
        log = report / (Path(path).stem + ".log")
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run(
                [sys.executable, path],
                cwd=ROOT,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=1500,
            )
        output = log.read_text(encoding="utf-8")
        ok = result.returncode == 0 and "\nOK" in output and "FAILED (" not in output
        # No registrar errores de driver que puedan contener parámetros privados.
        print(Path(path).name, "PASS" if ok else "FAIL", flush=True)
        return ok
    except Exception as error:
        print(Path(path).name, "FAIL", type(error).__name__, flush=True)
        return False
    finally:
        with connect() as c:
            c.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        manifest.write_text(
            json.dumps({"schema": schema, "test": path, "cleaned": True}), encoding="utf-8"
        )


if __name__ == "__main__":
    paths = sys.argv[1:] or [
        "tests/test_team_api.py",
        "tests/test_crm_api.py",
        "tests/test_helpdesk_api.py",
        "tests/test_leave_api.py",
        "tests/test_stability.py",
        "tests/test_auth.py",
        "tests/test_reports.py",
        "tests/test_postgres_flow.py",
    ]
    originals = [
        ROOT / "work" / p
        for p in ["team-data/team.sqlite3", "crm-data/crm.sqlite3", "leave-data/leaves.sqlite3"]
    ]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals if p.exists()}
    tables = fixtures()
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda path: run(path, tables), paths))
    unchanged = all(
        hashlib.sha256(p.read_bytes()).hexdigest() == value for p, value in before.items()
    )
    print("SQLite originales sin cambios:", unchanged, flush=True)
    sys.exit(0 if all(results) and unchanged else 1)
