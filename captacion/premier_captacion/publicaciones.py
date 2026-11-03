"""
Mensajes de los canales de venta y del grupo de picks, y enlaces de canales
que el dueño manda por privado (cuentas por cliente, diseño del 2026-11-01,
piezas 1 y 2). SOLO LECTURA en Telegram: leer chats y preguntar a qué canal
lleva un enlace, que ya estaban permitidos (guardia.LECTURA).

Dentro del lector, cada hora (lectura_periodica):
- De cada canal de venta (desde el 22/07), del grupo de picks y del canal
  principal, los mensajes nuevos desde el último leído: las apuestas, los
  enlaces que se publican (la compensación de un canal fallado es el enlace
  del siguiente), en el grupo de qué mensaje de canal es reenvío cada pick y,
  en el principal, los anuncios de venta (anuncios.py).
- De los chats privados con movimiento desde la última vez, los mensajes del
  dueño con un enlace de invitación (gratuitas y compensaciones por privado),
  de cualquier persona, no solo de las del embudo.
El destino de cada enlace nuevo se pregunta una vez y queda en `enlaces`.

Además, el lector guarda al momento cada mensaje del canal principal
(guardar_al_momento): un anuncio de venta abre las lecturas de overoption
cada 20 min (diseño del 2026-11-03).
"""
import asyncio
import logging
import time
from datetime import datetime

from . import analisis, db, enlaces, ventas

log = logging.getLogger("captacion.publicaciones")

LECTURA_CADA_S = 3600
ESPERA_INICIAL_S = 1200  # que el lector arranque tranquilo
MARGEN_S = 3600  # al volver a leer los privados, una hora hacia atrás por si acaso
PAUSA_S = 0.5
MAX_TEXTO = 4000
INTENTOS = 3
CLAVE_GRUPO = "publicaciones_grupo_picks"
CLAVE_PRIVADOS = "publicaciones_privados_ts"


# --- Base de datos -------------------------------------------------------------

def guardar_mensajes(con, chat_id, filas):
    """filas: [{"msg_id", "ts", "texto", "hashes", "reenvio": (chat, msg) o None}]."""
    con.executemany(
        "INSERT OR IGNORE INTO publicaciones (chat_id, msg_id, ts, texto, enlaces, reenvio_chat, reenvio_msg) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(chat_id, f["msg_id"], int(f["ts"]), f["texto"], " ".join(f["hashes"]),
          *(f["reenvio"] or (None, None))) for f in filas])


def guardar_privados(con, user_id, filas):
    """filas: [(msg_id, ts, hash)]."""
    con.executemany("INSERT OR IGNORE INTO enlaces_privados (user_id, msg_id, ts, hash) VALUES (?, ?, ?, ?)",
                    [(user_id, mid, int(ts), h) for mid, ts, h in filas])


def _desde_id(con, chat_id):
    """Desde qué mensaje sigue el repaso de un chat: el último que leyó (no lo
    guardado al momento, que podría saltarse mensajes) o, la primera vez, el
    último guardado."""
    v = db.leer_estado(con, f"publicaciones_ultimo_{chat_id}")
    return int(v) if v is not None else ultimo(con, chat_id)


def ultimo(con, chat_id):
    """El último mensaje leído de un chat (guardado o no), o None."""
    v = db.leer_estado(con, f"publicaciones_ultimo_{chat_id}")
    guardado = con.execute("SELECT MAX(msg_id) FROM publicaciones WHERE chat_id = ?", (chat_id,)).fetchone()[0]
    vistos = [int(x) for x in (v, guardado) if x is not None]
    return max(vistos) if vistos else None


def inicio_ts(cfg):
    return datetime.combine(analisis.DESDE, datetime.min.time(), tzinfo=cfg.tz).timestamp()


# --- Telegram -----------------------------------------------------------------------

def _filtro_url():
    from telethon.tl import types

    return types.InputMessagesFilterUrl()


def _reenvio(m):
    fwd = getattr(m, "fwd_from", None)
    if fwd is None or not getattr(fwd, "channel_post", None):
        return None
    origen = getattr(getattr(fwd, "from_id", None), "channel_id", None)
    return (origen, fwd.channel_post) if origen else None


async def _con_esperas(hacer, dormir):
    """Ejecuta `hacer()`; si Telegram pide esperar (FloodWaitError), espera
    lo que pide y lo vuelve a intentar (hasta INTENTOS veces)."""
    for intento in range(INTENTOS):
        try:
            return await hacer()
        except Exception as e:
            segundos = getattr(e, "seconds", None)
            if type(e).__name__ != "FloodWaitError" or segundos is None or intento == INTENTOS - 1:
                raise
            log.warning("Telegram pide esperar %s s", segundos)
            await dormir(segundos + 1)


async def _apuntar_destinos(con, hashes, destino):
    """Pregunta a qué canal lleva cada enlace que aún no está en la caché."""
    for h in hashes:
        if db.enlace_guardado(con, h) is None:
            chat_id, titulo = await destino(h)
            with con:
                db.guardar_enlace(con, h, chat_id, titulo, time.time())


def fila_de(m):
    """La fila de un mensaje con texto o enlace, o None (p. ej. una foto sola)."""
    texto = (m.message or "")[:MAX_TEXTO]
    hashes = enlaces.hashes_invitacion(enlaces.textos_de(m))
    if not (texto.strip() or hashes):
        return None
    return {"msg_id": m.id, "ts": m.date.timestamp(), "texto": texto, "hashes": hashes, "reenvio": _reenvio(m)}


def guardar_al_momento(con, chat_id, m):
    """Dentro del lector, al llegar un mensaje del canal principal: se guarda
    ya (el repaso de cada hora lo vuelve a ver sin duplicarlo). True si se guardó."""
    fila = fila_de(m)
    if fila is None:
        return False
    with con:
        guardar_mensajes(con, chat_id, [fila])
    return True


async def _leer_chat(client, chat, desde_id, desde_fecha):
    """(filas nuevas con texto o enlace, último msg_id visto)."""
    filas, ultimo_id = [], desde_id
    kw = {"min_id": desde_id} if desde_id else {"offset_date": desde_fecha}
    async for m in client.iter_messages(chat, reverse=True, **kw):
        ultimo_id = max(ultimo_id or 0, m.id)
        fila = fila_de(m)
        if fila is not None:
            filas.append(fila)
    return filas, ultimo_id


async def _canal_principal(client, cfg):
    """La entidad del canal principal, o None si no hay o no se puede ver."""
    if getattr(cfg, "canal_id", None) is None:
        return None
    try:
        return await client.get_entity(cfg.canal_id)
    except Exception:
        log.exception("No pude ver el canal principal")
        return None


async def leer_canales(client, con, cfg, destino, dormir=asyncio.sleep):
    """Los mensajes nuevos de los canales de venta, del grupo de picks y del
    canal principal. Devuelve cuántos se guardaron."""
    todos, grupo = await analisis.canales_de_venta(client, cfg)
    principal = await _canal_principal(client, cfg)
    chats = ventas.filtrar(todos, cfg) + [c for c in (grupo, principal) if c is not None]
    if grupo is not None:
        with con:
            db.guardar_estado(con, CLAVE_GRUPO, grupo.id)
    desde_fecha = datetime.fromtimestamp(inicio_ts(cfg), cfg.tz)
    total = 0
    for chat in chats:
        try:
            filas, ultimo_id = await _con_esperas(
                lambda: _leer_chat(client, chat, _desde_id(con, chat.id), desde_fecha), dormir)
            await _apuntar_destinos(con, dict.fromkeys(h for f in filas for h in f["hashes"]), destino)
        except Exception:
            log.exception("No pude leer los mensajes de «%s»", getattr(chat, "title", chat.id))
            continue
        with con:
            guardar_mensajes(con, chat.id, filas)
            if ultimo_id:
                db.guardar_estado(con, f"publicaciones_ultimo_{chat.id}", ultimo_id)
        total += len(filas)
        await dormir(PAUSA_S)
    return total


async def _enlaces_del_dueno(client, entidad, desde):
    filas = []
    async for m in client.iter_messages(entidad, filter=_filtro_url()):
        ts = m.date.timestamp()
        if ts < desde:
            break
        if m.out:
            filas.extend((m.id, ts, h) for h in enlaces.hashes_invitacion(enlaces.textos_de(m)))
    return filas


async def leer_privados(client, con, cfg, destino, dormir=asyncio.sleep, ahora=None):
    """Los enlaces de invitación que el dueño mandó por privado en los chats
    con movimiento desde la última lectura (la primera vez, desde el 22/07).
    Devuelve cuántos se guardaron."""
    ahora = time.time() if ahora is None else ahora
    anterior = db.leer_estado(con, CLAVE_PRIVADOS)
    desde = inicio_ts(cfg) if anterior is None else int(anterior) - MARGEN_S
    total = 0
    async for d in client.iter_dialogs():
        if d.date is not None and d.date.timestamp() < desde:
            if d.pinned:
                continue  # los fijados van primero, aunque sean antiguos
            break
        u = d.entity
        if not d.is_user or getattr(u, "bot", False) or getattr(u, "is_self", False) or getattr(u, "deleted", False):
            continue
        try:
            filas = await _con_esperas(lambda: _enlaces_del_dueno(client, u, desde), dormir)
            await _apuntar_destinos(con, dict.fromkeys(h for _, _, h in filas), destino)
        except Exception:
            log.exception("No pude leer los enlaces del chat %s", u.id)
            continue
        if filas:
            with con:
                guardar_privados(con, u.id, filas)
            total += len(filas)
        await dormir(PAUSA_S)
    with con:
        db.guardar_estado(con, CLAVE_PRIVADOS, int(ahora))
    return total


async def lectura_periodica(client, con, cfg, destino, cada=LECTURA_CADA_S):
    """Dentro del lector: cada hora, lo nuevo de los canales y de los privados."""
    await asyncio.sleep(ESPERA_INICIAL_S)
    while True:
        try:
            inicio = time.time()
            canales = await leer_canales(client, con, cfg, destino)
            privados = await leer_privados(client, con, cfg, destino, ahora=inicio)
            log.info("Publicaciones: %s mensajes nuevos de canales, %s enlaces por privado (%s s)",
                     canales, privados, int(time.time() - inicio))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Error leyendo los canales y los privados")
        await asyncio.sleep(cada)
