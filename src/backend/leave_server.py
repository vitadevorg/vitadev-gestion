"""Ausencias de personal. La identidad proviene de la sesión autenticada (auth.authorize)."""

from domain import REQUEST, PRIORITY, LEAVE, LABOR, AVAILABILITY, TASK
import base64, hashlib, io, json, os, re, sqlite3
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
import helpdesk_server as desk

team = desk.team
DATA = Path(os.environ.get("NEXO_LEAVE_DATA", str(team.ROOT / "work" / "leave-data")))
DATA.mkdir(parents=True, exist_ok=True)
(DATA / "files").mkdir(exist_ok=True)
TYPES = [
    {"name": n, "reasonRequired": n == "Otro"}
    for n in ["Vacaciones", "Enfermedad", "Permiso personal", "Estudio / Examen", "Otro"]
]


def connect():
    if team.pg.enabled():
        return team.pg.connect()
    c = sqlite3.connect(DATA / "leaves.sqlite3", timeout=15, factory=desk.crm.Connection)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    from identity import bind

    bind(c)
    return c


def decode(r):
    return {**json.loads(r["payload"]), "id": r["id"], "version": r["version"]}


def get(c, id):
    r = c.execute("SELECT * FROM absences WHERE id=?", (id,)).fetchone()
    return decode(r) if r else None


def init():
    if team.pg.enabled():
        return team.pg.ensure_ready()
    with connect() as c:
        c.executescript(
            "CREATE TABLE IF NOT EXISTS absences(id INTEGER PRIMARY KEY,employee INTEGER NOT NULL,start TEXT NOT NULL,end TEXT NOT NULL,status TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,payload TEXT NOT NULL); CREATE INDEX IF NOT EXISTS absence_period ON absences(employee,status,start,end); CREATE TABLE IF NOT EXISTS absence_events(id INTEGER PRIMARY KEY,absence_id INTEGER NOT NULL REFERENCES absences(id),action TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL,comment TEXT NOT NULL); CREATE TABLE IF NOT EXISTS absence_files(id TEXT PRIMARY KEY,name TEXT NOT NULL,mime TEXT NOT NULL,owner INTEGER);"
        )
        # owner es nulo para archivos de administración sin empleado vinculado; SQLite requiere reconstruir la tabla.
        if any(
            r["name"] == "owner" and r["notnull"]
            for r in c.execute("PRAGMA table_info(absence_files)")
        ):
            c.executescript(
                "BEGIN; CREATE TABLE absence_files_new(id TEXT PRIMARY KEY,name TEXT NOT NULL,mime TEXT NOT NULL,owner INTEGER); INSERT INTO absence_files_new SELECT id,name,mime,owner FROM absence_files; DROP TABLE absence_files; ALTER TABLE absence_files_new RENAME TO absence_files; COMMIT;"
            )
        from identity import prepare_audit, prepare_users

        prepare_audit(c, "absence_events", "leave", "absence_id")
        if not c.execute("SELECT 1 FROM absences LIMIT 1").fetchone():
            for id, employee, type, start, end, status in [
                (1, 3, "Vacaciones", "2026-09-10", "2026-09-18", LEAVE.APPROVED),
                (2, 2, "Permiso personal", "2026-09-21", "2026-09-23", LEAVE.PENDING),
            ]:
                d = dict(
                    employee=employee,
                    type=type,
                    start=start,
                    end=end,
                    days=(date.fromisoformat(end) - date.fromisoformat(start)).days + 1,
                    status=status,
                    reason="",
                    attachment="",
                    createdAt=team.now(),
                    createdBy="Importación de registros existentes",
                    resolvedAt=None,
                    resolvedBy=None,
                    resolutionComment="",
                )
                c.execute(
                    "INSERT INTO absences(id,employee,start,end,status,payload) VALUES(?,?,?,?,?,?)",
                    (id, employee, start, end, status, json.dumps(d, ensure_ascii=False)),
                )
                audit(
                    c,
                    id,
                    "Registro importado",
                    d["createdBy"],
                    "La fecha y autor de la resolución original no estaban registrados.",
                )


def audit(c, id, action, actor, comment=""):
    c.execute(
        "INSERT INTO absence_events(absence_id,action,actor,created_at,comment) VALUES(?,?,?,?,?)",
        (id, action, actor, team.now(), comment),
    )


def context(handler):
    if getattr(handler, "principal", None):
        u = handler.principal
        return {
            "role": "admin" if "leaves.manage" in u["permissions"] else "employee",
            "employee": u["employeeId"],
            "actor": (u.get("employee") or {}).get("name") or u["email"],
        }

    # Encabezados de vista solo para las suites (NEXO_TEST_MODE); nunca autentican en operación normal.
    import auth

    if not auth.test_mode():
        raise team.Validation({"_form": "Iniciá sesión para continuar."}, 401)
    role = handler.headers.get("X-Nexo-View")
    if role not in ["admin", "employee"]:
        raise team.Validation({"_form": "Esta vista no tiene acceso a Licencias."}, 403)
    try:
        employee_id = int(handler.headers.get("X-Nexo-Employee", "1"))
    except ValueError:
        raise team.Validation({"_form": "Empleado de desarrollo no válido."})
    if not desk.employee(employee_id):
        raise team.Validation({"_form": "Empleado no encontrado."})
    return {
        "role": role,
        "employee": employee_id,
        "actor": (
            "Administración local · sin autenticación"
            if role == "admin"
            else "Vista local sin autenticación"
        ),
    }


def permitted(ctx, r):
    return ctx["role"] == "admin" or r["employee"] == ctx["employee"]


def overlap(c, employee, start, end, exclude=0):
    return c.execute(
        "SELECT id FROM absences WHERE employee=? AND status IN ('Pendiente','Aprobada') AND start<=? AND end>=? AND id<>?",
        (employee, end, start, exclude),
    ).fetchone()


def validate(c, data, ctx):
    errors = {}
    employee = data.get("employee") if ctx["role"] == "admin" else ctx["employee"]
    person = desk.employee(employee)
    if not person or person["laborStatus"] != LABOR.ACTIVE:
        errors["employee"] = "Seleccioná un empleado activo."
    kind = data.get("type", "")
    start = data.get("start", "")
    end = data.get("end", "")
    reason = data.get("reason", "")
    if kind not in [t["name"] for t in TYPES]:
        errors["type"] = "Seleccioná un tipo de licencia."
    days = 0
    for key, value in [("start", start), ("end", end)]:
        try:
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError()
            date.fromisoformat(value)
        except ValueError:
            errors[key] = "Ingresá una fecha válida."
    if not ("start" in errors or "end" in errors):
        if end < start:
            errors["end"] = "La fecha final no puede ser anterior a la inicial."
        else:
            days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
            if person and overlap(c, employee, start, end):
                errors["end"] = (
                    "El período se superpone con una licencia pendiente o aprobada de este empleado."
                )
    if not isinstance(reason, str) or len(reason) > 3000:
        errors["reason"] = "Usá hasta 3.000 caracteres."
    elif kind == "Otro" and not reason.strip():
        errors["reason"] = "Indicá un motivo para este tipo de ausencia."
    attachment = data.get("attachment", "")
    if attachment:
        f = (
            c.execute("SELECT * FROM absence_files WHERE id=?", (attachment,)).fetchone()
            if isinstance(attachment, str)
            else None
        )
        if not f or (ctx["role"] != "admin" and f["owner"] != ctx["employee"]):
            errors["attachment"] = "Adjuntá un archivo válido."
    if errors:
        raise team.Validation(errors)
    return dict(
        employee=employee,
        type=kind,
        start=start,
        end=end,
        days=days,
        reason=reason.strip(),
        attachment=attachment,
        status=LEAVE.PENDING,
        createdAt=team.now(),
        createdBy=ctx["actor"],
        resolvedAt=None,
        resolvedBy=None,
        resolutionComment="",
    )


class Handler(desk.Handler):
    def do_GET(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/absences"):
            return super().do_GET()
        try:
            self.guard()
            with connect() as c:
                if path == "/api/absences/availability":
                    return self.send_json(
                        200,
                        {
                            "today": date.today().isoformat(),
                            "periods": [
                                dict(r)
                                for r in c.execute(
                                    "SELECT id,employee,start,end,status FROM absences WHERE status='Aprobada'"
                                )
                            ],
                        },
                    )
                ctx = context(self)
                if path == "/api/absences":
                    items = [
                        decode(r)
                        for r in c.execute("SELECT * FROM absences ORDER BY start DESC,id DESC")
                    ]
                    items = [r for r in items if permitted(ctx, r)]
                    ids = {r["id"] for r in items}
                    for r in items:
                        if r["attachment"]:
                            f = c.execute(
                                "SELECT name FROM absence_files WHERE id=?", (r["attachment"],)
                            ).fetchone()
                            r["attachmentName"] = f["name"] if f else "Adjunto"
                    events = [
                        dict(r)
                        for r in c.execute("SELECT * FROM absence_events ORDER BY id DESC")
                        if r["absence_id"] in ids
                    ]
                    return self.send_json(
                        200,
                        {
                            "items": items,
                            "events": events,
                            "types": TYPES,
                            "today": date.today().isoformat(),
                            "context": {
                                **ctx,
                                "authenticated": bool(getattr(self, "principal", None)),
                            },
                        },
                    )
                m = re.fullmatch(r"/api/absences/(\d+)/attachment", path)
                if m:
                    r = get(c, int(m[1]))
                    if not r or not permitted(ctx, r):
                        raise team.Validation({"_form": "No tenés acceso a este adjunto."}, 403)
                    f = c.execute(
                        "SELECT * FROM absence_files WHERE id=?", (r["attachment"],)
                    ).fetchone()
                    p = DATA / "files" / r["attachment"]
                    if not f or not p.is_file():
                        return self.send_error(404)
                    raw = p.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", f["mime"])
                    self.send_header("Content-Security-Policy", "sandbox")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
            self.send_error(404)
        except team.Validation as e:
            self.send_json(e.status, {"errors": e.fields})

    def mutate(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/absences"):
            return super().mutate()
        try:
            self.guard(True)
            ctx = context(self)
            n = team.content_length(self.headers)
            if n < 1 or n > 7500000:
                raise team.Validation({"attachment": "El adjunto debe pesar hasta 5 MB."}, 413)
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                raise team.Validation({"_form": "Formato no válido."}, 415)
            d = json.loads(self.rfile.read(n))
            if not isinstance(d, dict):
                raise team.Validation({"_form": "Datos no válidos."})
            with connect() as c:
                if path == "/api/absences/files" and self.command == "POST":
                    try:
                        raw = base64.b64decode(d.get("base64", ""), validate=True)
                        name = Path(str(d.get("name", "archivo")).replace("\\", "/")).name[:160]
                        if len(raw) > 5 * 1024 * 1024:
                            raise ValueError()
                        if name.lower().endswith(".pdf"):
                            from pypdf import PdfReader

                            if not raw.startswith(b"%PDF-"):
                                raise ValueError()
                            pdf = PdfReader(io.BytesIO(raw), strict=True)
                            if pdf.is_encrypted or not len(pdf.pages):
                                raise ValueError()
                            mime = "application/pdf"
                        else:
                            raw, fmt = team.clean_image(raw, 5 * 1024 * 1024)
                            mime = team.IMAGE_FORMATS[fmt][0]
                    except Exception:
                        raise team.Validation(
                            {"attachment": "Usá PDF, PNG, JPEG o WebP válido, hasta 5 MB."}
                        )
                    id = hashlib.sha256(raw + str(ctx["employee"]).encode()).hexdigest()
                    (DATA / "files" / id).write_bytes(raw)
                    c.execute(
                        "INSERT OR IGNORE INTO absence_files VALUES(?,?,?,?)",
                        (id, name, mime, ctx["employee"]),
                    )
                    return self.send_json(201, {"id": id, "name": name})
                if path == "/api/absences" and self.command == "POST":
                    c.execute("BEGIN IMMEDIATE")
                    r = validate(c, d, ctx)
                    id = c.execute(
                        "INSERT INTO absences(employee,start,end,status,payload) VALUES(?,?,?,?,?)",
                        (
                            r["employee"],
                            r["start"],
                            r["end"],
                            r["status"],
                            json.dumps(r, ensure_ascii=False),
                        ),
                    ).lastrowid
                    audit(c, id, "Solicitud creada", ctx["actor"])
                    return self.send_json(201, {"item": get(c, id)})
                m = re.fullmatch(r"/api/absences/(\d+)/(approve|reject|cancel)", path)
                if not m or self.command != "POST":
                    return self.send_error(404)
                c.execute("BEGIN IMMEDIATE")
                id = int(m[1])
                r = get(c, id)
                if not r or not permitted(ctx, r):
                    raise team.Validation({"_form": "No tenés acceso a esta solicitud."}, 403)
                action = m[2]
                if action in ["approve", "reject"] and ctx["role"] != "admin":
                    raise team.Validation(
                        {"_form": "Solo Administración puede resolver solicitudes."}, 403
                    )
                if d.get("version") != r["version"]:
                    raise team.Validation(
                        {
                            "_form": "La solicitud fue actualizada en otra sesión. Revisá los datos actuales."
                        },
                        409,
                    )
                if action in ["approve", "reject"] and r["status"] != LEAVE.PENDING:
                    raise team.Validation({"_form": "Esta solicitud ya fue resuelta."}, 409)
                if action == "cancel" and (
                    r["status"] not in [LEAVE.PENDING, LEAVE.APPROVED]
                    or (ctx["role"] == "employee" and r["status"] != LEAVE.PENDING)
                ):
                    raise team.Validation(
                        {"_form": "No se puede cancelar esta solicitud desde tu vista."}, 403
                    )
                comment = d.get("comment", "")
                if not isinstance(comment, str) or len(comment) > 3000:
                    raise team.Validation({"comment": "Usá hasta 3.000 caracteres."})
                if action == "reject" and not comment.strip():
                    raise team.Validation({"comment": "Indicá el motivo del rechazo."})
                if d.get("confirm") is not True:
                    raise team.Validation({"confirm": "Confirmá la decisión antes de continuar."})
                if action == "approve" and overlap(c, r["employee"], r["start"], r["end"], id):
                    raise team.Validation(
                        {"_form": "Existe otra licencia pendiente o aprobada superpuesta."}, 409
                    )
                r["status"] = {
                    "approve": LEAVE.APPROVED,
                    "reject": LEAVE.REJECTED,
                    "cancel": LEAVE.CANCELLED,
                }[action]
                if action == "cancel":
                    r.update(
                        cancelledAt=team.now(),
                        cancelledBy=ctx["actor"],
                        cancellationComment=comment.strip(),
                    )
                else:
                    r.update(
                        resolvedAt=team.now(),
                        resolvedBy=ctx["actor"],
                        resolutionComment=comment.strip(),
                    )
                r["updatedAt"] = team.now()
                c.execute(
                    "UPDATE absences SET status=?,payload=?,version=version+1 WHERE id=?",
                    (
                        r["status"],
                        json.dumps(
                            {k: v for k, v in r.items() if k not in ["id", "version"]},
                            ensure_ascii=False,
                        ),
                        id,
                    ),
                )
                audit(c, id, "Solicitud " + r["status"].lower(), ctx["actor"], comment.strip())
                self.send_json(200, {"item": get(c, id)})
        except team.Validation as e:
            self.send_json(e.status, {"errors": e.fields})
        except (ValueError, TypeError):
            self.send_json(400, {"errors": {"_form": "Los datos no son válidos."}})
        except Exception:
            team.log.exception("Error interno en %s %s", self.command, urlparse(self.path).path)
            self.send_json(
                500,
                {
                    "errors": {
                        "_form": "No se pudo guardar. Tus datos se conservan para reintentar."
                    }
                },
            )
