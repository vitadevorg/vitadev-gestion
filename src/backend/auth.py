"""Identidad, sesiones y políticas compartidas. Sin registro público ni cuentas automáticas."""

import hashlib, hmac, secrets, time, json, re, os, io, sqlite3, threading
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlparse
import team_server as team
from identity import principal

POLICY = json.loads(
    (Path(__file__).resolve().parents[1] / "access-policy.json").read_text(encoding="utf-8")
)
PROFILES = POLICY["profiles"]
COOKIE = "nexo_session"
HASH_LIMIT = threading.BoundedSemaphore(2)
GENERIC = "El correo o la contraseña ingresados no son correctos."


# Desactiva la autorización: solo válido dentro de una suite (tests/_isolation.py fija NEXO_TEST_SUITE).
def test_mode():
    return os.environ.get("NEXO_TEST_MODE") == "1" and os.environ.get("NEXO_TEST_SUITE") == "1"


def init():
    if team.pg.enabled():
        global POLICY, PROFILES
        team.pg.ensure_ready()
        from postgres_repository import PostgresRepository

        with team.connect() as c:
            POLICY = PostgresRepository(
                c.raw, os.environ.get("VITADEV_DB_SCHEMA", "vitadev")
            ).access_policy()
        PROFILES = POLICY["profiles"]
        return
    with team.connect() as c:
        columns = {r[1] for r in c.execute("PRAGMA table_info(users)")}
        for key, definition in [
            ("passwordHash", "TEXT"),
            ("permissionProfile", "TEXT NOT NULL DEFAULT 'EMPLOYEE'"),
            ("lastLoginAt", "TEXT"),
            ("createdAt", "TEXT"),
            ("updatedAt", "TEXT"),
        ]:
            if key not in columns:
                c.execute(f"ALTER TABLE users ADD COLUMN {key} {definition}")
        c.executescript(
            "CREATE UNIQUE INDEX IF NOT EXISTS user_employee ON users(employeeId) WHERE employeeId IS NOT NULL; CREATE TABLE IF NOT EXISTS sessions(tokenHash TEXT PRIMARY KEY,userId INTEGER NOT NULL REFERENCES users(id),csrf TEXT NOT NULL,expiresAt REAL NOT NULL,lastSeen REAL NOT NULL,idleSeconds INTEGER NOT NULL); CREATE TABLE IF NOT EXISTS login_attempts(key TEXT PRIMARY KEY,count INTEGER NOT NULL,expiresAt REAL NOT NULL); CREATE TABLE IF NOT EXISTS user_audit(id INTEGER PRIMARY KEY,actorUserId INTEGER,actorEmployeeId INTEGER,action TEXT NOT NULL,entityType TEXT NOT NULL,entityId INTEGER,timestamp TEXT NOT NULL,metadata TEXT NOT NULL);"
        )


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    with HASH_LIMIT:
        result = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt),
            n=131072,
            r=8,
            p=1,
            maxmem=268435456,
            dklen=32,
        )
    return "scrypt$131072$8$1$" + salt + "$" + result.hex()


def verify(password, encoded):
    try:
        if not encoded or not encoded.startswith("scrypt$131072$8$1$"):
            encoded = "scrypt$131072$8$1$" + "0" * 32 + "$" + "0" * 64
        return hmac.compare_digest(password_hash(password, encoded.split("$")[4]), encoded)
    except (ValueError, TypeError):
        return False


def public(row, connection=None, employees=None):
    """employees: filas de empleados por id ya leídas, para listar cuentas sin una consulta por cuenta."""
    d = {
        k: row[k]
        for k in [
            "id",
            "email",
            "role",
            "status",
            "employeeId",
            "permissionProfile",
            "lastLoginAt",
            "createdAt",
            "updatedAt",
        ]
    }
    d["userId"] = d["id"]
    d["permissions"] = PROFILES.get(d["permissionProfile"], [])
    d["employee"] = None
    if d["employeeId"]:
        if employees is not None:
            e = employees.get(d["employeeId"])
        elif connection is not None:
            e = connection.execute(
                "SELECT * FROM employees WHERE id=?", (d["employeeId"],)
            ).fetchone()
        else:
            with team.connect() as c:
                e = c.execute("SELECT * FROM employees WHERE id=?", (d["employeeId"],)).fetchone()
        if e:
            e = team.unpack(e)
            d["employee"] = {
                k: e.get(k)
                for k in [
                    "id",
                    "name",
                    "firstName",
                    "lastName",
                    "photo",
                    "area",
                    "role",
                    "laborStatus",
                ]
            }
    return d


def audit(c, action, id, metadata=None):
    actor = principal.get() or {}
    c.execute(
        "INSERT INTO user_audit(actorUserId,actorEmployeeId,action,entityType,entityId,timestamp,metadata) VALUES(?,?,?,?,?,?,?)",
        (
            actor.get("id"),
            actor.get("employeeId"),
            action,
            "user",
            id,
            team.now(),
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )


def save_user(data, id=None):
    errors = {}
    email = str(data.get("email", "")).strip().lower()
    role = data.get("role")
    profile = data.get("permissionProfile")
    status = data.get("status", "ACTIVE")
    employee = data.get("employeeId")
    password = data.get("password", "")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 180:
        errors["email"] = "Ingresá un correo válido."
    if role not in ["ADMIN", "EMPLOYEE"]:
        errors["role"] = "Seleccioná un rol válido."
    if profile not in PROFILES or (role == "ADMIN") != (profile == "ADMINISTRATOR"):
        errors["permissionProfile"] = "El perfil no corresponde al rol elegido."
    if status not in ["ACTIVE", "DISABLED"]:
        errors["status"] = "Seleccioná un estado válido."
    if not isinstance(password, str) or ((not id or password) and not 12 <= len(password) <= 128):
        errors["password"] = "Usá una contraseña de 12 a 128 caracteres."
    if employee is not None and (not isinstance(employee, int) or isinstance(employee, bool)):
        errors["employeeId"] = "Seleccioná un empleado válido."
    if role == "EMPLOYEE" and employee is None:
        errors["employeeId"] = "Un usuario empleado debe estar vinculado a Equipo."
    if errors:
        raise team.Validation(errors)
    encoded = password_hash(password) if password else None
    with team.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        old = c.execute("SELECT * FROM users WHERE id=?", (id,)).fetchone() if id else None
        if id and not old:
            raise team.Validation({"_form": "Usuario no encontrado."}, 404)
        if c.execute("SELECT id FROM users WHERE email=? AND id<>?", (email, id or 0)).fetchone():
            errors["email"] = "Ya existe un usuario con este correo."
        if employee:
            e = c.execute("SELECT * FROM employees WHERE id=?", (employee,)).fetchone()
            if not e:
                errors["employeeId"] = "El empleado no existe."
            elif status == "ACTIVE" and team.unpack(e)["laborStatus"] != team.LABOR.ACTIVE:
                errors["status"] = "El empleado debe estar activo para habilitar el acceso."
            if c.execute(
                "SELECT id FROM users WHERE employeeId=? AND id<>?", (employee, id or 0)
            ).fetchone():
                errors["employeeId"] = "El empleado ya tiene una cuenta. Gestioná ese acceso."
        if (
            old
            and old["role"] == "ADMIN"
            and old["status"] == "ACTIVE"
            and (status != "ACTIVE" or role != "ADMIN")
        ):
            if not team.pg.other_active_admin(c, id):
                errors["status"] = "Debe permanecer al menos un administrador activo."
        if errors:
            raise team.Validation(errors)
        stamp = team.now()
        if old:
            c.execute(
                "UPDATE users SET email=?,role=?,status=?,employeeId=?,permissions=?,permissionProfile=?,passwordHash=?,updatedAt=? WHERE id=?",
                (
                    email,
                    role,
                    status,
                    employee,
                    json.dumps(PROFILES[profile]),
                    profile,
                    encoded or old["passwordHash"],
                    stamp,
                    id,
                ),
            )
            # Credenciales, identidad o permisos modificados invalidan todas las sesiones de la cuenta.
            if encoded or (
                old["email"],
                old["role"],
                old["status"],
                old["employeeId"],
                old["permissionProfile"],
            ) != (email, role, status, employee, profile):
                c.execute("DELETE FROM sessions WHERE userId=?", (id,))
            audit(
                c,
                "Acceso actualizado",
                id,
                {
                    "previousStatus": old["status"],
                    "status": status,
                    "role": role,
                    "permissionProfile": profile,
                },
            )
        else:
            id = c.execute(
                "INSERT INTO users(email,role,status,employeeId,permissions,permissionProfile,passwordHash,createdAt,updatedAt) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    email,
                    role,
                    status,
                    employee,
                    json.dumps(PROFILES[profile]),
                    profile,
                    encoded,
                    stamp,
                    stamp,
                ),
            ).lastrowid
            audit(
                c,
                "Acceso creado",
                id,
                {"employeeId": employee, "role": role, "permissionProfile": profile},
            )
        result = dict(c.execute("SELECT * FROM users WHERE id=?", (id,)).fetchone())
    forget_sessions()  # Permisos, estado o credenciales pudieron cambiar.
    return public(result)


def client_ip(handler):
    # X-Forwarded-For solo se acepta si la conexión llega desde un proxy declarado en NEXO_TRUSTED_PROXIES.
    peer = handler.client_address[0]
    trusted = {
        p.strip() for p in os.environ.get("NEXO_TRUSTED_PROXIES", "").split(",") if p.strip()
    }
    if peer in trusted:
        for hop in reversed(
            [h.strip() for h in handler.headers.get("X-Forwarded-For", "").split(",") if h.strip()]
        ):
            if hop not in trusted:
                return hop
    return peer


def cookie_header(token, remember=False):
    secure = "; Secure" if os.environ.get("NEXO_COOKIE_SECURE") == "1" else ""
    return (
        f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict"
        + ("; Max-Age=2592000" if remember else "")
        + secure
    )


# Caché de sesiones validadas: evita 3 a 5 consultas remotas por petición. Toda operación que cambia
# cuentas, empleados o sesiones llama a forget_sessions(), así la revocación sigue siendo inmediata.
SESSION_CACHE_SECONDS = 30
SESSION_TOUCH_SECONDS = 300
SESSION_CACHE = {}
SESSION_LOCK = threading.Lock()


def forget_sessions(digest=None):
    with SESSION_LOCK:
        if digest:
            SESSION_CACHE.pop(digest, None)
        else:
            SESSION_CACHE.clear()


def session(handler):
    jar = SimpleCookie()
    try:
        jar.load(handler.headers.get("Cookie", ""))
        token = jar[COOKIE].value
    except Exception:
        raise team.Validation({"_form": "Iniciá sesión para continuar."}, 401)
    digest = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    with SESSION_LOCK:
        cached = SESSION_CACHE.get(digest)
    if (
        cached
        and now - cached[0] < SESSION_CACHE_SECONDS
        and cached[1]["expiresAt"] > now
        and cached[1]["lastSeen"] + cached[1]["idleSeconds"] > now
    ):
        row, user = cached[1], {**cached[2]}
    else:
        expired = blocked = False
        with team.connect() as c:
            row = c.execute(
                "SELECT users.*,sessions.csrf,sessions.expiresAt,sessions.lastSeen,sessions.idleSeconds FROM sessions JOIN users ON users.id=sessions.userId WHERE tokenHash=?",
                (digest,),
            ).fetchone()
            if (
                not row
                or row["status"] != "ACTIVE"
                or row["expiresAt"] <= now
                or row["lastSeen"] + row["idleSeconds"] <= now
            ):
                c.execute("DELETE FROM sessions WHERE tokenHash=?", (digest,))
                expired = True
            else:
                row = dict(row)
                user = public(row, c)
                blocked = bool(user["employeeId"]) and (
                    not user["employee"] or user["employee"]["laborStatus"] != team.LABOR.ACTIVE
                )
                # Escribir en cada petición serializaba todas las cargas (bloqueo de escritura en
                # PostgreSQL). La inactividad se mide en horas: basta con registrarla cada 5 minutos.
                if not blocked and now - row["lastSeen"] > SESSION_TOUCH_SECONDS:
                    c.execute("UPDATE sessions SET lastSeen=? WHERE tokenHash=?", (now, digest))
                    row["lastSeen"] = now
        # Las excepciones van fuera del bloque: dentro, el borrado de la sesión se desharía.
        if expired:
            forget_sessions(digest)
            raise team.Validation({"_form": "La sesión venció. Volvé a ingresar."}, 401)
        if blocked:
            raise team.Validation(
                {"_form": "No podés acceder a VitaDev con esta cuenta. Contactá al administrador."},
                401,
            )
        with SESSION_LOCK:
            SESSION_CACHE[digest] = (now, row, {**user})
    user["csrfToken"] = row["csrf"]
    handler.session_hash = digest
    handler.principal = user
    principal.set(user)
    return user


def visible_requests(user, requests, tasks):
    """Solicitudes que el usuario puede ver, a partir de datos ya cargados (sin consultar la base)."""
    own = {t["ticket"] for t in tasks if t["owner"] == user["employeeId"]}
    queue = "requests.viewQueue" in user["permissions"]
    assigned = "requests.viewAssigned" in user["permissions"]
    take = "requests.take" in user["permissions"]
    return [
        r
        for r in requests
        if queue
        or (assigned and r.get("agentId") == user["employeeId"])
        or r["id"] in own
        or (take and unclaimed(r))
    ]


def scoped_requests(user, handler=None):
    # Una lectura por petición HTTP: authorize y filter_response comparten el resultado (solo se reutiliza en lecturas).
    cached = getattr(handler, "scope_cache", None)
    if cached is not None:
        return cached
    import helpdesk_server as desk

    with desk.crm.connect() as c:
        tasks = [
            {**json.loads(r["payload"]), "id": r["id"]}
            for r in c.execute("SELECT * FROM desk_tasks")
        ]
        requests = desk.all_requests(c)
    result = visible_requests(user, requests, tasks), tasks
    if handler is not None and handler.command == "GET":
        handler.scope_cache = result
    return result


def unclaimed(r):
    # Cola de Soporte: solicitudes abiertas sin agente, visibles para poder tomarlas.
    return r.get("agentId") is None and r.get("status") not in [
        team.REQUEST.RESOLVED,
        team.REQUEST.CLOSED,
    ]


def require(user, permission):
    if permission not in user["permissions"]:
        raise team.Validation({"_form": "No tenés permisos para realizar esta operación."}, 403)


def authorize(handler, write=False):
    path = urlparse(handler.path).path
    if not path.startswith("/api/"):
        return
    if test_mode():
        return
    user = session(handler)
    permissions = user["permissions"]
    if write:
        if not hmac.compare_digest(handler.headers.get("X-CSRF-Token", ""), user["csrfToken"]):
            raise team.Validation(
                {"_form": "La sesión de la página cambió. Recargá e intentá nuevamente."}, 403
            )
        n = team.content_length(handler.headers)
        if n > 15000000:
            raise team.Validation({"_form": "Solicitud demasiado grande."}, 413)
        raw = handler.rfile.read(n)
        handler.rfile = io.BytesIO(raw)
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            raise team.Validation({"_form": "Datos inválidos."}, 400)
        if not isinstance(body, dict):
            raise team.Validation({"_form": "Datos inválidos."}, 400)
    else:
        body = {}
    if path.startswith("/api/auth/"):
        return
    if path.startswith("/api/users"):
        return require(user, "users.manage" if write else "users.view")
    if path.startswith("/api/reports"):
        return require(user, "reports.view")
    if path.startswith("/api/team"):
        if write:
            require(
                user, "employees.manage"
            )  # La protección del último administrador se verifica dentro de la transacción de team_server.
            if path.endswith("/access"):
                raise team.Validation(
                    {"_form": "Gestioná la cuenta desde Usuarios y permisos."}, 409
                )
        elif "/audit" in path:
            require(user, "employees.view")
        elif "/photos/" in path:
            if "employees.view" not in permissions and path != (user.get("employee") or {}).get(
                "photo"
            ):
                raise team.Validation({"_form": "No tenés acceso a esta fotografía."}, 403)
        return
    if path.startswith("/api/crm"):
        if write:
            return require(user, "clients.manage")
        if "/files/" in path and "clients.view" not in permissions:
            requests, _ = scoped_requests(user, handler)
            ids = {r["clientId"] for r in requests}
            import crm_server as crm

            with crm.connect() as c:
                logos = {c.get("logo") for c in crm.rows(c, "clients") if c["id"] in ids}
            if path not in logos:
                raise team.Validation({"_form": "No tenés acceso a este archivo."}, 403)
        return  # Read-only, scoped response below; no contracts or commercial history without permission.
    if path.startswith("/api/absences"):
        if "leaves.manage" in permissions:
            return
        require(user, "leaves.createOwn" if write else "leaves.viewOwn")
        if path.endswith(("/approve", "/reject")):
            raise team.Validation(
                {"_form": "No tenés permisos para aprobar o rechazar licencias."}, 403
            )
        return  # leave.context enforces identity for creation, cancellation and attachments.
    if path.startswith("/api/desk"):
        if not write and "/files/" not in path:
            return  # El listado se filtra en filter_response con los datos ya leídos.
        requests, tasks = scoped_requests(user, handler)
        ids = {r["id"] for r in requests}
        if not write:
            if "/files/" in path:
                file_id = path.rsplit("/", 1)[-1]
                import helpdesk_server as desk

                with desk.crm.connect() as c:
                    comments = [dict(r) for r in c.execute("SELECT * FROM desk_comments")]
                allowed_files = {
                    f.rsplit("/", 1)[-1] for r in requests for f in r.get("attachments", [])
                } | {
                    f.rsplit("/", 1)[-1]
                    for comment in comments
                    if comment["request_id"] in ids
                    and ("requests.internalNote" in permissions or "requests.manage" in permissions)
                    for f in json.loads(comment["attachments"])
                }
                if file_id not in allowed_files:
                    raise team.Validation({"_form": "No tenés acceso a este archivo."}, 403)
            return
        if path == "/api/desk/requests":
            return require(user, "requests.manage")
        if path == "/api/desk/files":
            return require(user, "requests.internalNote")
        match = re.fullmatch(r"/api/desk/requests/(\d+)/(update|comments|tasks|task-status)", path)
        if not match:
            raise team.Validation({"_form": "Operación no permitida."}, 403)
        rid = int(match[1])
        op = match[2]
        if rid not in ids:
            raise team.Validation({"_form": "No tenés acceso a esta solicitud."}, 403)
        target = next(r for r in requests if r["id"] == rid)
        if op == "update" and "agentId" in body and "requests.manage" not in permissions:
            # Tomar: solo asignarse a sí mismo una solicitud abierta sin agente, sin otros cambios.
            require(user, "requests.take")
            if (
                set(body) - {"agentId", "version"}
                or body["agentId"] != user["employeeId"]
                or not unclaimed(target)
            ):
                raise team.Validation(
                    {"_form": "Solo podés tomar solicitudes abiertas sin asignar."}, 403
                )
            return
        involved = target.get("agentId") == user["employeeId"] or any(
            t["ticket"] == rid and t["owner"] == user["employeeId"] for t in tasks
        )
        if (
            "requests.manage" not in permissions
            and "requests.viewQueue" not in permissions
            and not involved
        ):
            raise team.Validation({"_form": "Tomá la solicitud antes de trabajar en ella."}, 403)
        if op == "task-status":
            if "requests.manage" not in permissions:
                require(user, "tasks.updateAssigned")
                if not any(
                    t["id"] == body.get("taskId")
                    and t["ticket"] == rid
                    and t["owner"] == user["employeeId"]
                    for t in tasks
                ):
                    raise team.Validation(
                        {"_form": "Solo podés modificar tus tareas asignadas."}, 403
                    )
        elif op == "comments":
            require(user, "requests.internalNote")
        elif op == "tasks":
            require(user, "requests.createTask")
        elif op == "update":
            if "agentId" in body or "priority" in body:
                require(user, "requests.manage")
            if "status" in body:
                require(user, "requests.changeStatus")
            if "requests.manage" not in permissions and not any(
                r["id"] == rid and r.get("agentId") == user["employeeId"] for r in requests
            ):
                raise team.Validation(
                    {"_form": "Solo podés actualizar las solicitudes asignadas a vos."}, 403
                )
        return
    raise team.Validation({"_form": "Operación no autorizada."}, 403)


def filter_response(handler, data):
    if test_mode() or not getattr(handler, "principal", None) or not isinstance(data, dict):
        return data
    user = handler.principal
    permissions = user["permissions"]
    path = urlparse(handler.path).path
    if path == "/api/team":
        data["accessEnforcement"] = True
        if "employees.view" not in permissions:
            data["employees"] = [e for e in data["employees"] if e["id"] == user["employeeId"]]
            data["catalog"] = {}
            data["accessRoles"] = []
    if path == "/api/absences/availability" and "leaves.manage" not in permissions:
        data["periods"] = [e for e in data["periods"] if e["employee"] == user["employeeId"]]
    if path == "/api/desk":
        tasks = data["tasks"]
        allowed = visible_requests(user, data["requests"], tasks)
        ids = {r["id"] for r in allowed}
        data["requests"] = allowed
        data["tasks"] = [
            t for t in tasks if "requests.manage" in permissions or t["owner"] == user["employeeId"]
        ]
        for key in ["events", "comments"]:
            data[key] = (
                [e for e in data[key] if e["request_id"] in ids]
                if "requests.internalNote" in permissions
                else []
            )
        file_ids = {f.rsplit("/", 1)[-1] for r in allowed for f in r.get("attachments", [])} | {
            f.rsplit("/", 1)[-1] for c in data["comments"] for f in c["attachments"]
        }
        data["files"] = [f for f in data["files"] if f["id"] in file_ids]
        data["authenticationEnforced"] = True
    if path == "/api/crm" and "clients.view" not in permissions:
        requests, _ = scoped_requests(user, handler)
        client_ids = {r["clientId"] for r in requests}
        sub_ids = {r["subscriptionId"] for r in requests}
        contact_ids = {r["contactId"] for r in requests}
        data["clients"] = [
            {k: c.get(k) for k in ["id", "name", "logo"]}
            for c in data["clients"]
            if c["id"] in client_ids
        ]
        data["contacts"] = [
            {k: c.get(k) for k in ["id", "firstName", "lastName", "position", "clientId"]}
            for c in data["contacts"]
            if c["id"] in contact_ids
        ]
        data["subscriptions"] = [
            {k: s.get(k) for k in ["id", "productId", "clientId"]}
            for s in data["subscriptions"]
            if s["id"] in sub_ids
        ]
        products = {s["productId"] for s in data["subscriptions"]}
        data["catalog"] = [
            {k: p.get(k) for k in ["id", "name"]} for p in data["catalog"] if p["id"] in products
        ]
        data["contracts"] = []
        data["activity"] = []
        data["options"] = {}
    return data
