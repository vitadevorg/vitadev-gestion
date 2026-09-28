"""Mesa de Ayuda: solicitudes, comentarios, adjuntos y trabajo técnico relacionado."""

from identity import actor
from domain import REQUEST, PRIORITY, LEAVE, LABOR, AVAILABILITY, TASK
import base64, hashlib, io, json, re, zipfile
from datetime import date
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote
import crm_server as crm

team = crm.team
STATES = [
    REQUEST.NEW,
    REQUEST.IN_PROGRESS,
    REQUEST.WAITING_CLIENT,
    REQUEST.RESOLVED,
    REQUEST.CLOSED,
]
PRIORITIES = [PRIORITY.LOW, PRIORITY.MEDIUM, PRIORITY.HIGH, PRIORITY.URGENT]
TYPES = ["Incidente", "Consulta", "Requerimiento", "Capacitación"]
SEED_TEXT = {
    1042: (
        "Revisar la confirmación de turnos",
        "El equipo de recepción solicita revisar el flujo de confirmación de turnos.",
    ),
    1041: (
        "Preparar capacitación del panel administrativo",
        "Preparar una capacitación inicial para el personal administrativo.",
    ),
    1040: (
        "Verificar configuración de profesionales",
        "Se verificó la configuración de profesionales en el entorno de demostración.",
    ),
}
TRANSITIONS = {
    REQUEST.NEW: [REQUEST.IN_PROGRESS, REQUEST.RESOLVED],
    REQUEST.IN_PROGRESS: [REQUEST.WAITING_CLIENT, REQUEST.RESOLVED],
    REQUEST.WAITING_CLIENT: [REQUEST.IN_PROGRESS, REQUEST.RESOLVED],
    REQUEST.RESOLVED: [REQUEST.IN_PROGRESS, REQUEST.CLOSED],
    REQUEST.CLOSED: [REQUEST.IN_PROGRESS],
}


def get(c, id):
    r = c.execute("SELECT * FROM desk_requests WHERE id=?", (id,)).fetchone()
    return {**json.loads(r["payload"]), "id": r["id"], "version": r["version"]} if r else None


def event(c, id, action, reference=""):
    c.execute(
        "INSERT INTO desk_events(request_id,action,reference,actor,created_at) VALUES(?,?,?,?,?)",
        (id, action, reference, actor(), team.now()),
    )


def init():
    if team.pg.enabled():
        return team.pg.ensure_ready()
    crm.init()
    with crm.connect() as c:
        c.executescript(
            "CREATE TABLE IF NOT EXISTS desk_requests(id INTEGER PRIMARY KEY,client_id INTEGER NOT NULL REFERENCES records(id),subscription_id INTEGER NOT NULL REFERENCES records(id),contact_id INTEGER REFERENCES records(id),version INTEGER NOT NULL DEFAULT 1,payload TEXT NOT NULL); CREATE TABLE IF NOT EXISTS desk_events(id INTEGER PRIMARY KEY,request_id INTEGER NOT NULL REFERENCES desk_requests(id),action TEXT NOT NULL,reference TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS desk_comments(id INTEGER PRIMARY KEY,request_id INTEGER NOT NULL REFERENCES desk_requests(id),text TEXT NOT NULL,attachments TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS desk_tasks(id INTEGER PRIMARY KEY,request_id INTEGER NOT NULL REFERENCES desk_requests(id),payload TEXT NOT NULL); CREATE TABLE IF NOT EXISTS desk_files(id TEXT PRIMARY KEY,name TEXT NOT NULL,mime TEXT NOT NULL); CREATE INDEX IF NOT EXISTS desk_event_request ON desk_events(request_id,id);"
        )
        from identity import prepare_audit, prepare_users

        prepare_audit(c, "desk_events", "request", "request_id")
        prepare_audit(c, "desk_comments", "requestComment", "request_id")
        if not c.execute("SELECT 1 FROM desk_requests LIMIT 1").fetchone():
            for id, cid, title, status, priority, kind, agent in [
                (
                    1042,
                    1,
                    "Revisar la confirmación de turnos",
                    REQUEST.IN_PROGRESS,
                    PRIORITY.HIGH,
                    "Incidente",
                    2,
                ),
                (
                    1041,
                    2,
                    "Preparar capacitación para el equipo",
                    REQUEST.NEW,
                    PRIORITY.MEDIUM,
                    "Capacitación",
                    None,
                ),
                (
                    1040,
                    1,
                    "Verificar configuración del servicio",
                    REQUEST.RESOLVED,
                    PRIORITY.LOW,
                    "Consulta",
                    2,
                ),
            ]:
                sub = next(s for s in crm.rows(c, "subscriptions") if s["clientId"] == cid)
                d = dict(
                    clientId=cid,
                    subscriptionId=sub["id"],
                    contactId=None,
                    title=SEED_TEXT[id][0],
                    description=SEED_TEXT[id][1],
                    status=status,
                    priority=priority,
                    type=kind,
                    queue="Mesa de Ayuda",
                    agentId=agent,
                    createdAt=team.now(),
                    updatedAt=team.now(),
                    attachments=[],
                )
                c.execute(
                    "INSERT INTO desk_requests(id,client_id,subscription_id,payload) VALUES(?,?,?,?)",
                    (id, cid, sub["id"], json.dumps(d, ensure_ascii=False)),
                )
                event(
                    c,
                    id,
                    "Solicitud importada",
                    "Registro inicial de ejemplo; fecha de importación",
                )
        aliases = {
            "Pendiente": REQUEST.NEW,
            "Asignada": REQUEST.NEW,
            "En proceso": REQUEST.IN_PROGRESS,
            "Resuelto": REQUEST.RESOLVED,
        }
        for row in c.execute("SELECT id,payload FROM desk_requests").fetchall():
            payload = json.loads(row["payload"])
            if payload.get("status") in aliases:
                payload["status"] = aliases[payload["status"]]
                c.execute(
                    "UPDATE desk_requests SET payload=?,version=version+1 WHERE id=?",
                    (json.dumps(payload, ensure_ascii=False), row["id"]),
                )
                event(c, row["id"], "Estado normalizado", payload["status"])
        for id, (title, description) in SEED_TEXT.items():
            r = get(c, id)
            if (
                r
                and r["version"] == 1
                and r["description"]
                == "Solicitud de ejemplo importada de Nexo. Completar el contexto con el contacto de la institución."
            ):
                r.update(title=title, description=description)
                c.execute(
                    "UPDATE desk_requests SET payload=? WHERE id=?",
                    (
                        json.dumps(
                            {k: v for k, v in r.items() if k not in ["id", "version"]},
                            ensure_ascii=False,
                        ),
                        id,
                    ),
                )


def validate_files(c, files):
    if not isinstance(files, list) or len(files) > 10:
        raise team.Validation({"attachments": "Adjuntá hasta 10 archivos."})
    out = []
    for path in files:
        if (
            not isinstance(path, str)
            or not re.fullmatch("/api/desk/files/[a-f0-9]{64}", path)
            or not c.execute(
                "SELECT 1 FROM desk_files WHERE id=?", (path.rsplit("/", 1)[-1],)
            ).fetchone()
        ):
            raise team.Validation({"attachments": "Hay un archivo no válido."})
        if path not in out:
            out.append(path)
    return out


def employee(id):
    if not isinstance(id, int) or isinstance(id, bool):
        return None
    c = team.connect()
    try:
        r = c.execute("SELECT * FROM employees WHERE id=?", (id,)).fetchone()
        return team.unpack(r) if r else None
    finally:
        c.close()


def validate_new(c, data):
    errors = {}
    d = {}
    for k in ["title", "description", "type", "priority"]:
        v = data.get(k, "")
        d[k] = v.strip() if isinstance(v, str) else ""
        if not d[k]:
            errors[k] = "Este campo es obligatorio."
    if len(d["title"]) > 180:
        errors["title"] = "Usá hasta 180 caracteres."
    if len(d["description"]) > 10000:
        errors["description"] = "Usá hasta 10.000 caracteres."
    if d["type"] not in TYPES:
        errors["type"] = "Elegí un tipo válido."
    if d["priority"] not in PRIORITIES:
        errors["priority"] = "Elegí una prioridad válida."
    for k, target in [
        ("clientId", "clients"),
        ("subscriptionId", "subscriptions"),
        ("contactId", "contacts"),
    ]:
        value = data.get(k)
        d[k] = value
        if not isinstance(value, int) or not crm.record(c, target, value):
            errors[k] = "Seleccioná un registro válido."
    client = crm.record(c, "clients", d["clientId"]) if "clientId" not in errors else None
    if client and client["status"] in ["Prospecto", "Finalizado"]:
        errors["clientId"] = "Seleccioná un cliente con una relación comercial vigente."
    sub = (
        crm.record(c, "subscriptions", d["subscriptionId"])
        if "subscriptionId" not in errors
        else None
    )
    if sub and (sub["clientId"] != d["clientId"] or sub["status"] == "Finalizado"):
        errors["subscriptionId"] = "Elegí un producto o servicio contratado por este cliente."
    contact = crm.record(c, "contacts", d["contactId"]) if "contactId" not in errors else None
    if contact and (contact["clientId"] != d["clientId"] or contact["status"] != LABOR.ACTIVE):
        errors["contactId"] = "Elegí un contacto activo de este cliente."
    d["attachments"] = validate_files(c, data.get("attachments", []))
    if errors:
        raise team.Validation(errors)
    d.update(
        status=REQUEST.NEW,
        queue="Mesa de Ayuda",
        agentId=None,
        createdAt=team.now(),
        updatedAt=team.now(),
    )
    return d


class Handler(crm.Handler):
    def do_GET(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/desk"):
            return super().do_GET()
        try:
            self.guard()
            with crm.connect() as c:
                if path == "/api/desk":
                    return self.send_json(
                        200,
                        {
                            "requests": [
                                get(c, r["id"])
                                for r in c.execute("SELECT id FROM desk_requests ORDER BY id DESC")
                            ],
                            "tasks": [
                                {**json.loads(r["payload"]), "id": r["id"]}
                                for r in c.execute("SELECT * FROM desk_tasks")
                            ],
                            "events": [
                                dict(r)
                                for r in c.execute("SELECT * FROM desk_events ORDER BY id DESC")
                            ],
                            "comments": [
                                {**dict(r), "attachments": json.loads(r["attachments"])}
                                for r in c.execute("SELECT * FROM desk_comments ORDER BY id")
                            ],
                            "files": [dict(r) for r in c.execute("SELECT * FROM desk_files")],
                            "states": STATES,
                            "priorities": PRIORITIES,
                            "types": TYPES,
                            "transitions": TRANSITIONS,
                            "capabilities": {
                                "Administrador": ["supervisar", "reasignar", "priorizar"],
                                "Soporte": ["tomar", "atender", "comentar", "derivar", "resolver"],
                                "Técnico": ["consultar trabajo vinculado"],
                            },
                            "authenticationEnforced": False,
                        },
                    )
                if re.fullmatch("/api/desk/files/[a-f0-9]{64}", path):
                    id = path.rsplit("/", 1)[-1]
                    r = c.execute("SELECT * FROM desk_files WHERE id=?", (id,)).fetchone()
                    p = crm.DATA / "files" / ("desk-" + id)
                    if not r or not p.exists():
                        return self.send_error(404)
                    raw = p.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", r["mime"])
                    self.send_header("Content-Security-Policy", "sandbox")
                    inline = r["mime"].startswith("image/") or r["mime"] == "application/pdf"
                    self.send_header(
                        "Content-Disposition",
                        (
                            "inline"
                            if inline and "download" not in parse_qs(urlparse(self.path).query)
                            else "attachment"
                        )
                        + "; filename*=UTF-8''"
                        + quote(r["name"]),
                    )
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
            self.send_error(404)
        except team.Validation as e:
            self.send_json(e.status, {"errors": e.fields})

    def mutate(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/desk"):
            return super().mutate()
        try:
            self.guard(True)
            n = team.content_length(self.headers)
            if n < 1 or n > 15000000:
                raise team.Validation({"attachments": "Archivo demasiado grande."}, 413)
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                raise team.Validation({"_form": "Formato no válido."}, 415)
            d = json.loads(self.rfile.read(n))
            if not isinstance(d, dict):
                raise team.Validation({"_form": "Datos inválidos."})
            with crm.connect() as c:
                if path == "/api/desk/files" and self.command == "POST":
                    try:
                        raw = base64.b64decode(d.get("base64", ""), validate=True)
                        name = Path(str(d.get("name", "archivo")).replace("\\", "/")).name[:160]
                        ext = Path(name).suffix.lower()
                        if not raw or len(raw) > 10 * 1024 * 1024:
                            raise ValueError()
                        if ext in [".png", ".jpg", ".jpeg", ".webp"]:
                            raw, fmt = team.clean_image(raw, 10 * 1024 * 1024)
                            mime = team.IMAGE_FORMATS[fmt][0]
                        elif ext == ".pdf":
                            from pypdf import PdfReader

                            if not raw.startswith(b"%PDF-"):
                                raise ValueError()
                            pdf = PdfReader(io.BytesIO(raw), strict=True)
                            if pdf.is_encrypted or not len(pdf.pages):
                                raise ValueError()
                            mime = "application/pdf"
                        elif ext in [".txt", ".log", ".csv"]:
                            raw.decode("utf-8")
                            mime = "text/plain; charset=utf-8"
                        elif ext in [".docx", ".xlsx"]:
                            z = zipfile.ZipFile(io.BytesIO(raw))
                            names = z.namelist()
                            if (
                                "[Content_Types].xml" not in names
                                or ("word/document.xml" if ext == ".docx" else "xl/workbook.xml")
                                not in names
                                or any("vbaproject" in v.lower() for v in names)
                                or sum(i.file_size for i in z.infolist()) > 50000000
                            ):
                                raise ValueError()
                            mime = "application/vnd.openxmlformats-officedocument." + (
                                "wordprocessingml.document"
                                if ext == ".docx"
                                else "spreadsheetml.sheet"
                            )
                        else:
                            raise ValueError()
                    except Exception:
                        raise team.Validation(
                            {
                                "attachments": "Archivo no válido. Usá imágenes, PDF, DOCX, XLSX, TXT, CSV o LOG UTF-8, hasta 10 MB."
                            }
                        )
                    id = hashlib.sha256(raw).hexdigest()
                    (crm.DATA / "files" / ("desk-" + id)).write_bytes(raw)
                    c.execute("INSERT OR IGNORE INTO desk_files VALUES(?,?,?)", (id, name, mime))
                    return self.send_json(201, {"url": "/api/desk/files/" + id, "name": name})
                if path == "/api/desk/requests" and self.command == "POST":
                    c.execute("BEGIN IMMEDIATE")
                    request = validate_new(c, d)
                    id = c.execute(
                        "INSERT INTO desk_requests(client_id,subscription_id,contact_id,payload) VALUES(?,?,?,?)",
                        (
                            request["clientId"],
                            request["subscriptionId"],
                            request["contactId"],
                            json.dumps(request, ensure_ascii=False),
                        ),
                    ).lastrowid
                    event(c, id, "Solicitud creada", "Mesa de Ayuda · Sin asignar")
                    for f in request["attachments"]:
                        event(c, id, "Archivo agregado", f)
                    crm.audit(
                        c,
                        request["clientId"],
                        "Solicitud creada",
                        "SOL-" + str(id) + " · " + request["title"],
                    )
                    return self.send_json(201, {"request": get(c, id)})
                match = re.fullmatch(
                    r"/api/desk/requests/(\d+)/(update|comments|tasks|task-status)", path
                )
                if not match or self.command != "POST":
                    return self.send_error(404)
                id = int(match[1])
                c.execute("BEGIN IMMEDIATE")
                old = get(c, id)
                if not old:
                    raise team.Validation({"_form": "Solicitud no encontrada."}, 404)
                if d.get("version") != old["version"]:
                    raise team.Validation(
                        {
                            "_form": "La solicitud cambió en otra sesión. Los datos se actualizaron; revisá y volvé a intentar."
                        },
                        409,
                    )
                if match[2] == "update":
                    previous_status = old["status"]
                    for key in ["status", "priority", "agentId"]:
                        if key not in d or d[key] == old.get(key):
                            continue
                        value = d[key]
                        if key == "status" and value not in TRANSITIONS[old["status"]]:
                            raise team.Validation(
                                {"status": "Este cambio no corresponde al flujo de atención."}
                            )
                        if key == "priority" and value not in PRIORITIES:
                            raise team.Validation({"priority": "Elegí una prioridad válida."})
                        if key == "agentId" and value is not None:
                            e = employee(value)
                            if not e or e["laborStatus"] != LABOR.ACTIVE:
                                raise team.Validation({"agentId": "Seleccioná un empleado activo."})
                        reference = (
                            employee(value)["name"]
                            if key == "agentId" and value
                            else str(value or "Sin asignar")
                        )
                        event(
                            c,
                            id,
                            {
                                "status": "Estado actualizado",
                                "priority": "Prioridad actualizada",
                                "agentId": (
                                    "Agente asignado"
                                    if not old.get("agentId")
                                    else "Agente cambiado"
                                ),
                            }[key],
                            reference,
                        )
                        old[key] = value
                    if old["status"] != previous_status and old["status"] in [
                        REQUEST.RESOLVED,
                        REQUEST.CLOSED,
                    ]:
                        old["resolvedAt" if old["status"] == REQUEST.RESOLVED else "closedAt"] = (
                            team.now()
                        )
                    # Reabrir invalida las fechas de cierre; el historial queda en desk_events. None (no pop): PostgreSQL fusiona el payload previo.
                    if old["status"] == REQUEST.IN_PROGRESS and previous_status in [
                        REQUEST.RESOLVED,
                        REQUEST.CLOSED,
                    ]:
                        old["resolvedAt"] = old["closedAt"] = None
                elif match[2] == "comments":
                    content = d.get("text", "")
                    files = validate_files(c, d.get("attachments", []))
                    if not isinstance(content, str) or not content.strip() or len(content) > 10000:
                        raise team.Validation(
                            {"text": "Escribí un comentario de hasta 10.000 caracteres."}
                        )
                    c.execute(
                        "INSERT INTO desk_comments(request_id,text,attachments,actor,created_at) VALUES(?,?,?,?,?)",
                        (id, content.strip(), json.dumps(files), actor(), team.now()),
                    )
                    event(c, id, "Comentario interno agregado", content.strip()[:180])
                    for f in files:
                        event(c, id, "Archivo agregado", f)
                elif match[2] == "task-status":
                    taskrow = c.execute(
                        "SELECT * FROM desk_tasks WHERE id=? AND request_id=?",
                        (d.get("taskId"), id),
                    ).fetchone()
                    if not taskrow or not isinstance(d.get("done"), bool):
                        raise team.Validation({"_form": "Tarea o estado no válido."})
                    task = json.loads(taskrow["payload"])
                    task["done"] = d["done"]
                    task["status"] = TASK.COMPLETED if d["done"] else TASK.PENDING
                    c.execute(
                        "UPDATE desk_tasks SET payload=? WHERE id=?",
                        (json.dumps(task, ensure_ascii=False), taskrow["id"]),
                    )
                    event(
                        c,
                        id,
                        "Estado de tarea actualizado",
                        "TAR-" + str(taskrow["id"]).zfill(3) + " · " + task["status"],
                    )
                elif match[2] == "tasks":
                    errors = {}
                    title = d.get("title", "")
                    owner = d.get("owner")
                    e = employee(owner)
                    due = d.get("due", "")
                    priority = d.get("priority", PRIORITY.MEDIUM)
                    if not isinstance(title, str) or not title.strip() or len(title) > 180:
                        errors["title"] = "Ingresá un título de hasta 180 caracteres."
                    if not e or e["laborStatus"] != LABOR.ACTIVE:
                        errors["owner"] = "Seleccioná un empleado activo."
                    if priority not in PRIORITIES:
                        errors["priority"] = "Elegí una prioridad válida."
                    if due:
                        try:
                            date.fromisoformat(due)
                        except (ValueError, TypeError):
                            errors["due"] = "Ingresá una fecha válida."
                    if errors:
                        raise team.Validation(errors)
                    task = dict(
                        title=title.strip(),
                        owner=owner,
                        client=old["clientId"],
                        ticket=id,
                        status=TASK.PENDING,
                        priority=priority,
                        due=due,
                        done=False,
                        createdAt=team.now(),
                    )
                    tid = c.execute(
                        "INSERT INTO desk_tasks(request_id,payload) VALUES(?,?)",
                        (id, json.dumps(task, ensure_ascii=False)),
                    ).lastrowid
                    event(
                        c,
                        id,
                        "Tarea vinculada",
                        "TAR-" + str(tid).zfill(3) + " · " + task["title"] + " · " + e["name"],
                    )
                old["updatedAt"] = team.now()
                c.execute(
                    "UPDATE desk_requests SET payload=?,version=version+1 WHERE id=?",
                    (
                        json.dumps(
                            {k: v for k, v in old.items() if k not in ["id", "version"]},
                            ensure_ascii=False,
                        ),
                        id,
                    ),
                )
                self.send_json(200, {"request": get(c, id)})
        except team.Validation as e:
            self.send_json(e.status, {"errors": e.fields})
        except (ValueError, TypeError):
            self.send_json(400, {"errors": {"_form": "Datos inválidos."}})
        except Exception:
            team.log.exception("Error interno en %s %s", self.command, urlparse(self.path).path)
            self.send_json(
                500,
                {"errors": {"_form": "No se pudo guardar. Conservamos los datos para reintentar."}},
            )
