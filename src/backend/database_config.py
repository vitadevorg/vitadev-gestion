"""Configuración privada de PostgreSQL; nunca registra valores de conexión."""

import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
KEYS = {"SUPABASE_DB_URL", "SUPABASE_SSLROOTCERT", "VITADEV_DATABASE", "VITADEV_DB_SCHEMA"}


def load_environment(path=None, environ=None):
    """Carga solo las claves admitidas, sin sobrescribir el entorno del proceso."""
    target = os.environ if environ is None else environ
    path = ROOT / ".env" if path is None else Path(path)
    if not path.is_file():
        return
    pending = {}
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if key not in KEYS:
            continue
        if not separator or key in pending:
            raise ValueError(f"Configuración .env inválida en línea {number}.")
        value = value.strip()
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f"Comillas sin cerrar en .env, línea {number}.")
            value = value[1:-1]
        pending[key] = value
    for key, value in pending.items():
        target.setdefault(key, value)


def connection_options(environ=None):
    source = os.environ if environ is None else environ
    url = source.get("SUPABASE_DB_URL", "")
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme in ("postgresql", "postgres")
            and parsed.hostname
            and parsed.username
            and parsed.password
            and parsed.port
            and parsed.path not in ("", "/")
            and "[YOUR-PASSWORD]" not in url
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            "SUPABASE_DB_URL debe contener una conexión PostgreSQL completa."
        ) from None
    cert = source.get("SUPABASE_SSLROOTCERT")
    options = {
        "connect_timeout": 10,
        "sslmode": "verify-full",
        "prepare_threshold": None,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    }
    if cert:
        if not Path(cert).is_file():
            raise ValueError("No existe el certificado indicado en SUPABASE_SSLROOTCERT.")
        options["sslrootcert"] = cert
    return url, options
