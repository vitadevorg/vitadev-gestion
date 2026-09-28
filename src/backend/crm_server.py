"""Clientes: persistencia local y relaciones comerciales. Reutiliza Equipo sin modificarlo."""

from identity import actor
from domain import REQUEST, PRIORITY, LEAVE, LABOR, AVAILABILITY, TASK
import base64, hashlib, io, json, os, re, sqlite3
from datetime import date
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote
import team_server as team

DATA = Path(os.environ.get("NEXO_CRM_DATA", str(team.ROOT / "work" / "crm-data")))
DATA.mkdir(parents=True, exist_ok=True)
(DATA / "files").mkdir(exist_ok=True)
DB = DATA / "crm.sqlite3"
ASSET_LOGOS = {
    "assets/clients/" + p.name
    for p in (team.ROOT / "src/assets/clients").iterdir()
    if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
}
KINDS = ["clients", "contacts", "catalog", "subscriptions", "contracts"]
OPTIONS = {
    "clientStates": ["Prospecto", "Implementación", LABOR.ACTIVE, "Suspendido", "Finalizado"],
    "organizationTypes": [
        "Hospital",
        "Clínica",
        "Sanatorio",
        "Consultorio",
        "Centro médico",
        "Obra social",
        "Farmacia",
        "Empresa",
        "Organismo público",
        "Otro",
    ],
    "productTypes": ["Producto de software", "Servicio", "Otro"],
    "contractStates": [
        "Borrador",
        "Pendiente de firma",
        "Vigente",
        "Próximo a vencer",
        "Vencido",
        "Finalizado",
    ],
    "periods": ["Mensual", "Trimestral", "Semestral", "Anual", "Pago único", "Personalizada"],
    "renewals": ["Automática", "Manual", "Sin renovación"],
    "subscriptionStates": ["Implementación", LABOR.ACTIVE, "Suspendido", "Finalizado"],
}


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect():
    if team.pg.enabled():
        return team.pg.connect()
    c = sqlite3.connect(DB, timeout=15, factory=Connection)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    from identity import bind

    bind(c)
    return c


def rows(c, kind):
    return [decode(r) for r in c.execute("SELECT * FROM records WHERE kind=? ORDER BY id", (kind,))]


def decode(r):
    return {**json.loads(r["payload"]), "id": r["id"], "version": r["version"]}


def record(c, kind, id):
    r = c.execute("SELECT * FROM records WHERE kind=? AND id=?", (kind, id)).fetchone()
    return decode(r) if r else None


def add(c, kind, d, id=None):
    return c.execute(
        "INSERT INTO records(kind,id,payload,unique_key,client_id) VALUES(?,?,?,?,?)",
        (kind, id, json.dumps(d, ensure_ascii=False), unique(kind, d), d.get("clientId")),
    ).lastrowid


def unique(kind, d):
    return (
        str(d.get({"clients": "cuit", "catalog": "name", "contracts": "number"}.get(kind, ""), ""))
        .strip()
        .casefold()
        or None
    )


def audit(c, client, action, reference):
    c.execute(
        "INSERT INTO activity(client_id,action,reference,actor,created_at) VALUES(?,?,?,?,?)",
        (client, action, reference, actor(), team.now()),
    )


def init():
    if team.pg.enabled():
        return team.pg.ensure_ready()
    with connect() as c:
        c.executescript(
            "CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, client_id INTEGER REFERENCES records(id), unique_key TEXT, version INTEGER NOT NULL DEFAULT 1,payload TEXT NOT NULL, UNIQUE(kind,unique_key)); CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY,client_id INTEGER REFERENCES records(id),action TEXT NOT NULL,reference TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL); CREATE INDEX IF NOT EXISTS activity_client ON activity(client_id,id); CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,name TEXT NOT NULL,mime TEXT NOT NULL);"
        )
        from identity import prepare_audit, prepare_users

        prepare_audit(c, "activity", "client", "client_id")
        if not c.execute("SELECT 1 FROM records LIMIT 1").fetchone():
            for id, name, city, province, owner, status, logo in [
                (
                    1,
                    "Sanatorio 9 de Julio",
                    "San Miguel de Tucumán",
                    "Tucumán",
                    1,
                    LABOR.ACTIVE,
                    "sanatorio-9-de-julio",
                ),
                (2, "Centro Médico Demo", "Salta", "Salta", 4, "Implementación", "default-company"),
            ]:
                add(
                    c,
                    "clients",
                    dict(
                        name=name,
                        legalName="",
                        cuit="",
                        organizationType="Sanatorio" if id == 1 else "Centro médico",
                        country="Argentina",
                        province=province,
                        city=city,
                        address="",
                        postalCode="",
                        owner=owner,
                        status=status,
                        logo=(
                            "assets/clients/sanatorio9dejulio.jpeg"
                            if id == 1
                            else "assets/clients/default-company.png"
                        ),
                        createdAt=team.now(),
                        since="",
                        imported=True,
                    ),
                    id,
                )
                audit(
                    c,
                    id,
                    "Registro inicial importado",
                    "Datos de ejemplo; información fiscal y fechas comerciales pendientes",
                )
            pid = add(
                c,
                "catalog",
                dict(
                    name="SAMSA",
                    description="Software de gestión para instituciones de salud.",
                    type="Producto de software",
                    status=LABOR.ACTIVE,
                    plans=[],
                    configFields=["Historia Clínica", "Turnos", "Pacientes", "Receta Electrónica"],
                    createdAt=team.now(),
                ),
            )
            for cid in [1, 2]:
                add(
                    c,
                    "subscriptions",
                    dict(
                        clientId=cid,
                        productId=pid,
                        plan="",
                        status=LABOR.ACTIVE if cid == 1 else "Implementación",
                        start="",
                        configuration=[],
                        createdAt=team.now(),
                    ),
                )


def cuit_valid(value):
    if not re.fullmatch(r"\d{11}", value):
        return False
    check = 11 - sum(int(n) * w for n, w in zip(value[:10], [5, 4, 3, 2, 7, 6, 5, 4, 3, 2])) % 11
    return (0 if check == 11 else 9 if check == 10 else check) == int(value[-1]) and len(
        set(value)
    ) > 1


def validate(c, kind, data, old=None):
    d = {}
    errors = {}
    old = old or {}
    if kind == "clients" and old and data.get("lifecycle") is True:
        if data.get("confirm") is not True or data.get("status") != "Finalizado":
            raise team.Validation({"confirm": "Confirmá la finalización."})
        return {
            **{k: v for k, v in old.items() if k not in ["id", "version"]},
            "status": "Finalizado",
            "updatedAt": team.now(),
        }

    def text(key, required=False, maxlen=250):
        value = data.get(key, "")
        value = value.strip() if isinstance(value, str) else ""
        d[key] = value
        if required and not value:
            errors[key] = "Este campo es obligatorio."
        if len(value) > maxlen:
            errors[key] = f"Usá hasta {maxlen} caracteres."
        return value

    def choice(key, choices, required=True):
        value = text(key, required)
        if value not in choices and (required or value):
            errors[key] = "Seleccioná una opción válida."

    def dt(key, required=False):
        value = text(key, required)
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                errors[key] = "Ingresá una fecha válida."

    def ref(key, target, required=True):
        value = data.get(key)
        r = record(c, target, value) if isinstance(value, int) else None
        d[key] = value
        if not r and required:
            errors[key] = "Seleccioná un registro válido."
        return r

    def strings(key):
        values = data.get(key, [])
        if (
            not isinstance(values, list)
            or len(values) > 40
            or any(not isinstance(v, str) or not v.strip() or len(v) > 100 for v in values)
        ):
            errors[key] = "Usá hasta 40 valores de 100 caracteres."
            values = []
        d[key] = list(dict.fromkeys(v.strip() for v in values))

    if kind in ["contacts", "subscriptions", "contracts"]:
        client = ref("clientId", "clients")
        if old and old.get("clientId") != d["clientId"]:
            errors["clientId"] = "El cliente de un registro histórico no puede cambiar."
        if client and client["status"] == "Finalizado" and not old:
            errors["clientId"] = "La relación comercial está finalizada."
    if kind == "clients":
        for k in ["name", "legalName", "organizationType", "country", "province", "city"]:
            text(k, True)
        choice("organizationType", OPTIONS["organizationTypes"])
        choice("status", OPTIONS["clientStates"])
        if not old and d["status"] not in OPTIONS["clientStates"][:3]:
            errors["status"] = "Elegí Prospecto, Implementación o Activo."
        d["cuit"] = re.sub(r"[-\s]", "", text("cuit", True))
        if not cuit_valid(d["cuit"]):
            errors["cuit"] = "El CUIT debe tener 11 dígitos y un verificador válido."
        for k in ["address", "postalCode"]:
            text(k)
        dt("since")
        if d["since"] and d["since"] > date.today().isoformat():
            errors["since"] = "La fecha no puede ser futura."
        owner = data.get("owner")
        d["owner"] = owner
        with team.connect() as ec:
            r = ec.execute(
                "SELECT * FROM employees WHERE id=?", (owner if isinstance(owner, int) else -1,)
            ).fetchone()
        if not r or (team.unpack(r)["laborStatus"] != LABOR.ACTIVE and owner != old.get("owner")):
            errors["owner"] = "Seleccioná un responsable activo de VitaDev."
        logo = text("logo")
        if logo and logo not in ASSET_LOGOS and not file_valid(c, logo, "image/"):
            errors["logo"] = "Seleccioná una imagen válida."
        if (
            old.get("status") != "Finalizado"
            and d["status"] == "Finalizado"
            and data.get("confirm") is not True
        ):
            errors["confirm"] = "Confirmá la finalización de la relación comercial."
    elif kind == "contacts":
        for k in ["firstName", "lastName", "email"]:
            text(k, True)
        for k in ["position", "phone", "role"]:
            text(k)
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", d["email"]):
            errors["email"] = "Ingresá un correo válido."
        choice("status", [LABOR.ACTIVE, LABOR.INACTIVE])
        d["principal"] = data.get("principal") is True
        if d["status"] == LABOR.INACTIVE:
            d["principal"] = False
    elif kind == "catalog":
        text("name", True)
        text("description", True, 2000)
        choice("type", OPTIONS["productTypes"])
        choice("status", [LABOR.ACTIVE, LABOR.INACTIVE])
        strings("plans")
        strings("configFields")
        if old:
            used = [s for s in rows(c, "subscriptions") if s["productId"] == old["id"]]
            if any(s.get("plan") and s["plan"] not in d["plans"] for s in used):
                errors["plans"] = "Conservá los planes que tienen contrataciones asociadas."
            if any(
                any(v not in d["configFields"] for v in s.get("configuration", [])) for s in used
            ):
                errors["configFields"] = (
                    "Conservá las opciones utilizadas por contrataciones existentes."
                )
    elif kind == "subscriptions":
        product = ref("productId", "catalog")
        text("plan")
        choice("status", OPTIONS["subscriptionStates"])
        dt("start", True)
        strings("configuration")
        if old and d["productId"] != old["productId"]:
            errors["productId"] = "El producto de una contratación histórica no puede cambiar."
        if product:
            if product["status"] != LABOR.ACTIVE and not old:
                errors["productId"] = "Este producto no admite nuevas contrataciones."
            if d["plan"] and d["plan"] not in product["plans"]:
                errors["plan"] = "Elegí un plan del catálogo."
            if any(v not in product["configFields"] for v in d["configuration"]):
                errors["configuration"] = "Configuración no válida para este producto."
    elif kind == "contracts":
        text("number", True)
        choice("status", OPTIONS["contractStates"])
        dt("signed")
        dt("start", True)
        dt("end")
        choice("renewal", OPTIONS["renewals"])
        choice("period", OPTIONS["periods"])
        choice("currency", ["ARS", "USD", "EUR"])
        text("notes", False, 4000)
        text("document")
        if d["end"] and d["start"] and d["end"] < d["start"]:
            errors["end"] = "El vencimiento no puede ser anterior al inicio."
        if d["signed"] and d["signed"] > date.today().isoformat():
            errors["signed"] = "La fecha de firma no puede ser futura."
        value = data.get("amount", "")
        d["amount"] = value
        try:
            from decimal import Decimal

            if value != "" and (
                not Decimal(str(value)).is_finite()
                or Decimal(str(value)) < 0
                or Decimal(str(value)) > Decimal("999999999999.99")
                or Decimal(str(value)).as_tuple().exponent < -2
            ):
                raise ValueError()
        except Exception:
            errors["amount"] = "Ingresá un importe positivo con hasta dos decimales."
        ids = data.get("subscriptionIds", [])
        d["subscriptionIds"] = ids
        if (
            not isinstance(ids, list)
            or not ids
            or len(ids) > 100
            or any(
                not isinstance(i, int)
                or not (s := record(c, "subscriptions", i))
                or s["clientId"] != d["clientId"]
                for i in ids
            )
        ):
            errors["subscriptionIds"] = "Seleccioná contrataciones de este cliente."
        if d["document"] and not file_valid(c, d["document"], "application/pdf"):
            errors["document"] = "Adjuntá un PDF válido."
        if d["document"] and "document" not in errors:
            d["documentName"] = c.execute(
                "SELECT name FROM files WHERE id=?", (d["document"].rsplit("/", 1)[-1],)
            ).fetchone()["name"]
        if (
            old
            and old["status"] != "Finalizado"
            and d["status"] == "Finalizado"
            and data.get("confirm") is not True
        ):
            errors["confirm"] = "Confirmá la finalización del contrato."
    key = unique(kind, d)
    if key:
        r = c.execute(
            "SELECT id FROM records WHERE kind=? AND unique_key=?", (kind, key)
        ).fetchone()
        if r and r["id"] != old.get("id"):
            errors[{"clients": "cuit", "catalog": "name", "contracts": "number"}[kind]] = (
                "Ya existe un registro con este valor."
            )
    if errors:
        raise team.Validation(errors)
    d["createdAt"] = old.get("createdAt", team.now())
    d["updatedAt"] = team.now()
    return d


def file_valid(c, path, prefix):
    r = (
        c.execute("SELECT mime FROM files WHERE id=?", (path.rsplit("/", 1)[-1],)).fetchone()
        if path.startswith("/api/crm/files/")
        else None
    )
    return r and r["mime"].startswith(prefix)


class Handler(team.Handler):
    def do_GET(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/crm"):
            return super().do_GET()
        try:
            self.guard()
            with connect() as c:
                if path == "/api/crm":
                    return self.send_json(
                        200,
                        {
                            **{k: rows(c, k) for k in KINDS},
                            "activity": [
                                dict(r)
                                for r in c.execute("SELECT * FROM activity ORDER BY id DESC")
                            ],
                            "options": OPTIONS,
                            "today": date.today().isoformat(),
                        },
                    )
                if re.fullmatch("/api/crm/files/[a-f0-9]{64}", path):
                    id = path.rsplit("/", 1)[-1]
                    r = c.execute("SELECT * FROM files WHERE id=?", (id,)).fetchone()
                    p = DATA / "files" / id
                    if not r or not p.exists():
                        return self.send_error(404)
                    raw = p.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", r["mime"])
                    self.send_header("Content-Security-Policy", "sandbox")
                    self.send_header(
                        "Content-Disposition",
                        (
                            "attachment"
                            if "download" in parse_qs(urlparse(self.path).query)
                            else "inline"
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
        if not path.startswith("/api/crm"):
            return super().mutate()
        try:
            self.guard(True)
            n = team.content_length(self.headers)
            if n < 1 or n > 15000000:
                raise team.Validation({"_form": "El archivo supera el tamaño permitido."}, 413)
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                raise team.Validation({"_form": "Formato no válido."}, 415)
            d = json.loads(self.rfile.read(n))
            if not isinstance(d, dict):
                raise team.Validation({"_form": "Datos inválidos."})
            with connect() as c:
                if path == "/api/crm/files" and self.command == "POST":
                    try:
                        raw = base64.b64decode(d.get("base64", ""), validate=True)
                        name = Path(str(d.get("name", "archivo")).replace("\\", "/")).name[:160]
                        if d.get("kind") == "document":
                            from pypdf import PdfReader

                            if (
                                len(raw) > 10 * 1024 * 1024
                                or not name.lower().endswith(".pdf")
                                or not raw.startswith(b"%PDF-")
                            ):
                                raise ValueError()
                            pdf = PdfReader(io.BytesIO(raw), strict=True)
                            if pdf.is_encrypted or not len(pdf.pages):
                                raise ValueError()
                            mime = "application/pdf"
                        else:
                            raw, fmt = team.clean_image(raw, 3 * 1024 * 1024)
                            mime = team.IMAGE_FORMATS[fmt][0]
                    except Exception:
                        raise team.Validation(
                            {
                                d.get(
                                    "kind", "logo"
                                ): "Usá un PDF válido sin contraseña de hasta 10 MB, o una imagen PNG/JPEG/WebP de hasta 3 MB."
                            }
                        )
                    id = hashlib.sha256(raw).hexdigest()
                    (DATA / "files" / id).write_bytes(raw)
                    c.execute("INSERT OR IGNORE INTO files VALUES(?,?,?)", (id, name, mime))
                    return self.send_json(201, {"url": "/api/crm/files/" + id, "name": name})
                if path == "/api/crm/events" and self.command == "POST":
                    if (
                        not isinstance(d.get("clientId"), int)
                        or not record(c, "clients", d["clientId"])
                        or not isinstance(d.get("ticketId"), int)
                        or not isinstance(d.get("title"), str)
                    ):
                        raise team.Validation({"_form": "Referencia de solicitud no válida."})
                    audit(
                        c,
                        d["clientId"],
                        "Solicitud creada",
                        "#" + str(d["ticketId"]) + " · " + d["title"][:250],
                    )
                    return self.send_json(201, {"ok": True})
                match = re.fullmatch(
                    r"/api/crm/(clients|contacts|catalog|subscriptions|contracts)(?:/(\d+))?", path
                )
                if not match:
                    return self.send_error(404)
                kind, id = match[1], int(match[2]) if match[2] else None
                if (id is None and self.command != "POST") or (id and self.command != "PUT"):
                    raise team.Validation({"_form": "Método no permitido."}, 405)
                c.execute("BEGIN IMMEDIATE")
                old = record(c, kind, id) if id else None
                if id and not old:
                    raise team.Validation({"_form": "Registro no encontrado."}, 404)
                if old and d.get("version") != old["version"]:
                    raise team.Validation(
                        {
                            "_form": "Este registro cambió en otra sesión. Cerrá el formulario y volvé a abrirlo para editar la versión actual."
                        },
                        409,
                    )
                clean = validate(c, kind, d, old)
                contact = None
                if kind == "clients" and not old:
                    # Validación atómica: nunca crear una organización sin su contacto principal.
                    initial = d.get("primaryContact", {})
                    if not isinstance(initial, dict):
                        initial = {}
                    contact = initial
                if old:
                    c.execute(
                        "UPDATE records SET payload=?,unique_key=?,version=version+1 WHERE id=?",
                        (json.dumps(clean, ensure_ascii=False), unique(kind, clean), id),
                    )
                else:
                    id = add(c, kind, clean)
                if contact is not None:
                    try:
                        contact = validate(
                            c,
                            "contacts",
                            {**contact, "clientId": id, "status": LABOR.ACTIVE, "principal": True},
                        )
                    except team.Validation as e:
                        raise team.Validation(
                            {"primaryContact." + k: v for k, v in e.fields.items()}
                        )
                    add(c, "contacts", contact)
                if kind == "contacts" and clean["principal"]:
                    for other in rows(c, "contacts"):
                        if (
                            other["id"] != id
                            and other["clientId"] == clean["clientId"]
                            and other["principal"]
                        ):
                            other["principal"] = False
                            c.execute(
                                "UPDATE records SET payload=?,version=version+1 WHERE id=?",
                                (
                                    json.dumps(
                                        {
                                            k: v
                                            for k, v in other.items()
                                            if k not in ["id", "version"]
                                        },
                                        ensure_ascii=False,
                                    ),
                                    other["id"],
                                ),
                            )
                            audit(
                                c,
                                clean["clientId"],
                                "Contacto principal reemplazado",
                                (
                                    other.get("firstName", "") + " " + other.get("lastName", "")
                                ).strip(),
                            )
                client = id if kind == "clients" else clean.get("clientId")
                label = (
                    clean.get("name")
                    or clean.get("number")
                    or (clean.get("firstName", "") + " " + clean.get("lastName", "")).strip()
                    or str(id)
                )
                action = {
                    "clients": "Cliente",
                    "contacts": "Contacto",
                    "catalog": "Producto/servicio",
                    "subscriptions": "Contratación",
                    "contracts": "Contrato",
                }[kind] + (" actualizado" if old else " creado")
                if old and clean.get("status") != old.get("status"):
                    action += " · " + clean["status"]
                if (
                    kind == "contracts"
                    and old
                    and clean.get("signed")
                    and clean["signed"] != old.get("signed")
                ):
                    action += " · firma registrada"
                if kind == "contracts" and old and clean.get("end", "") > old.get("end", ""):
                    action += " · vigencia ampliada"
                audit(c, client, action, label)
                if contact is not None:
                    audit(
                        c,
                        id,
                        "Contacto principal agregado",
                        contact["firstName"] + " " + contact["lastName"],
                    )
                result = record(c, kind, id)
            self.send_json(200 if old else 201, {"record": result})
        except team.Validation as e:
            self.send_json(e.status, {"errors": e.fields})
        except sqlite3.IntegrityError:
            self.send_json(409, {"errors": {"_form": "Registro duplicado o relación no válida."}})
        except (ValueError, TypeError):
            self.send_json(400, {"errors": {"_form": "Los datos enviados no son válidos."}})
        except Exception:
            team.log.exception("Error interno en %s %s", self.command, urlparse(self.path).path)
            self.send_json(
                500,
                {"errors": {"_form": "No se pudo guardar. Tus datos permanecen en el formulario."}},
            )
