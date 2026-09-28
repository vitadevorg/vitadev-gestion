"""Suites locales aisladas; siempre selecciona SQLite en carpetas temporales."""

import os, sys, subprocess, json, hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHS = [
    "test_team_api.py",
    "test_crm_api.py",
    "test_helpdesk_api.py",
    "test_leave_api.py",
    "test_stability.py",
    "test_auth.py",
    "test_reports.py",
    "test_database_config.py",
    "test_migration.py",
    "test_postgres_repository.py",
]


def run(name):
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests" / name)],
        cwd=ROOT,
        env={**os.environ, "VITADEV_DATABASE": "sqlite"},
        capture_output=True,
        text=True,
        timeout=900,
    )
    output = result.stdout + result.stderr
    ok = result.returncode == 0 and "\nOK" in output and "FAILED (" not in output
    directory = ROOT / "work/sqlite-test-results"
    directory.mkdir(exist_ok=True)
    (directory / (Path(name).stem + ".log")).write_text(output, encoding="utf-8")
    print(name, "PASS" if ok else "FAIL", flush=True)
    return ok


if __name__ == "__main__":
    paths = [
        ROOT / "work" / p
        for p in ["team-data/team.sqlite3", "crm-data/crm.sqlite3", "leave-data/leaves.sqlite3"]
    ]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()}
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run, PATHS))
    unchanged = all(
        hashlib.sha256(p.read_bytes()).hexdigest() == value for p, value in before.items()
    )
    print("SQLite originales sin cambios:", unchanged, flush=True)
    sys.exit(not (all(results) and unchanged))
