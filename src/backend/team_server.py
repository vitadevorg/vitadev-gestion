"""Persistencia de Equipo y servidor base.
Iniciar Nexo mediante auth_server.py, que integra autenticación y todos los módulos.
"""

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent)
)  # Permite cargarlo por ruta (tests/test_team_api.py).
from identity import actor
from domain import REQUEST, PRIORITY, LEAVE, LABOR, AVAILABILITY, TASK
import base64, hashlib, io, json, os, re, sqlite3, sys
from database_config import load_environment

load_environment()
import postgres_backend as pg
from datetime import date, datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("NEXO_TEAM_DATA", str(ROOT / "work" / "team-data")))
DATA.mkdir(parents=True, exist_ok=True)
(DATA / "photos").mkdir(exist_ok=True)
DB = DATA / "team.sqlite3"
CATALOG = {
    "Administración": [
        "Responsable de operaciones",
        "Analista administrativo",
        "Responsable de Recursos Humanos",
    ],
    "Desarrollo": [
        "Desarrollador backend",
        "Desarrollador frontend",
        "Responsable de Backend",
        "Responsable de Frontend",
        "Líder de desarrollo",
    ],
    "Soporte": ["Especialista de soporte", "Responsable de soporte", "Analista de implementación"],
    "Comercial": ["Ejecutiva de cuentas", "Ejecutivo de cuentas", "Responsable comercial"],
    "Calidad": ["Analista de calidad", "Responsable de QA"],
}
ACCESS_ROLES = ["Empleado", "Supervisor", "Administrador"]
ASSET_PHOTOS = ["assets/avatars/" + p.name for p in (ROOT / "src/assets/avatars").glob("*.png")]
CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; frame-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
IMAGE_FORMATS = {
    "PNG": ("image/png", ".png"),
    "JPEG": ("image/jpeg", ".jpg"),
    "WEBP": ("image/webp", ".webp"),
}


def clean_image(raw, max_bytes):
    """Valida y re-codifica la imagen: descarta EXIF (GPS, dispositivo) y contenido ajeno a los píxeles."""
    from PIL import Image, ImageOps

    if not raw or len(raw) > max_bytes:
        raise ValueError()
    with Image.open(io.BytesIO(raw)) as probe:
        fmt = probe.format
        if fmt not in IMAGE_FORMATS or probe.width * probe.height > 16000000:
            raise ValueError()
        probe.verify()
    with Image.open(io.BytesIO(raw)) as im:
        im = ImageOps.exif_transpose(im)
        if fmt == "JPEG" and im.mode not in ("RGB", "L", "CMYK"):
            im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, format=fmt, **({"quality": 90} if fmt in ("JPEG", "WEBP") else {}))
    return out.getvalue(), fmt


import logging

log = logging.getLogger(
    "vitadev"
)  # Errores internos: siempre registrados, nunca enviados al cliente.


def now():
    return datetime.now(timezone.utc).isoformat()


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect():
    if pg.enabled():
        return pg.connect()
    c = sqlite3.connect(DB, timeout=15, factory=Connection)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    from identity import bind

    bind(c)
    return c


def init():
    if pg.enabled():
        return pg.ensure_ready()
    with connect() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS employees (id INTEGER PRIMARY KEY, email TEXT NOT NULL COLLATE NOCASE UNIQUE, legajo TEXT NOT NULL COLLATE NOCASE UNIQUE, version INTEGER NOT NULL DEFAULT 1, payload TEXT NOT NULL)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS employee_audit (id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), action TEXT NOT NULL, fields TEXT NOT NULL, created_at TEXT NOT NULL, actor TEXT NOT NULL)"
        )
        from identity import prepare_audit, prepare_users

        prepare_audit(c, "employee_audit", "employee", "employee_id")
        prepare_users(c)
        if c.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
            seed = json.loads(
                (Path(__file__).parent / "team-seed.json").read_text(encoding="utf-8")
            )
            for e in seed:
                c.execute(
                    "INSERT INTO employees(id,email,legajo,payload) VALUES(?,?,?,?)",
                    (e["id"], e["email"], e["legajo"], json.dumps(e, ensure_ascii=False)),
                )
                c.execute(
                    "INSERT INTO employee_audit(employee_id,action,fields,created_at,actor) VALUES(?,?,?,?,?)",
                    (
                        e["id"],
                        "Importación inicial",
                        "[]",
                        now(),
                        "Inicialización de registros de ejemplo",
                    ),
                )
        for row in c.execute("SELECT id,payload FROM employees").fetchall():
            payload = json.loads(row["payload"])
            if "load" in payload or "status" in payload:
                payload.pop("load", None)
                payload.pop("status", None)
                c.execute(
                    "UPDATE employees SET payload=?,version=version+1 WHERE id=?",
                    (json.dumps(payload, ensure_ascii=False), row["id"]),
                )
                c.execute(
                    "INSERT INTO employee_audit(employee_id,action,fields,created_at,actor) VALUES(?,?,?,?,?)",
                    (
                        row["id"],
                        "Retiro de campos obsoletos",
                        '["load","status"]',
                        now(),
                        "Migración técnica · sin usuario autenticado",
                    ),
                )


def unpack(row):
    obj = json.loads(row["payload"])
    obj.pop("load", None)
    obj.pop("status", None)
    obj.update(id=row["id"], version=row["version"])
    return obj


class Validation(Exception):
    def __init__(self, fields, status=422):
        self.fields = fields
        self.status = status


def content_length(headers):
    # Un valor negativo haría que rfile.read() bloquee el hilo hasta cerrar la conexión.
    value = headers.get("Content-Length", "0")
    if not re.fullmatch(r"\d{1,12}", value.strip()):
        raise Validation({"_form": "Solicitud inválida."}, 400)
    return int(value)


def validate(data, c, employee_id=None):
    fields = {}
    out = {}
    required = [
        "firstName",
        "lastName",
        "legajo",
        "area",
        "role",
        "hireDate",
        "modality",
        "laborStatus",
        "email",
    ]
    for key in required + ["dni", "birthDate", "phone", "photo", "availability"]:
        value = data.get(key, "")
        if not isinstance(value, str):
            fields[key] = "Ingresá un valor válido."
            value = ""
        out[key] = value.strip()
        if len(out[key]) > 180:
            fields[key] = "Usá hasta 180 caracteres."
    for key in required:
        if not out[key]:
            fields[key] = "Este campo es obligatorio."
    if out["area"] not in CATALOG:
        fields["area"] = "Seleccioná un área del catálogo."
    if out["role"] not in CATALOG.get(out["area"], []):
        fields["role"] = "Seleccioná un puesto del área elegida."
    if out["modality"] not in ["Remoto", "Híbrido", "Presencial"]:
        fields["modality"] = "Seleccioná una modalidad."
    if out["laborStatus"] not in [LABOR.ACTIVE, LABOR.INACTIVE]:
        fields["laborStatus"] = "Seleccioná un estado laboral."
    if out["availability"] not in [
        AVAILABILITY.AVAILABLE,
        AVAILABILITY.BUSY,
        AVAILABILITY.ABSENT,
        AVAILABILITY.ON_LEAVE,
    ]:
        fields["availability"] = "Seleccioná la disponibilidad."
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", out["email"]):
        fields["email"] = "Ingresá un correo válido."
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,30}", out["legajo"]):
        fields["legajo"] = "Usá hasta 30 letras, números, guiones o guiones bajos."
    if out["dni"] and not re.fullmatch(r"\d{7,9}", out["dni"]):
        fields["dni"] = "Ingresá entre 7 y 9 dígitos, sin puntos."
    for key in ["birthDate", "hireDate"]:
        if out[key]:
            try:
                parsed = date.fromisoformat(out[key])
                if key == "birthDate" and parsed > date.today():
                    fields[key] = "La fecha de nacimiento no puede ser futura."
            except ValueError:
                fields[key] = "Ingresá una fecha válida."
    if out["birthDate"] and out["hireDate"] and out["birthDate"] >= out["hireDate"]:
        fields["hireDate"] = "El ingreso debe ser posterior al nacimiento."
    for key in ["email", "legajo"]:
        found = c.execute(
            f"SELECT id FROM employees WHERE {key}=? COLLATE NOCASE", (out[key],)
        ).fetchone()
        if found and found["id"] != employee_id:
            fields[key] = "Ya existe un empleado con este " + (
                "correo." if key == "email" else "legajo."
            )
    manager = data.get("managerId")
    if manager in ["", None]:
        manager = None
    if manager is not None:
        if not isinstance(manager, int) or isinstance(manager, bool):
            fields["managerId"] = "Seleccioná un responsable válido."
        else:
            seen = {employee_id} if employee_id else set()
            current = manager
            while current:
                if current in seen:
                    fields["managerId"] = "La relación de responsables no puede formar un ciclo."
                    break
                seen.add(current)
                row = c.execute("SELECT * FROM employees WHERE id=?", (current,)).fetchone()
                if not row:
                    fields["managerId"] = "El responsable no existe."
                    break
                parent = unpack(row)
                if current == manager and parent["laborStatus"] != LABOR.ACTIVE:
                    fields["managerId"] = "Seleccioná un responsable activo."
                current = parent.get("managerId")
    out["managerId"] = manager
    skills = data.get("skills", [])
    if (
        not isinstance(skills, list)
        or len(skills) > 25
        or any(not isinstance(s, str) or not s.strip() or len(s) > 40 for s in skills)
    ):
        fields["skills"] = "Usá hasta 25 habilidades de 40 caracteres."
        skills = []
    out["skills"] = list({s.strip().casefold(): s.strip() for s in skills}.values())
    access = data.get("access", {})
    if not isinstance(access, dict):
        access = {}
    enabled = access.get("enabled", False)
    if not isinstance(enabled, bool):
        fields["access"] = "Indicá si debe tener acceso."
        enabled = False
    role = access.get("role", "Empleado")
    if role not in ACCESS_ROLES:
        fields["accessRole"] = "Seleccioná un rol del sistema."
    if out["laborStatus"] == LABOR.INACTIVE:
        enabled = False
    out["access"] = {"enabled": enabled, "role": role if role in ACCESS_ROLES else "Empleado"}
    photo = out["photo"]
    if (
        photo
        and photo not in ASSET_PHOTOS
        and not re.fullmatch(r"/api/team/photos/[a-f0-9]{64}\.(png|jpg|webp)", photo)
    ):
        fields["photo"] = "Seleccioná una fotografía válida."
    if fields:
        raise Validation(fields)
    out.update(
        name=out["firstName"] + " " + out["lastName"], email=out["email"].lower(), updatedAt=now()
    )
    return out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "dist"), **kwargs)

    def log_message(self, fmt, *args):
        pass

    def list_directory(self, path):
        self.send_error(404)
        return None

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if os.environ.get("NEXO_COOKIE_SECURE") == "1":
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        super().end_headers()

    def send_json(self, status, obj):
        import auth

        obj = auth.filter_response(self, obj)
        if pg.enabled() and 200 <= status < 300:
            pg.before_response()
        payload = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        [self.send_header(k, v) for k, v in getattr(self, "extra_headers", [])]
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def guard(self, write=False, authentication=True):
        host = self.headers.get("Host", "")
        if host not in [
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
        ]:
            raise Validation({"_form": "Origen no permitido."}, 403)
        if write:
            origin = self.headers.get("Origin")
            if origin and origin not in [
                "http://" + host,
                os.environ.get("NEXO_PUBLIC_ORIGIN", "http://" + host),
            ]:
                raise Validation({"_form": "Origen no permitido."}, 403)
            if self.headers.get("X-Nexo-Client") != "team":
                raise Validation({"_form": "Solicitud no autorizada."}, 403)
        if authentication:
            import auth

            auth.authorize(self, write)

    def body(self):
        n = content_length(self.headers)
        if n > 4500000:
            raise Validation({"photo": "La imagen debe pesar hasta 3 MB."}, 413)
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            raise Validation({"_form": "Formato de solicitud inválido."}, 415)
        try:
            d = json.loads(self.rfile.read(n))
        except (ValueError, UnicodeError):
            raise Validation({"_form": "Datos inválidos."}, 400)
        if not isinstance(d, dict):
            raise Validation({"_form": "Datos inválidos."}, 400)
        return d

    def do_GET(self):
        try:
            self.guard()
            path = urlparse(self.path).path
            if path == "/api/team":
                with connect() as c:
                    rows = [unpack(r) for r in c.execute("SELECT * FROM employees ORDER BY id")]
                return self.send_json(
                    200,
                    {
                        "employees": rows,
                        "catalog": CATALOG,
                        "accessRoles": ACCESS_ROLES,
                        "today": date.today().isoformat(),
                        "accessEnforcement": False,
                    },
                )
            if path.startswith("/api/team/photos/"):
                name = path.rsplit("/", 1)[-1]
                if not re.fullmatch(r"[a-f0-9]{64}\.(png|jpg|webp)", name):
                    return self.send_error(404)
                p = DATA / "photos" / name
                if not p.is_file():
                    return self.send_error(404)
                raw = p.read_bytes()
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}[p.suffix[1:]],
                )
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if re.fullmatch(r"/api/team/\d+/audit", path):
                with connect() as c:
                    rows = [
                        dict(r)
                        for r in c.execute(
                            "SELECT * FROM employee_audit WHERE employee_id=? ORDER BY id DESC",
                            (int(path.split("/")[3]),),
                        )
                    ]
                return self.send_json(200, {"events": rows})
            if path.startswith("/api/"):
                return self.send_json(404, {"error": "Ruta no encontrada."})
            if Path(path).suffix in [".py", ".sqlite3", ".json"] or "/backend/" in path:
                return self.send_error(404)
            return super().do_GET()
        except Validation as e:
            self.send_json(e.status, {"errors": e.fields})

    def do_POST(self):
        self.mutate()

    def do_PUT(self):
        self.mutate()

    def mutate(self):
        try:
            self.guard(True)
            path = urlparse(self.path).path
            data = self.body()
            if path == "/api/team/photos" and self.command == "POST":
                try:
                    raw, fmt = clean_image(
                        base64.b64decode(data.get("base64", ""), validate=True), 3 * 1024 * 1024
                    )
                except Exception:
                    raise Validation(
                        {"photo": "Elegí PNG, JPEG o WebP válido, de hasta 3 MB y 16 megapíxeles."}
                    )
                name = hashlib.sha256(raw).hexdigest() + IMAGE_FORMATS[fmt][1]
                (DATA / "photos" / name).write_bytes(raw)
                return self.send_json(201, {"photo": "/api/team/photos/" + name})
            match = re.fullmatch(r"/api/team/(\d+)(/(deactivate|access))?", path)
            create = path == "/api/team" and self.command == "POST"
            if not create and not match:
                return self.send_json(404, {"error": "Ruta no encontrada."})
            with connect() as c:
                c.execute("BEGIN IMMEDIATE")
                old = None
                employee_id = None
                action = "Alta"
                if match:
                    employee_id = int(match[1])
                    row = c.execute("SELECT * FROM employees WHERE id=?", (employee_id,)).fetchone()
                    if not row:
                        return self.send_json(
                            404, {"errors": {"_form": "El empleado ya no está disponible."}}
                        )
                    old = unpack(row)
                    # Dentro de la transacción: dos desactivaciones simultáneas no pueden dejar el sistema sin administrador.
                    if match[3] == "deactivate" or data.get("laborStatus") == LABOR.INACTIVE:
                        target = c.execute(
                            "SELECT id FROM users WHERE employeeId=? AND role='ADMIN' AND status='ACTIVE'",
                            (employee_id,),
                        ).fetchone()
                        if target and not pg.other_active_admin(c, target["id"]):
                            raise Validation(
                                {
                                    "_form": "No se puede desactivar al empleado del último administrador activo."
                                },
                                422,
                            )
                    if data.get("version") != old["version"]:
                        raise Validation(
                            {
                                "_form": "Otro cambio actualizó este empleado. Cerrá y volvé a abrir su ficha antes de guardar."
                            },
                            409,
                        )
                    if match[3] == "deactivate":
                        if not data.get("reason", "").strip():
                            raise Validation({"reason": "Indicá el motivo de desactivación."})
                        data = {
                            **old,
                            "laborStatus": LABOR.INACTIVE,
                            "access": {**old["access"], "enabled": False},
                            "deactivationReason": data["reason"].strip()[:500],
                        }
                        action = "Desactivación"
                    elif match[3] == "access":
                        data = {**old, "access": data.get("access", {})}
                        action = "Configuración de acceso"
                    else:
                        action = "Edición"
                employee = validate(data, c, employee_id)
                if old:
                    employee["createdAt"] = old.get("createdAt")
                    employee["training"] = old.get("training", [])
                    employee["certifications"] = old.get("certifications", [])
                    if action == "Desactivación":
                        employee["deactivationReason"] = data["deactivationReason"]
                    elif old.get("deactivationReason"):
                        employee["deactivationReason"] = old["deactivationReason"]
                    c.execute(
                        "UPDATE employees SET email=?,legajo=?,payload=?,version=version+1 WHERE id=?",
                        (
                            employee["email"],
                            employee["legajo"],
                            json.dumps(employee, ensure_ascii=False),
                            employee_id,
                        ),
                    )
                else:
                    employee.update(createdAt=now(), training=[], certifications=[])
                    employee_id = c.execute(
                        "INSERT INTO employees(email,legajo,payload) VALUES(?,?,?)",
                        (
                            employee["email"],
                            employee["legajo"],
                            json.dumps(employee, ensure_ascii=False),
                        ),
                    ).lastrowid
                changed = [
                    k
                    for k in employee
                    if (old or {}).get(k) != employee[k] and k not in ["updatedAt", "createdAt"]
                ]
                c.execute(
                    "INSERT INTO employee_audit(employee_id,action,fields,created_at,actor) VALUES(?,?,?,?,?)",
                    (employee_id, action, json.dumps(changed), now(), actor()),
                )
                result = unpack(
                    c.execute("SELECT * FROM employees WHERE id=?", (employee_id,)).fetchone()
                )
            self.send_json(201 if create else 200, {"employee": result})
        except Validation as e:
            self.send_json(e.status, {"errors": e.fields})
        except sqlite3.IntegrityError:
            self.send_json(
                409, {"errors": {"_form": "El legajo o correo ya existe. Revisá los datos."}}
            )
        except Exception:
            log.exception("Error interno en %s %s", self.command, urlparse(self.path).path)
            self.send_json(
                500,
                {
                    "errors": {
                        "_form": "No se pudo guardar. Conservamos tus datos para que vuelvas a intentarlo."
                    }
                },
            )
