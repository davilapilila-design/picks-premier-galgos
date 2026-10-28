"""
Quién entra y sale de los canales de venta (carpeta «CH Venta»). Solo lectura.

Pedido por el dueño el 2026-10-28, para saber a cuántos canales de venta ha
entrado cada persona. El enlace de un canal de venta es el mismo para la
venta (payoption lo manda por correo al pagar), la gratuita y las
compensaciones, así que Telegram no dice quién pagó: como la gratuita de
cada uno ya está apuntada, el resto de canales son compras o
compensaciones (y se podrá cruzar con las ventas de payoption).

Dos fuentes:
- La lista de miembros de cada canal, con la fecha en que entró cada uno
  (solo de quien sigue dentro).
- El registro de acciones del canal (entradas y salidas, también de quien ya
  salió), que Telegram guarda solo 48 horas: el lector lo lee cada pocas
  horas y lo va guardando (ver registro_periodico).

Modo a mano: `lector.sh real ventas [enlace del Sheet]` lee todo una vez y lo
deja en las pestañas «Canales de venta · …» del Sheet. Después, la copia
periódica al Sheet (sheet.py) las mantiene al día.
"""
import asyncio
import logging
import os
import time
from datetime import datetime

from . import analisis, carpetas, db, sheet

log = logging.getLogger("captacion.ventas")

REGISTRO_CADA_S = 4 * 3600  # el registro de Telegram dura 48 h: sobra margen
ESPERA_MAXIMA_S = 30 * 60
_BUSQUEDAS = "abcdefghijklmnopqrstuvwxyz0123456789"

TAB_PERSONAS = "Canales de venta · Personas"
TAB_MOVIMIENTOS = "Canales de venta · Entradas y salidas"
CABECERA_PERSONAS = ["Equipo", "Nombre", "Usuario", "User ID", "Canales de venta (entró)", "Sigue dentro en",
                     "Canales", "Canal de su gratuita", "Otros canales (compras o compensaciones)",
                     "Nº otros canales"]
CABECERA_MOVIMIENTOS = ["Fecha y hora", "Canal", "Equipo", "Nombre", "Usuario", "User ID", "Movimiento", "Enlace usado"]


# --- Base de datos -------------------------------------------------------------

def guardar_canal(con, canal_id, titulo, ts):
    con.execute("INSERT INTO ventas_canales (canal_id, titulo, leido_ts) VALUES (?, ?, ?) "
                "ON CONFLICT (canal_id) DO UPDATE SET titulo = excluded.titulo, leido_ts = excluded.leido_ts",
                (canal_id, titulo, int(ts)))


def guardar_persona(con, user_id, nombre, username):
    con.execute("INSERT INTO ventas_personas (user_id, nombre, username) VALUES (?, ?, ?) "
                "ON CONFLICT (user_id) DO UPDATE SET nombre = COALESCE(excluded.nombre, nombre), "
                "username = COALESCE(excluded.username, username)", (user_id, nombre, username))


def guardar_miembros(con, canal_id, miembros, ts):
    """miembros: [(user_id, desde_ts o None)] de quien está ahora dentro."""
    con.executemany(
        "INSERT INTO ventas_miembros (canal_id, user_id, desde_ts, visto_ts) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (canal_id, user_id) DO UPDATE SET desde_ts = COALESCE(excluded.desde_ts, desde_ts), "
        "visto_ts = excluded.visto_ts",
        [(canal_id, uid, None if desde is None else int(desde), int(ts)) for uid, desde in miembros])


def guardar_movimientos(con, canal_id, movimientos):
    """movimientos: [(log_id, user_id, "entra"/"sale", ts, enlace o None)]. Devuelve los nuevos."""
    antes = con.total_changes
    con.executemany(
        "INSERT OR IGNORE INTO ventas_movimientos (canal_id, log_id, user_id, tipo, ts, enlace) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(canal_id, log_id, uid, tipo, int(ts), enlace) for log_id, uid, tipo, ts, enlace in movimientos])
    return con.total_changes - antes


# --- Telegram -----------------------------------------------------------------------

async def canales(client, cfg):
    """Los canales de venta desde «Premier Galgos Debut» (22/07): los de antes
    no interesan (2026-10-28, el dueño). Cada vez se vuelve a mirar la
    carpeta, así que los canales nuevos entran solos."""
    todos, _ = await analisis.canales_de_venta(client, cfg)
    desde = datetime.combine(analisis.DESDE, datetime.min.time(), tzinfo=cfg.tz).timestamp()
    return [c for c in todos
            if (getattr(c, "date", None) is None or c.date.timestamp() >= desde)
            and "prueba" not in carpetas.normalizar(c.title)]  # el canal de pruebas del bot


def _nombre(u):
    return " ".join(x for x in (getattr(u, "first_name", None), getattr(u, "last_name", None)) if x) or None


async def leer_miembros(client, canal):
    """[(usuario, desde_ts)] de quien está ahora en el canal. Telegram da como
    mucho unos 200 de una vez: si hay más, se completa con búsquedas."""
    vistos = {}

    async def leer(**kw):
        async for u in client.iter_participants(canal, **kw):
            # Fuera bots y cuentas borradas. Los administradores se quedan,
            # marcados como del equipo en el Sheet.
            if not getattr(u, "bot", False) and not getattr(u, "deleted", False):
                fecha = getattr(getattr(u, "participant", None), "date", None)
                vistos[u.id] = (u, fecha.timestamp() if fecha else None)

    await leer()
    if len(vistos) >= 190:
        for letra in _BUSQUEDAS:
            await leer(search=letra)
    return list(vistos.values())


def _movimiento(accion):
    nombre = type(accion).__name__
    if "ParticipantJoin" in nombre or "ParticipantInvite" in nombre:
        return "entra"
    if "ParticipantLeave" in nombre:
        return "sale"
    return None


async def leer_registro(client, canal):
    """[(log_id, usuario o None, user_id, tipo, ts, enlace)] de las entradas y
    salidas de las últimas 48 h, o None si no se puede (grupo básico, o la
    cuenta no es administradora)."""
    from telethon import errors
    from telethon.tl import types

    if not isinstance(canal, types.Channel):
        return None
    movimientos = []
    try:
        async for ev in client.iter_admin_log(canal, join=True, leave=True, invite=True):
            tipo = _movimiento(ev.action)
            if tipo is None:
                continue
            invitacion = getattr(ev.action, "invite", None)
            uid, usuario = ev.user_id, getattr(ev, "user", None)
            invitado = getattr(getattr(ev.action, "participant", None), "user_id", None)
            if "ParticipantInvite" in type(ev.action).__name__ and invitado:
                # Lo metió un administrador: ev.user_id es quien lo metió.
                uid, usuario = invitado, (getattr(ev, "entities", None) or {}).get(invitado)
            movimientos.append((ev.id, usuario, uid, tipo, ev.date.timestamp(), getattr(invitacion, "link", None)))
    except (errors.ChatAdminRequiredError, errors.ChannelPrivateError):
        return None
    return movimientos


async def leer_canal(client, con, canal, con_miembros):
    ahora = time.time()
    miembros = await leer_miembros(client, canal) if con_miembros else []
    registro = await leer_registro(client, canal)
    with con:
        guardar_canal(con, canal.id, canal.title, ahora)
        for u, _ in miembros:
            guardar_persona(con, u.id, _nombre(u), getattr(u, "username", None))
            tipo = type(getattr(u, "participant", None)).__name__
            if "Admin" in tipo or "Creator" in tipo:
                con.execute("UPDATE ventas_personas SET admin = 1 WHERE user_id = ?", (u.id,))
        if con_miembros:
            # La lista es una foto de quién está ahora: la anterior se cambia
            # entera (quien salió sigue en los movimientos).
            con.execute("DELETE FROM ventas_miembros WHERE canal_id = ?", (canal.id,))
            guardar_miembros(con, canal.id, [(u.id, desde) for u, desde in miembros], ahora)
        nuevos = 0
        if registro:
            for _, u, uid, *_ in registro:
                if u is not None:
                    guardar_persona(con, uid, _nombre(u), getattr(u, "username", None))
            nuevos = guardar_movimientos(con, canal.id, [(lid, uid, tipo, ts, enlace)
                                                         for lid, _, uid, tipo, ts, enlace in registro])
    return len(miembros), registro, nuevos


async def ejecutar(cfg, entorno, sheet_id, crear_cliente, credenciales_api):
    """Modo a mano «ventas»: miembros y registro de todos los canales de venta,
    y las pestañas del Sheet."""
    api_id, api_hash, sesion = credenciales_api(entorno)
    libro = None
    if sheet_id:
        credencial = sheet.ruta_credencial()
        if credencial is None:
            log.error("No encuentro la credencial de Google")
            return 2
        libro = sheet.abrir_libro(credencial, sheet_id)  # antes de leer: si falla el acceso, se ve ya
        libro.preparar()
    client = crear_cliente(sesion, api_id, api_hash, "ventas")
    client.flood_sleep_threshold = ESPERA_MAXIMA_S
    con = db.abrir(cfg.db_path)
    inicio = time.time()
    sin_registro = 0
    await client.connect()
    try:
        if not await client.is_user_authorized():
            log.error("La cuenta no está conectada: el dueño tiene que ejecutar conectar-cuenta.sh")
            return 2
        lista = await canales(client, cfg)
        with con:  # los que ya no cuentan (anteriores al debut, el de pruebas)
            ids = ",".join(str(c.id) for c in lista) or "0"
            for tabla in ("ventas_miembros", "ventas_movimientos", "ventas_canales"):
                con.execute(f"DELETE FROM {tabla} WHERE canal_id NOT IN ({ids})")
        for canal in lista:
            n, registro, nuevos = await leer_canal(client, con, canal, con_miembros=True)
            sin_registro += registro is None
            log.info("Canal «%s»: %s dentro, %s", canal.title, n,
                     "sin registro (no eres admin o es un grupo básico)" if registro is None
                     else f"{len(registro)} entradas/salidas en 48 h")
            await asyncio.sleep(0.3)
        if libro is not None:
            escribir_pestanas(con, cfg.tz, libro)
        personas = con.execute("SELECT COUNT(DISTINCT user_id) FROM ventas_miembros").fetchone()[0]
    finally:
        await client.disconnect()
        con.close()
    print(f"✓ Canales de venta leídos en {int(time.time() - inicio) // 60} min: {len(lista)} canales, "
          f"{personas} personas dentro de alguno"
          + (f"; en {sin_registro} no se pudo leer el registro de entradas y salidas" if sin_registro else "")
          + (". Está en las pestañas «Canales de venta · …» del Sheet." if libro is not None else "."))
    return 0


async def registro_periodico(client, con, cfg, cada=REGISTRO_CADA_S):
    """Dentro del lector: guarda cada pocas horas las entradas y salidas de
    los canales de venta, antes de que Telegram las borre (48 h)."""
    await asyncio.sleep(300)  # que el lector arranque tranquilo
    while True:
        try:
            lista = await canales(client, cfg)
            total = 0
            for canal in lista:
                _, _, nuevos = await leer_canal(client, con, canal, con_miembros=False)
                total += nuevos
                await asyncio.sleep(1)
            log.info("Registro de los canales de venta: %s movimientos nuevos", total)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Error leyendo el registro de los canales de venta")
        await asyncio.sleep(cada)


# --- Sheet ------------------------------------------------------------------------------

def _dia(ts, tz):
    return datetime.fromtimestamp(ts, tz).strftime("%d/%m")


def equipo(entorno=None):
    """@usuarios o ids del equipo (CAPTACION_EQUIPO, separados por comas):
    están en los canales pero no son clientes; en el Sheet salen marcados.
    Se guardan en la configuración de la VM, no aquí (el repositorio es
    público). Los administradores de los canales también cuentan como equipo."""
    valor = (entorno if entorno is not None else os.environ).get("CAPTACION_EQUIPO", "")
    return {x.strip().lstrip("@").lower() for x in valor.split(",") if x.strip()}


def _es_equipo(uid, username, admin, del_equipo):
    return bool(admin) or str(uid) in del_equipo or bool(username and username.lower() in del_equipo)


def filas_personas(con, tz, del_equipo=None):
    del_equipo = equipo() if del_equipo is None else del_equipo
    canales = {f["canal_id"]: f["titulo"] for f in con.execute("SELECT canal_id, titulo FROM ventas_canales")}
    por_persona = {}  # user_id -> {canal_id: {"entra": ts, "dentro": bool, "sale": ts}}

    def dato(uid, cid):
        return por_persona.setdefault(uid, {}).setdefault(cid, {"entra": None, "dentro": False, "sale": None})

    for f in con.execute("SELECT canal_id, user_id, desde_ts FROM ventas_miembros"):
        d = dato(f["user_id"], f["canal_id"])
        d["dentro"] = True
        d["entra"] = f["desde_ts"]
    for f in con.execute("SELECT canal_id, user_id, tipo, ts FROM ventas_movimientos ORDER BY ts"):
        d = dato(f["user_id"], f["canal_id"])
        if f["tipo"] == "entra":
            d["entra"] = d["entra"] or f["ts"]
        else:
            d["sale"] = f["ts"]
    filas = []
    for uid, por_canal in por_persona.items():
        persona = con.execute("SELECT nombre, username, admin FROM ventas_personas WHERE user_id = ?",
                              (uid,)).fetchone()
        usuario = db.obtener_usuario(con, uid)
        nombre = (persona and persona["nombre"]) or (usuario and usuario["nombre"]) or ""
        username = (persona and persona["username"]) or (usuario and usuario["username"]) or ""
        es_equipo = _es_equipo(uid, username, persona and persona["admin"], del_equipo)
        gratuita = (usuario["canal_venta"] if usuario is not None and usuario["enlace_venta_ts"] is not None
                    else None)
        orden = sorted(por_canal.items(), key=lambda kv: kv[1]["entra"] or 0)
        textos, otros = [], []
        for cid, d in orden:
            titulo = canales.get(cid, str(cid))
            texto = titulo + (f" (entró {_dia(d['entra'], tz)})" if d["entra"] else "")
            if not d["dentro"] and d["sale"]:
                texto += f" (salió {_dia(d['sale'], tz)})"
            textos.append(texto)
            if titulo != gratuita:
                otros.append(titulo)
        filas.append(["Equipo" if es_equipo else "", nombre, f"@{username}" if username else "", uid, len(por_canal),
                      sum(d["dentro"] for d in por_canal.values()), " · ".join(textos), gratuita or "",
                      " · ".join(otros), len(otros)])
    # Primero los clientes con más canales aparte de su gratuita; el equipo, al final.
    filas.sort(key=lambda f: (f[0] != "", -f[9], -f[4], f[1].lower()))
    return filas


def filas_movimientos(con, tz, del_equipo=None):
    del_equipo = equipo() if del_equipo is None else del_equipo
    filas = []
    for f in con.execute(
            "SELECT m.ts, m.user_id, m.tipo, m.enlace, c.titulo, p.nombre, p.username, p.admin FROM ventas_movimientos m "
            "LEFT JOIN ventas_canales c USING (canal_id) LEFT JOIN ventas_personas p USING (user_id) "
            "ORDER BY m.ts DESC"):
        es_equipo = _es_equipo(f["user_id"], f["username"], f["admin"], del_equipo)
        filas.append([sheet.serie_fecha_hora(f["ts"], tz), f["titulo"] or "", "Equipo" if es_equipo else "",
                      f["nombre"] or "",
                      f"@{f['username']}" if f["username"] else "", f["user_id"],
                      "Entra" if f["tipo"] == "entra" else "Sale", f["enlace"] or ""])
    return filas


def hay_datos(con):
    return con.execute("SELECT 1 FROM ventas_canales LIMIT 1").fetchone() is not None


def escribir_pestanas(con, tz, libro):
    p = libro.pestana(TAB_PERSONAS, [CABECERA_PERSONAS])
    p.reemplazar(filas_personas(con, tz), desde_fila=2)
    p = libro.pestana(TAB_MOVIMIENTOS, [CABECERA_MOVIMIENTOS])
    p.reemplazar(filas_movimientos(con, tz), desde_fila=2)
    p.formatear([("A2:A", sheet.FORMATO_FECHA_HORA)])
