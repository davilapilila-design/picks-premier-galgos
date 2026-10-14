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
]


def abrir(ruta):
    con = sqlite3.connect(ruta, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=10000")
    _migrar(con)
    return con


def _migrar(con):
    version = con.execute("PRAGMA user_version").fetchone()[0]
    for numero in range(version + 1, len(MIGRACIONES) + 1):
        con.executescript(
            "BEGIN;\n"
            f"{MIGRACIONES[numero - 1]}\n"
            f"PRAGMA user_version = {numero};\n"
            "COMMIT;"
        )


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


def guardar_estado(con, clave, valor):
    con.execute(
        "INSERT INTO estado (clave, valor) VALUES (?, ?) "
        "ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
        (clave, str(valor)),
    )
