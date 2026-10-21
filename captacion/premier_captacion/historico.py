"""
Lectura del histórico de la cuenta del dueño (fase 4 de captacion/PLAN.md).

SOLO LECTURA en Telegram (guardia.py en modo "historico": ni carpetas, ni
enviar, ni marcar como leído). Lo que encuentra se apunta en la base de
datos local de la instancia:

1. Busca en sus chats privados las bienvenidas que enviaba a mano:
   - «Buenas! Bienvenido a 𝗣𝗥𝗘𝗠𝗜𝗘𝗥 𝗚𝗔𝗟𝗚𝗢𝗦 🐕 …»          -> manual_buenas
   - «Buenos dias y bienvenido a Premier Galgos! 🐾 …» y
     variantes («Buenas tardes y bienvenido…», «bienvenida…») -> manual_buenos_dias
2. Esas personas quedan como del embudo: el bot ya no les repetirá la
   bienvenida si salen del canal y vuelven.
3. Para cada una mira qué pasó después: cuándo contestó por primera vez y
   cuándo recibió un enlace de venta (y de qué canal; los del canal
   principal no cuentan). Así el Sheet puede comparar las bienvenidas
   manuales con la del bot.

Se puede repetir: lo que ya está apuntado no se duplica.
"""
import asyncio
import logging
import time

from . import carpetas, db, enlaces, mensajes

log = logging.getLogger("captacion.historico")

PALABRAS_BUSQUEDA = ("bienvenido", "bienvenida")
_NEGRITA_PREMIER = mensajes.negrita("PREMIER GALGOS")
MAX_MENSAJES_POR_CHAT = 500
PAUSA_ENTRE_CHATS_S = 0.3
# Si Telegram pide esperar (muchas consultas seguidas), se espera solo hasta
# este tope en vez de dejarlo a medias: es una lectura larga que se hace una vez.
ESPERA_MAXIMA_S = 30 * 60  # en la cuenta real llegó a pedir 886 s (2026-10-18)
AVISO_PROGRESO_CADA = 100


def tipo_bienvenida_manual(texto):
    """manual_buenas / manual_buenos_dias / None, según el texto enviado."""
    if not texto:
        return None
    if _NEGRITA_PREMIER in texto:
        return mensajes.TIPO_MANUAL_BUENAS
    t = carpetas.normalizar(texto)
    if ("bienvenido a premier galgos" in t or "bienvenida a premier galgos" in t):
        return mensajes.TIPO_MANUAL_BUENOS_DIAS
    return None


async def buscar_bienvenidas(client):
    """{user_id: (ts, tipo, msg_id, usuario)} con la primera bienvenida manual de cada uno."""
    encontradas = {}
    vistas = set()
    for palabra in PALABRAS_BUSQUEDA:
        log.info("Buscando «%s» en tus chats…", palabra)
        async for m in client.iter_messages(None, search=palabra):
            clave = (getattr(m, "chat_id", None), m.id)
            if clave in vistas or not m.out or not m.is_private:
                continue
            vistas.add(clave)
            tipo = tipo_bienvenida_manual(m.message)
            if tipo is None:
                continue
            otro = await m.get_chat()
            if otro is None or getattr(otro, "bot", False) or getattr(otro, "is_self", False):
                continue
            ts = m.date.timestamp()
            if otro.id not in encontradas or ts < encontradas[otro.id][0]:
                usuario = {"id": otro.id, "first_name": getattr(otro, "first_name", None),
                           "last_name": getattr(otro, "last_name", None), "username": getattr(otro, "username", None)}
                encontradas[otro.id] = (ts, tipo, m.id, usuario)
    return encontradas


def apuntar_bienvenida(con, user_id, ts, tipo, usuario, historico=True):
    with con:
        db.actualizar_datos_usuario(con, time.time(), usuario)
        fila = db.obtener_usuario(con, user_id)
        # Se queda la primera bienvenida que recibió, sea manual o del bot.
        if fila["bienvenida_ts"] is None or ts < fila["bienvenida_ts"]:
            db.actualizar_campos(con, user_id, time.time(), bienvenida_tipo=tipo, bienvenida_ts=int(ts))
        if not db.existe_evento(con, user_id, "bienvenida_manual", ts):
            db.registrar_evento(con, ts, "bienvenida_manual", user_id, tipo_mensaje=tipo,
                               **({"historico": True} if historico else {}))


async def repasar_chat(client, con, org, user_id, desde_msg_id):
    """Primera respuesta y primer enlace de venta después de la bienvenida."""
    fila = db.obtener_usuario(con, user_id)
    respuesta = fila["primer_mensaje_ts"]
    enlace_ts = fila["enlace_venta_ts"]
    hecho = {"respondio": False, "enlace": False}
    async for m in client.iter_messages(user_id, min_id=desde_msg_id, reverse=True, limit=MAX_MENSAJES_POR_CHAT):
        ts = m.date.timestamp()
        if not m.out and (respuesta is None or ts < respuesta):
            boton = carpetas.detectar_boton(m.message or "")
            with con:
                campos = {"primer_mensaje_ts": int(ts)}
                if fila["boton"] is None and boton:
                    campos["boton"] = boton
                db.actualizar_campos(con, user_id, time.time(), **campos)
                if not db.existe_evento(con, user_id, "te_escribe", ts):
                    db.registrar_evento(con, ts, "te_escribe", user_id, primera_vez=True, historico=True)
            respuesta = ts
            hecho["respondio"] = True
        if m.out and enlace_ts is None:
            for h in enlaces.hashes_invitacion(enlaces.textos_de(m)):
                chat_id, titulo = await org.destino(h)
                if org.es_principal(chat_id):
                    continue
                with con:
                    db.actualizar_campos(con, user_id, time.time(), enlace_venta_ts=int(ts),
                                         enlace_venta=enlaces.enlace(h), canal_venta=titulo or "desconocido")
                    if not db.existe_evento(con, user_id, "enlace_venta", ts):
                        db.registrar_evento(con, ts, "enlace_venta", user_id, enlace=enlaces.enlace(h),
                                            canal=titulo or "desconocido", historico=True)
                enlace_ts = ts
                hecho["enlace"] = True
                break
        if respuesta is not None and enlace_ts is not None:
            break
    return hecho


async def leer(client, con, org):
    """Todo el proceso. Devuelve un resumen con los números."""
    encontradas = await buscar_bienvenidas(client)
    log.info("Bienvenidas manuales encontradas: %d", len(encontradas))
    por_tipo = {}
    respondieron = con_enlace = 0
    for n, (user_id, (ts, tipo, msg_id, usuario)) in enumerate(
            sorted(encontradas.items(), key=lambda par: par[1][0]), start=1):
        if n % AVISO_PROGRESO_CADA == 0:
            log.info("Repasando chats: %d de %d", n, len(encontradas))
        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
        apuntar_bienvenida(con, user_id, ts, tipo, usuario)
        await repasar_chat(client, con, org, user_id, msg_id)
        fila = db.obtener_usuario(con, user_id)
        respondieron += fila["primer_mensaje_ts"] is not None
        con_enlace += fila["enlace_venta_ts"] is not None
        await asyncio.sleep(PAUSA_ENTRE_CHATS_S)
    return {"personas": len(encontradas), "por_tipo": por_tipo,
            "respondieron": respondieron, "con_enlace": con_enlace}


def texto_resumen(resultado):
    lineas = [f"📚 Histórico leído (solo lectura): {resultado['personas']} personas con bienvenida manual."]
    for tipo, n in sorted(resultado["por_tipo"].items()):
        lineas.append(f"   · {mensajes.TIPOS_MENSAJE.get(tipo, tipo)}: {n}")
    lineas.append(f"✉️ Te contestaron: {resultado['respondieron']}")
    lineas.append(f"🔗 Recibieron enlace de venta: {resultado['con_enlace']}")
    lineas.append("A ninguna se le volverá a enviar la bienvenida del bot.")
    return "\n".join(lineas)


async def ejecutar(cfg, entorno):
    from .lector import TelegramReal, ajustes_desde, crear_avisador, crear_cliente, credenciales_api

    api_id, api_hash, sesion = credenciales_api(entorno)
    aj = ajustes_desde(entorno, cfg)
    con = db.abrir(cfg.db_path)
    client = crear_cliente(sesion, api_id, api_hash, "historico")
    client.flood_sleep_threshold = ESPERA_MAXIMA_S
    await client.connect()
    try:
        if not await client.is_user_authorized():
            log.error("La cuenta no está conectada: el dueño tiene que ejecutar conectar-cuenta.sh")
            return 2
        # El organizador solo se usa para saber a qué canal lleva cada enlace
        # (con caché); en este modo el candado no deja tocar carpetas.
        org = carpetas.Organizador(con, TelegramReal(client), cfg.tz, aj)
        resultado = await leer(client, con, org)
        texto = texto_resumen(resultado)
        print(texto)
        crear_avisador(cfg)(texto)
        await asyncio.sleep(2)  # que salga el aviso antes de cerrar
        return 0
    finally:
        await client.disconnect()
        con.close()
