"""
Quién se unió con cada enlace de invitación de las ventas. Solo lectura.

Autorizado por el dueño el 2026-10-29. overoption da el enlace de Telegram
exacto de cada producto (pagos.py) y Telegram guarda, por enlace, la lista
de quién se unió con él y a qué hora (en la app: Enlaces de invitación →
«X se unieron»). Con esa hora, cada venta se empareja con quien entró justo
después de pagar, también en los canales antiguos, de los que no hay
registro de entradas (pagos.emparejar_ventas).

Modo a mano: `lector.sh real invitaciones [trozo del enlace]` (con el lector
parado: la sesión no se puede usar desde dos programas a la vez).
"""
import asyncio
import logging
import time

from . import db, enlaces, ventas

log = logging.getLogger("captacion.invitaciones")

MODO = "invitaciones"
POR_PAGINA = 100
PAUSA_S = 2  # entre enlaces, para no forzar a Telegram


# --- Base de datos -------------------------------------------------------------

def guardar(con, enlace, canal_id, titulo, invitados, ahora):
    """invitados: [(user_id, nombre, username, ts)]. Si alguien aparece con
    otra hora, se queda la primera vez que se unió."""
    con.execute("INSERT INTO pagos_enlaces (enlace, canal_id, titulo, leido_ts) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (enlace) DO UPDATE SET canal_id = excluded.canal_id, "
                "titulo = excluded.titulo, leido_ts = excluded.leido_ts",
                (enlace, canal_id, titulo, int(ahora)))
    for uid, nombre, username, ts in invitados:
        ventas.guardar_persona(con, uid, nombre, username)
        con.execute("INSERT INTO pagos_invitados (enlace, user_id, ts) VALUES (?, ?, ?) "
                    "ON CONFLICT (enlace, user_id) DO UPDATE SET ts = MIN(ts, excluded.ts)",
                    (enlace, uid, int(ts)))


def enlaces_de_ventas(con):
    """Los enlaces de las ventas, sin repetir, los de la venta más reciente primero."""
    return [f[0] for f in con.execute(
        "SELECT enlace FROM pagos_overoption WHERE enlace IS NOT NULL "
        "AND es_propina = 0 AND estado = 'SUCCESS' GROUP BY enlace ORDER BY MAX(pago_ts) DESC")]


# --- Telegram -----------------------------------------------------------------------

async def leer_enlace(client, enlace):
    """(canal, invitados) de un enlace: el canal al que lleva y
    [(user_id, nombre, username, ts)] de quien se unió con él.
    (None, None) si no lleva a un canal en el que estés o ha caducado;
    (canal, None) si no eres administrador de ese canal."""
    from telethon import errors
    from telethon.tl import functions, types

    hashes = enlaces.hashes_invitacion([enlace])
    if not hashes:
        return None, None
    try:
        respuesta = await client(functions.messages.CheckChatInviteRequest(hash=hashes[0]))
    except (errors.InviteHashExpiredError, errors.InviteHashInvalidError, errors.InviteHashEmptyError):
        return None, None
    canal = getattr(respuesta, "chat", None)
    if not isinstance(canal, types.Channel):
        return None, None
    invitados = []
    desde_fecha, desde_usuario = None, types.InputUserEmpty()
    try:
        while True:
            pagina = await client(functions.messages.GetChatInviteImportersRequest(
                peer=canal, link=enlaces.enlace(hashes[0]), requested=False,
                offset_date=desde_fecha, offset_user=desde_usuario, limit=POR_PAGINA))
            usuarios = {u.id: u for u in pagina.users}
            for imp in pagina.importers:
                u = usuarios.get(imp.user_id)
                invitados.append((imp.user_id, ventas._nombre(u) if u else None,
                                  getattr(u, "username", None), int(imp.date.timestamp())))
            if len(pagina.importers) < POR_PAGINA:
                break
            ultimo = pagina.importers[-1]
            desde_fecha, desde_usuario = ultimo.date, usuarios[ultimo.user_id]
    except (errors.ChatAdminRequiredError, errors.ChannelPrivateError):
        return canal, None
    return canal, invitados


async def ejecutar(cfg, entorno, crear_cliente, credenciales_api, solo=None):
    """Modo a mano «invitaciones»: quién se unió con cada enlace de las ventas
    (o solo con los que contienen `solo`)."""
    api_id, api_hash, sesion = credenciales_api(entorno)
    con = db.abrir(cfg.db_path)
    lista = [e for e in enlaces_de_ventas(con) if not solo or solo in e]
    if not lista:
        con.close()
        print("No hay ventas con ese enlace." if solo else "No hay ventas con enlace.")
        return 1
    client = crear_cliente(sesion, api_id, api_hash, MODO)
    client.flood_sleep_threshold = ventas.ESPERA_MAXIMA_S
    sin_canal = sin_admin = personas = 0
    inicio = time.time()
    await client.connect()
    try:
        if not await client.is_user_authorized():
            log.error("La cuenta no está conectada: el dueño tiene que ejecutar conectar-cuenta.sh")
            return 2
        for n, enlace in enumerate(lista, 1):
            canal, invitados = await leer_enlace(client, enlace)
            sin_canal += canal is None
            sin_admin += canal is not None and invitados is None
            personas += len(invitados or [])
            with con:
                guardar(con, enlace, getattr(canal, "id", None), getattr(canal, "title", None),
                        invitados or [], time.time())
            log.info("Enlace %s/%s: %s", n, len(lista),
                     "no lleva a un canal tuyo (o ha caducado)" if canal is None
                     else f"«{canal.title}», sin permiso para ver quién entró" if invitados is None
                     else f"«{canal.title}», {len(invitados)} se unieron")
            await asyncio.sleep(PAUSA_S)
    finally:
        await client.disconnect()
        con.close()
    print(f"✓ {len(lista)} enlaces leídos en {int(time.time() - inicio) // 60} min: {personas} entradas"
          + (f"; {sin_canal} no llevan a un canal tuyo o han caducado" if sin_canal else "")
          + (f"; en {sin_admin} no eres administrador" if sin_admin else "") + ".")
    return 0
