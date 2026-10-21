"""
Lector de la cuenta de Telegram del dueño (fases 3 y 4 de captacion/PLAN.md).

Se conecta como el dueño (con Telethon, la API de cuentas de usuario) para
ordenar sus carpetas según las reglas de carpetas.py. NUNCA envía nada desde
su cuenta: toda petición pasa por guardia.py, que solo deja leer y organizar
carpetas. Tampoco marca nada como leído ni le hace aparecer «en línea».

Modos:
    python -m premier_captacion.lector                   servicio (captacion-lector@)
    python -m premier_captacion.lector iniciar-sesion    lo ejecuta el dueño a mano
                                                         (deploy/conectar-cuenta.sh)
    python -m premier_captacion.lector historico         fase 4, solo lectura
                                                         (deploy/leer-historico.sh)
    python -m premier_captacion.lector embudo-prueba ID  solo pruebas: marca a alguien
                                                         como si hubiera recibido bienvenida
    python -m premier_captacion.lector canal-de-enlace ENLACE
                                                         a qué canal lleva un enlace (solo
                                                         lectura; lo usa leer-historico.sh)

Empieza SIEMPRE en modo simulación (CAPTACION_LECTOR_SIMULAR=1): avisa por
el bot de lo que haría, sin tocar las carpetas. Para que actúe de verdad:
configurar.sh <instancia> lector real.

Una misma sesión no puede usarse desde dos programas a la vez (Telegram la
anula): conectar-cuenta.sh y leer-historico.sh paran antes el servicio.
"""
import argparse
import asyncio
import concurrent.futures
import copy
import getpass
import logging
import os
import re
import signal
import sys
import time

from . import carpetas, consulta, db, guardia, historico
from .enlaces import hashes_invitacion, textos_de
from .config import ErrorConfig, cargar_config
from .telegram_api import BotAPI, ErrorRed, ErrorTelegram

log = logging.getLogger("captacion.lector")

REVISION_CADA_S = 600
# Al arrancar se repasa lo que llegó mientras el lector estaba parado; la
# primera vez, solo el último día (lo anterior es cosa de la fase 4).
HORIZONTE_INICIAL_S = 24 * 3600
_RE_API_HASH = re.compile(r"^[0-9a-f]{32}$")
_RE_TELEFONO = re.compile(r"^\+\d{8,15}$")


class ErrorLector(Exception):
    pass


# --- Ajustes ---------------------------------------------------------------

def _entero(entorno, clave, defecto, minimo=1):
    valor = entorno.get(clave, "").strip()
    if not valor:
        return defecto
    try:
        numero = int(valor)
    except ValueError:
        raise ErrorConfig(f"{clave} debe ser un número (está como {valor!r})") from None
    if numero < minimo:
        raise ErrorConfig(f"{clave} debe ser {minimo} o más")
    return numero


def credenciales_api(entorno):
    api_id = entorno.get("CAPTACION_API_ID", "").strip()
    api_hash = entorno.get("CAPTACION_API_HASH", "").strip()
    if not api_id.isdigit() or not _RE_API_HASH.match(api_hash):
        raise ErrorConfig("Faltan CAPTACION_API_ID / CAPTACION_API_HASH (de my.telegram.org): "
                          "configurar.sh <instancia> api")
    sesion = entorno.get("CAPTACION_SESION", "").strip()
    if not sesion:
        raise ErrorConfig("CAPTACION_SESION vacío (ruta del archivo de sesión)")
    return int(api_id), api_hash, sesion


def ajustes_desde(entorno, cfg):
    simular = entorno.get("CAPTACION_LECTOR_SIMULAR", "1").strip() != "0"
    return carpetas.Ajustes(
        canal_principal=carpetas.id_canal_puro(cfg.canal_id),
        dias=_entero(entorno, "CAPTACION_DIAS_CARPETAS", 5),
        nombre_free_send=entorno.get("CAPTACION_FREE_SEND", "").strip() or "free send",
        max_free_send=_entero(entorno, "CAPTACION_MAX_FREE_SEND", 90),
        max_carpetas=_entero(entorno, "CAPTACION_MAX_CARPETAS", 10),
        max_chats=_entero(entorno, "CAPTACION_MAX_CHATS_CARPETA", 100),
        simular=simular,
        bienvenidas_manuales=entorno.get("CAPTACION_BIENVENIDAS_MANUALES", "").strip() == "1",
    )


# --- Telethon ----------------------------------------------------------------

def crear_cliente(sesion, api_id, api_hash, modo):
    """Cliente de Telethon con el candado de guardia.py enganchado.

    Todas las peticiones de Telethon pasan por TelegramClient._call; aquí se
    comprueban antes de salir. Lo no permitido se bloquea y se registra.
    """
    from telethon import TelegramClient

    class ClienteVigilado(TelegramClient):
        async def _call(self, sender, request, ordered=False, flood_sleep_threshold=None):
            try:
                guardia.comprobar(request, modo)
            except guardia.PeticionProhibida as e:
                log.error("BLOQUEADO por seguridad: %s", e)
                raise
            return await super()._call(sender, request, ordered=ordered,
                                       flood_sleep_threshold=flood_sleep_threshold)

    return ClienteVigilado(
        sesion, api_id, api_hash,
        # Así aparece en Telegram → Ajustes → Dispositivos.
        device_model="Premier captación (VM)", system_version="Linux", app_version="1.0",
        receive_updates=(modo in ("lector", "simulacion")), catch_up=False, flood_sleep_threshold=120,
    )


_REGLAS = ("contacts", "non_contacts", "groups", "broadcasts", "bots")


class TelegramReal:
    """Adaptador de carpetas.py sobre Telethon (carpetas = "dialog filters")."""

    def __init__(self, client):
        from telethon.tl import functions, types

        self.client = client
        self.f = functions
        self.t = types
        self._raw = {}
        self._peers = {}

    def recordar(self, peer):
        if isinstance(peer, self.t.InputPeerUser):
            self._peers[peer.user_id] = peer

    async def carpetas(self):
        res = await self.client(self.f.messages.GetDialogFiltersRequest())
        filtros = getattr(res, "filters", res)
        self._raw = {}
        lista = []
        for f in filtros:
            if not hasattr(f, "id"):
                continue  # «Todos los chats» (DialogFilterDefault)
            titulo = getattr(f.title, "text", f.title) or ""
            peers = list(getattr(f, "pinned_peers", None) or []) + list(getattr(f, "include_peers", None) or [])
            usuarios = set()
            for p in peers:
                if isinstance(p, self.t.InputPeerUser):
                    usuarios.add(p.user_id)
                    self._peers.setdefault(p.user_id, p)
            self._raw[f.id] = f
            lista.append(carpetas.Carpeta(
                f.id, titulo, frozenset(usuarios), len(peers),
                gestionable=isinstance(f, self.t.DialogFilter),
                con_reglas=any(getattr(f, r, None) for r in _REGLAS),
            ))
        return lista

    async def _peer(self, user_id):
        if user_id not in self._peers:
            self._peers[user_id] = await self.client.get_input_entity(user_id)
        return self._peers[user_id]

    async def crear_carpeta(self, titulo, usuarios):
        if not self._raw:
            await self.carpetas()
        nuevo = min(set(range(2, 256)) - set(self._raw))
        filtro = self.t.DialogFilter(
            id=nuevo, title=self.t.TextWithEntities(text=titulo, entities=[]),
            pinned_peers=[], include_peers=[await self._peer(u) for u in sorted(usuarios)], exclude_peers=[],
        )
        await self.client(self.f.messages.UpdateDialogFilterRequest(id=nuevo, filter=filtro))
        self._raw[nuevo] = filtro
        return nuevo

    async def cambiar(self, carpeta_id, anadir=frozenset(), quitar=frozenset()):
        f = self._raw[carpeta_id]
        if not isinstance(f, self.t.DialogFilter):
            raise ErrorLector(f"la carpeta {carpeta_id} es compartida: no se toca")

        def fuera(p):
            return isinstance(p, self.t.InputPeerUser) and p.user_id in quitar

        fijados = [p for p in f.pinned_peers if not fuera(p)]
        incluidos = [p for p in f.include_peers if not fuera(p)]
        presentes = {p.user_id for p in fijados + incluidos if isinstance(p, self.t.InputPeerUser)}
        for u in sorted(set(anadir) - presentes):
            incluidos.append(await self._peer(u))
        if not fijados and not incluidos and not any(getattr(f, r, None) for r in _REGLAS):
            await self.borrar(carpeta_id)  # Telegram no acepta carpetas vacías
            return False
        nuevo = copy.copy(f)  # conserva todo lo demás (excluidos, reglas, emoji, color...)
        nuevo.pinned_peers = fijados
        nuevo.include_peers = incluidos
        await self.client(self.f.messages.UpdateDialogFilterRequest(id=f.id, filter=nuevo))
        self._raw[f.id] = nuevo
        return True

    async def borrar(self, carpeta_id):
        await self.client(self.f.messages.UpdateDialogFilterRequest(id=carpeta_id))
        self._raw.pop(carpeta_id, None)

    async def destino_enlace(self, hash_enlace):
        from telethon import errors

        try:
            r = await self.client(self.f.messages.CheckChatInviteRequest(hash=hash_enlace))
        except (errors.InviteHashExpiredError, errors.InviteHashInvalidError, errors.InviteHashEmptyError):
            return None, None
        chat = getattr(r, "chat", None)
        if chat is not None:
            return chat.id, getattr(chat, "title", None)
        return None, getattr(r, "title", None)


async def procesar(mensaje, otro, entrada, org, tg_real):
    """Un mensaje de un chat privado (en directo o recuperado al arrancar)."""
    if otro is None or getattr(otro, "bot", False) or getattr(otro, "is_self", False):
        return
    tg_real.recordar(entrada)
    ts = mensaje.date.timestamp()
    if mensaje.out:
        tipo = historico.tipo_bienvenida_manual(mensaje.message) if org.aj.bienvenidas_manuales else None
        if tipo:  # el dueño acaba de darle la bienvenida a mano: entra en el embudo
            historico.apuntar_bienvenida(org.con, otro.id, ts, tipo, _usuario(otro), historico=False)
        await org.al_enviar(otro.id, mensaje.id, ts, textos_de(mensaje))
    else:
        await org.al_recibir(otro.id, mensaje.id, ts, mensaje.message or "", usuario=_usuario(otro))


def _usuario(otro):
    return {"id": otro.id, "first_name": getattr(otro, "first_name", None),
            "last_name": getattr(otro, "last_name", None), "username": getattr(otro, "username", None)}


async def recuperar_perdido(client, con, org, tg_real, horizonte):
    """Repasa los chats con movimiento desde `horizonte` (p. ej. si el lector
    estuvo parado). Lo ya procesado se salta (ultimo_msg_id por persona)."""
    from datetime import datetime, timezone

    desde = datetime.fromtimestamp(horizonte, timezone.utc)
    async for dialogo in client.iter_dialogs(limit=400):
        if dialogo.date is not None and dialogo.date < desde:
            if dialogo.pinned:
                continue  # los fijados van primero, aunque sean antiguos
            break
        if not dialogo.is_user:
            continue
        otro = dialogo.entity
        if getattr(otro, "bot", False) or getattr(otro, "is_self", False):
            continue
        fila = db.obtener_usuario(con, otro.id)
        if not db.es_del_embudo(fila) and not org.aj.bienvenidas_manuales:
            continue  # (con bienvenidas manuales, también quien pudo recibir una mientras estaba parado)
        async for mensaje in client.iter_messages(otro, reverse=True, offset_date=desde,
                                                  min_id=(fila["ultimo_msg_id"] if fila else None) or 0, limit=300):
            await procesar(mensaje, otro, dialogo.input_entity, org, tg_real)


# --- Avisos por el bot ---------------------------------------------------------

def crear_avisador(cfg):
    """Avisos al dueño por el bot (si hay token y propietario). No bloquea, y
    llegan en el orden en que se piden: los envía un solo hilo, uno detrás de
    otro (antes iban a la vez y se desordenaban)."""
    if not cfg.bot_token or cfg.propietario_id is None:
        return lambda texto: log.warning("AVISO (sin bot configurado): %s", texto)
    api = BotAPI(cfg.bot_token)
    hilo = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="avisos")

    def enviar(texto):
        try:
            api.llamar("sendMessage", chat_id=cfg.propietario_id, text=texto[:4000])
        except (ErrorTelegram, ErrorRed) as e:
            log.error("No se pudo enviar un aviso por el bot: %s", e)
        except Exception:
            log.exception("Fallo inesperado enviando un aviso por el bot")

    def avisar(texto):
        log.info("AVISO: %s", texto)
        hilo.submit(enviar, texto)  # al salir del programa se envían los que queden

    return avisar


# --- Modos -------------------------------------------------------------------

async def servicio(cfg, entorno):
    from telethon import events

    api_id, api_hash, sesion = credenciales_api(entorno)
    aj = ajustes_desde(entorno, cfg)
    avisar = crear_avisador(cfg)
    con = db.abrir(cfg.db_path)
    # En simulación el candado ni siquiera deja pedir cambios de carpetas.
    client = crear_cliente(sesion, api_id, api_hash, "simulacion" if aj.simular else "lector")
    await client.connect()
    try:
        if not await client.is_user_authorized():
            log.error("La cuenta no está conectada: el dueño tiene que ejecutar conectar-cuenta.sh")
            avisar("🚨 El lector de carpetas no tiene la cuenta conectada (¿se cerró la sesión en "
                   "Telegram → Dispositivos?). Queda parado. Para volver a conectarla: "
                   "bash /opt/premier-captacion/conectar-cuenta.sh <instancia>")
            return 2
        yo = await client.get_me()
        await client(client_status_offline())
        tg_real = TelegramReal(client)
        if aj.simular:
            tg = await carpetas.CarpetasEnMemoria.desde(tg_real, max_carpetas=aj.max_carpetas, max_chats=aj.max_chats)
        else:
            tg = tg_real
        org = carpetas.Organizador(con, tg, cfg.tz, aj, avisar=avisar)

        @client.on(events.NewMessage(func=lambda e: e.is_private))
        async def al_mensaje(evento):
            try:
                await procesar(evento.message, await evento.get_chat(), await evento.get_input_chat(), org, tg_real)
            except Exception:
                log.exception("Error procesando un mensaje")
                avisar("🚨 Error del lector de carpetas procesando un mensaje (revisa el registro). Sigo funcionando.")

        modo = "SIMULACIÓN (no toca nada; solo avisa de lo que haría)" if aj.simular else "REAL"
        nombre = " ".join(x for x in (yo.first_name, yo.last_name) if x) or str(yo.id)
        log.info("Lector conectado a la cuenta de %s (id %s), modo %s", nombre, yo.id, modo)
        avisar(f"📁 Lector de carpetas conectado a la cuenta de {nombre}. Modo: {modo}.")

        horizonte = int(db.leer_estado(con, "lector_horizonte_ts") or time.time() - HORIZONTE_INICIAL_S)
        await org.rotar()
        await recuperar_perdido(client, con, org, tg_real, horizonte)

        async def revisar():
            while True:
                await asyncio.sleep(REVISION_CADA_S)
                try:
                    await client(client_status_offline())
                    with con:
                        db.guardar_estado(con, "lector_horizonte_ts", int(time.time()) - 120)
                    await org.rotar()
                except Exception:
                    log.exception("Error en la revisión periódica")

        tarea = asyncio.ensure_future(revisar())
        parada = asyncio.Event()

        def parar():  # systemctl stop: salir limpio, sin dejar la unidad en "failed"
            parada.set()
            asyncio.ensure_future(client.disconnect())

        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, parar)
        try:
            await client.run_until_disconnected()
        finally:
            tarea.cancel()
        return 0 if parada.is_set() else 1  # desconexión inesperada: systemd lo rearranca
    finally:
        await client.disconnect()
        con.close()


def client_status_offline():
    from telethon.tl.functions.account import UpdateStatusRequest

    return UpdateStatusRequest(offline=True)


def pedir_telefono(leer=input):
    """Teléfono en formato internacional, como lo quiere Telegram: + y el
    prefijo del país, y el número sin el 0 inicial."""
    while True:
        valor = re.sub(r"[\s().-]", "", leer("Teléfono de la cuenta, con el prefijo del país y sin el 0 "
                                             "inicial (p. ej. +353 8… o +34 6…): "))
        if valor.startswith("00"):
            valor = "+" + valor[2:]
        if _RE_TELEFONO.match(valor):
            return valor
        print("   Tiene que empezar por + y el prefijo del país (+353 Irlanda, +34 España).")


async def iniciar_sesion(entorno):
    from telethon import errors

    api_id, api_hash, sesion = credenciales_api(entorno)
    client = crear_cliente(sesion, api_id, api_hash, "iniciar-sesion")
    for _ in range(3):
        try:
            await client.start(
                phone=pedir_telefono,
                code_callback=lambda: input("Código que te acaba de llegar por Telegram (o SMS): "),
                password=lambda: getpass.getpass("Contraseña de verificación en dos pasos (no se verá): "),
            )
            break
        except errors.PhoneNumberInvalidError:
            print("   Telegram dice que ese teléfono no es válido: revisa el prefijo y quita el 0 "
                  "inicial del número (+353 8…, no +353 08…).")
    else:
        await client.disconnect()
        return 1
    yo = await client.get_me()
    nombre = " ".join(x for x in (yo.first_name, yo.last_name) if x)
    print(f"✅ Conectado como {nombre} (@{yo.username or '-'}, id {yo.id}). La sesión queda en la VM.")
    await client.disconnect()
    return 0


async def canal_de_enlace(entorno, texto):
    """A qué canal lleva un enlace de invitación, sin unirse (solo lectura).
    Lo usa leer-historico.sh para saber cuál es el canal principal: imprime
    «-100…<tabulador>título», con el id en el formato de la Bot API."""
    from telethon import errors
    from telethon.tl import functions, types

    hashes = hashes_invitacion([texto])
    if not hashes:
        log.error("Eso no parece un enlace de invitación (t.me/+…)")
        return 1
    api_id, api_hash, sesion = credenciales_api(entorno)
    client = crear_cliente(sesion, api_id, api_hash, "historico")
    await client.connect()
    try:
        if not await client.is_user_authorized():
            log.error("La cuenta no está conectada: el dueño tiene que ejecutar conectar-cuenta.sh")
            return 2
        try:
            respuesta = await client(functions.messages.CheckChatInviteRequest(hash=hashes[0]))
        except (errors.InviteHashExpiredError, errors.InviteHashInvalidError, errors.InviteHashEmptyError):
            respuesta = None
    finally:
        await client.disconnect()
    chat = getattr(respuesta, "chat", None)
    if not isinstance(chat, types.Channel) or not chat.broadcast:
        log.error("Ese enlace no lleva a un canal en el que estés (o ha caducado)")
        return 1
    print(f"-100{chat.id}\t{chat.title}")
    return 0


async def apuntar_gratuita(cfg, entorno, usuario, bienvenida, gratuita, enlace):
    """Apunta a mano la bienvenida y la gratuita de alguien cuyo chat ya no se
    puede leer. Solo lee de Telegram (busca a la persona por su @)."""
    from datetime import datetime

    hashes = hashes_invitacion([enlace])
    if not hashes:
        log.error("Eso no parece un enlace de invitación (t.me/+…)")
        return 1
    try:
        tss = [datetime.strptime(t, "%Y-%m-%d %H:%M").replace(tzinfo=cfg.tz).timestamp() for t in (bienvenida, gratuita)]
    except ValueError:
        log.error("Las fechas van como «AAAA-MM-DD HH:MM» (hora de España)")
        return 1
    api_id, api_hash, sesion = credenciales_api(entorno)
    client = crear_cliente(sesion, api_id, api_hash, "historico")
    await client.connect()
    try:
        if not await client.is_user_authorized():
            log.error("La cuenta no está conectada: el dueño tiene que ejecutar conectar-cuenta.sh")
            return 2
        otro = await client.get_entity(usuario.lstrip("@"))
    finally:
        await client.disconnect()
    con = db.abrir(cfg.db_path)
    try:
        canal = historico.apuntar_gratuita_a_mano(con, _usuario(otro), tss[0], tss[1], hashes[0])
        fila = db.obtener_usuario(con, otro.id)
        print(f"✓ Apuntado (canal «{canal}»):\n" + consulta.ficha(con, fila, cfg.tz))
    finally:
        con.close()
    return 0


def marcar_embudo_prueba(cfg, user_id):
    """Solo pruebas: marca a alguien como si hubiera recibido la bienvenida."""
    con = db.abrir(cfg.db_path)
    try:
        ahora = time.time()
        with con:
            db.actualizar_datos_usuario(con, ahora, {"id": user_id})
            db.marcar_bienvenida(con, user_id, ahora, "prueba")
            db.registrar_evento(con, ahora, "bienvenida_prueba", user_id)
    finally:
        con.close()
    print(f"✓ {user_id} queda como del embudo (solo para pruebas)")
    return 0


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Lector de la cuenta del dueño (carpetas e histórico).")
    parser.add_argument("modo", nargs="?", default="servicio",
                        choices=["servicio", "iniciar-sesion", "historico", "embudo-prueba", "canal-de-enlace",
                                 "apuntar-gratuita"])
    parser.add_argument("dato", nargs="?", help="id de Telegram (embudo-prueba), enlace (canal-de-enlace) "
                                                "o @usuario (apuntar-gratuita)")
    parser.add_argument("mas", nargs="*", help="apuntar-gratuita: «AAAA-MM-DD HH:MM» de la bienvenida y de la "
                                               "gratuita, y el enlace de venta")
    args = parser.parse_args(argv)
    entorno = os.environ
    try:
        cfg = cargar_config(entorno, requiere_bot=False)
        if args.modo == "embudo-prueba":
            if not (args.dato or "").isdigit():
                parser.error("embudo-prueba necesita el id de Telegram (un número)")
            return marcar_embudo_prueba(cfg, int(args.dato))
        if args.modo == "canal-de-enlace":
            if not args.dato:
                parser.error("canal-de-enlace necesita el enlace")
            return asyncio.run(canal_de_enlace(entorno, args.dato))
        if args.modo == "iniciar-sesion":
            if not sys.stdin.isatty():
                log.error("iniciar-sesion lo ejecuta el dueño en su terminal (pide el código de Telegram)")
                return 2
            return asyncio.run(iniciar_sesion(entorno))
        if args.modo == "historico":
            return asyncio.run(historico.ejecutar(cfg, entorno))
        if args.modo == "apuntar-gratuita":
            if not args.dato or len(args.mas) != 3:
                parser.error('apuntar-gratuita @usuario "AAAA-MM-DD HH:MM" "AAAA-MM-DD HH:MM" <enlace de venta>')
            return asyncio.run(apuntar_gratuita(cfg, entorno, args.dato, *args.mas))
        return asyncio.run(servicio(cfg, entorno))
    except ErrorConfig as e:
        log.error("Configuración incorrecta: %s", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
