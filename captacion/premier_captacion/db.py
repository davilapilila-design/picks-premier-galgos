"""
Base de datos local (SQLite) del sistema de captación.

Es la memoria con la que el bot decide (p. ej. "¿esta persona ya recibió
la bienvenida?"), así que vive en la propia VM y no depende de que Google
responda. El Google Sheet de la fase 2 es una copia para consultar y
sacar estadísticas, alimentada desde aquí.

Dos tablas principales:
- `usuarios`: una fila por persona (user_id de Telegram, que no cambia
  aunque cambie el nombre o el @), con su estado actual.
- `eventos`: todo lo que pasa, en orden (solicitud, bienvenida enviada o
  fallida, aceptación, mensaje al bot...). Las estadísticas salen de aquí.

Todas las horas se guardan como segundos desde 1970 (UTC); la conversión a
hora de España se hace al mostrarlas.

El esquema se versiona con `PRAGMA user_version`: para cambiarlo se añade
una migración nueva al final de MIGRACIONES, nunca se edita una existente.
"""
import json
import sqlite3
import time

MIGRACIONES = [
    # 1 (fase 1)
    """
    CREATE TABLE usuarios (
        user_id INTEGER PRIMARY KEY,
        nombre TEXT,
        username TEXT,
        idioma TEXT,
        primera_solicitud_ts INTEGER,
        ultima_solicitud_ts INTEGER,
        num_solicitudes INTEGER NOT NULL DEFAULT 0,
        enlace_entrada TEXT,
        bienvenida_tipo TEXT,
        bienvenida_ts INTEGER,
        ultima_redireccion_ts INTEGER,
        creado_ts INTEGER NOT NULL,
        actualizado_ts INTEGER NOT NULL
    );
    CREATE TABLE eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER NOT NULL,
        user_id INTEGER,
        tipo TEXT NOT NULL,
        detalle TEXT
    );
    CREATE INDEX eventos_ts ON eventos (ts);
    CREATE INDEX eventos_usuario ON eventos (user_id);
    CREATE TABLE estado (
        clave TEXT PRIMARY KEY,
        valor TEXT
    );
    """,
    # 2 (fase 3: programa de carpetas, que lee la cuenta del dueño)
    """
    ALTER TABLE usuarios ADD COLUMN primer_mensaje_ts INTEGER;
    ALTER TABLE usuarios ADD COLUMN ultimo_mensaje_ts INTEGER;
    ALTER TABLE usuarios ADD COLUMN ultimo_msg_id INTEGER;
    ALTER TABLE usuarios ADD COLUMN boton TEXT;
    ALTER TABLE usuarios ADD COLUMN enlace_venta_ts INTEGER;
    ALTER TABLE usuarios ADD COLUMN enlace_venta TEXT;
    ALTER TABLE usuarios ADD COLUMN canal_venta TEXT;
    ALTER TABLE usuarios ADD COLUMN carpeta TEXT;
    CREATE TABLE enlaces (
        hash TEXT PRIMARY KEY,
        chat_id INTEGER,
        titulo TEXT,
        comprobado_ts INTEGER NOT NULL
    );
    """,
    # 3 (textos que el dueño cambia desde el bot con /textos; ver textos.py)
    """
    CREATE TABLE textos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        clave TEXT NOT NULL,
        texto TEXT NOT NULL,
        tipo_mensaje TEXT,
        creado_ts INTEGER NOT NULL
    );
    CREATE INDEX textos_clave ON textos (clave, id);
    """,
    # 4 (quien ya estaba en el canal o vuelve a entrar recibe la bienvenida
    # sin la gratuita; pedido por el dueño el 2026-10-23)
    """
    CREATE TABLE miembros_canal (
        user_id INTEGER PRIMARY KEY,
        visto_ts INTEGER NOT NULL
    );
    ALTER TABLE usuarios ADD COLUMN recurrente_ts INTEGER;
    """,
    # 5 (quién entra y sale de los canales de venta; pedido por el dueño el
    # 2026-10-28; ver ventas.py)
    """
    CREATE TABLE ventas_canales (
        canal_id INTEGER PRIMARY KEY,
        titulo TEXT,
        leido_ts INTEGER
    );
    CREATE TABLE ventas_personas (
        user_id INTEGER PRIMARY KEY,
        nombre TEXT,
        username TEXT
    );
    CREATE TABLE ventas_miembros (
        canal_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        desde_ts INTEGER,
        visto_ts INTEGER NOT NULL,
        PRIMARY KEY (canal_id, user_id)
    );
    CREATE TABLE ventas_movimientos (
        canal_id INTEGER NOT NULL,
        log_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        tipo TEXT NOT NULL,
        ts INTEGER NOT NULL,
        enlace TEXT,
        PRIMARY KEY (canal_id, log_id)
    );
    CREATE INDEX ventas_movimientos_usuario ON ventas_movimientos (user_id);
    """,
    # 6 (administradores de los canales de venta: se marcan como del equipo)
    """
    ALTER TABLE ventas_personas ADD COLUMN admin INTEGER;
    """,
]


def abrir(ruta):
    # Si varios procesos crean/migran la base a la vez, el paso a WAL puede
    # dar "database is locked" sin esperar al busy_timeout: se reintenta.
    for intento in range(30):
        con = sqlite3.connect(ruta, timeout=10)
        try:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA busy_timeout=10000")
            con.execute("PRAGMA journal_mode=WAL")
            _migrar(con)
            return con
        except sqlite3.OperationalError as e:
            con.close()
            if "locked" not in str(e) or intento == 29:
                raise
            time.sleep(0.02 * (intento + 1))


def _migrar(con):
    objetivo = len(MIGRACIONES)
    if con.execute("PRAGMA user_version").fetchone()[0] >= objetivo:
        return
    # Varios procesos (bot, resúmenes, Sheet, lector) abren la misma base de
    # datos: BEGIN IMMEDIATE hace que solo uno migre y el resto espere y
    # vuelva a mirar la versión, en vez de intentar repetir los ALTER.
    nivel = con.isolation_level
    con.isolation_level = None
    try:
        con.execute("BEGIN IMMEDIATE")
        try:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            for numero in range(version + 1, objetivo + 1):
                for sentencia in MIGRACIONES[numero - 1].split(";"):
                    if sentencia.strip():
                        con.execute(sentencia)
            con.execute(f"PRAGMA user_version = {max(version, objetivo)}")
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    finally:
        con.isolation_level = nivel


def nombre_completo(usuario):
    partes = (usuario.get("first_name"), usuario.get("last_name"))
    return " ".join(p for p in partes if p) or None


def actualizar_datos_usuario(con, ts, usuario):
    """Crea la fila de la persona o refresca su nombre/@ (pueden cambiar)."""
    con.execute(
        """
        INSERT INTO usuarios (user_id, nombre, username, idioma, creado_ts, actualizado_ts)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (user_id) DO UPDATE SET
            nombre = excluded.nombre,
            username = excluded.username,
            idioma = COALESCE(excluded.idioma, usuarios.idioma),
            actualizado_ts = excluded.actualizado_ts
        """,
        (
            usuario["id"],
            nombre_completo(usuario),
            usuario.get("username"),
            usuario.get("language_code"),
            int(ts),
            int(ts),
        ),
    )


def registrar_solicitud(con, ts, usuario, enlace):
    actualizar_datos_usuario(con, ts, usuario)
    con.execute(
        """
        UPDATE usuarios SET
            primera_solicitud_ts = COALESCE(primera_solicitud_ts, ?),
            ultima_solicitud_ts = ?,
            num_solicitudes = num_solicitudes + 1,
            enlace_entrada = COALESCE(enlace_entrada, ?)
        WHERE user_id = ?
        """,
        (int(ts), int(ts), enlace, usuario["id"]),
    )


def marcar_bienvenida(con, user_id, ts, tipo):
    con.execute(
        "UPDATE usuarios SET bienvenida_tipo = ?, bienvenida_ts = ?, actualizado_ts = ? WHERE user_id = ?",
        (tipo, int(ts), int(ts), user_id),
    )


def marcar_redireccion(con, user_id, ts):
    con.execute(
        "UPDATE usuarios SET ultima_redireccion_ts = ?, actualizado_ts = ? WHERE user_id = ?",
        (int(ts), int(ts), user_id),
    )


def obtener_usuario(con, user_id):
    return con.execute("SELECT * FROM usuarios WHERE user_id = ?", (user_id,)).fetchone()


def es_del_embudo(fila):
    """¿Recibió alguna bienvenida (del bot o, con la fase 4, manual)?"""
    return fila is not None and fila["bienvenida_ts"] is not None


def guardar_miembros(con, user_ids, ts):
    """Apunta a quien está en el canal principal (lista leída por el lector).
    Solo se guarda el id: basta para no ofrecerles la gratuita."""
    con.executemany("INSERT OR IGNORE INTO miembros_canal (user_id, visto_ts) VALUES (?, ?)",
                    [(uid, int(ts)) for uid in user_ids])


def es_miembro(con, user_id):
    return con.execute("SELECT 1 FROM miembros_canal WHERE user_id = ?", (user_id,)).fetchone() is not None


def ya_conocido(con, user_id, fila):
    """¿Estaba ya en el canal o pasó antes por aquí? Entonces, si vuelve a
    pedir entrar, recibe la bienvenida sin la gratuita."""
    if fila is not None and any(fila[c] is not None for c in ("bienvenida_ts", "enlace_venta_ts", "recurrente_ts")):
        return True
    return es_miembro(con, user_id)


def estado_oferta(con, user_id, fila):
    """Qué se le ofrece cuando escribe al bot o mira las dudas:
    "nueva" (aún puede pedir la gratuita), "gratuita" (ya la tiene) o
    "recurrente" (ya estaba en el canal o volvió a entrar: sin gratuita, y con
    un texto ya escrito distinto para que el dueño lo reconozca)."""
    if fila is not None and fila["enlace_venta_ts"] is not None:
        return "gratuita"
    if fila is not None and fila["recurrente_ts"] is not None:
        return "recurrente"
    # En la lista del canal pero con la bienvenida normal del bot: entró como
    # cliente nuevo (la lista se leyó después), así que sigue siendo nueva.
    nueva_del_bot = fila is not None and (fila["bienvenida_tipo"] or "").startswith("bot_b")
    if es_miembro(con, user_id) and not nueva_del_bot:
        return "recurrente"
    return "nueva"


def actualizar_campos(con, user_id, ts, **campos):
    """UPDATE de las columnas dadas (nombres fijos del código, nunca del usuario)."""
    if not campos:
        return
    asignaciones = ", ".join(f"{columna} = ?" for columna in campos)
    con.execute(
        f"UPDATE usuarios SET {asignaciones}, actualizado_ts = ? WHERE user_id = ?",
        (*campos.values(), int(ts), user_id),
    )


def enlace_guardado(con, hash_enlace):
    return con.execute("SELECT * FROM enlaces WHERE hash = ?", (hash_enlace,)).fetchone()


def guardar_enlace(con, hash_enlace, chat_id, titulo, ts):
    con.execute(
        "INSERT INTO enlaces (hash, chat_id, titulo, comprobado_ts) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (hash) DO UPDATE SET chat_id = excluded.chat_id, titulo = excluded.titulo, "
        "comprobado_ts = excluded.comprobado_ts",
        (hash_enlace, chat_id, titulo, int(ts)),
    )


def registrar_evento(con, ts, tipo, user_id=None, **detalle):
    con.execute(
        "INSERT INTO eventos (ts, user_id, tipo, detalle) VALUES (?, ?, ?, ?)",
        (
            int(ts),
            user_id,
            tipo,
            json.dumps(detalle, ensure_ascii=False, sort_keys=True) if detalle else None,
        ),
    )


def existe_evento(con, user_id, tipo, ts):
    return con.execute(
        "SELECT 1 FROM eventos WHERE user_id = ? AND tipo = ? AND ts = ? LIMIT 1", (user_id, tipo, int(ts))
    ).fetchone() is not None


def eventos_entre(con, desde_ts, hasta_ts):
    """Eventos con desde_ts <= ts < hasta_ts, con `detalle` ya como dict."""
    filas = con.execute(
        "SELECT id, ts, user_id, tipo, detalle FROM eventos WHERE ts >= ? AND ts < ? ORDER BY id",
        (int(desde_ts), int(hasta_ts)),
    ).fetchall()
    return [
        {
            "id": f["id"],
            "ts": f["ts"],
            "user_id": f["user_id"],
            "tipo": f["tipo"],
            "detalle": json.loads(f["detalle"]) if f["detalle"] else {},
        }
        for f in filas
    ]


def leer_estado(con, clave, defecto=None):
    fila = con.execute("SELECT valor FROM estado WHERE clave = ?", (clave,)).fetchone()
    return fila["valor"] if fila else defecto


def pausa_desde(con):
    """Desde cuándo está el bot en pausa (el dueño escribió /pausar), o None."""
    valor = leer_estado(con, "pausa_desde")
    return int(float(valor)) if valor else None


def guardar_estado(con, clave, valor):
    con.execute(
        "INSERT INTO estado (clave, valor) VALUES (?, ?) "
        "ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
        (clave, str(valor)),
    )
