"""
Bot de bienvenida de PREMIER GALGOS (fase 1 de captacion/PLAN.md).

Qué hace:
1. Recibe cada solicitud de unión al canal (enlace con "Solicitar
   aprobación de administrador" activado).
2. Si esa persona (por su user_id) nunca ha recibido la bienvenida, se la
   envía por privado con los dos botones que abren el chat del dueño.
   Telegram solo deja escribirle mientras la solicitud está pendiente (5
   min como máximo): por eso SIEMPRE se envía primero y se acepta después.
3. Acepta la solicitud, haya podido enviar la bienvenida o no.
4. Si alguien escribe al bot, le contesta con el mismo "escríbeme" y los
   dos botones (cada vez, salvo ráfagas: ver Config.pausa_redireccion_s).
5. Avisa al dueño por Telegram de cualquier problema, y atiende sus
   comandos (/resumen, /semana, /estado).

Nunca acepta solicitudes de un chat que no sea el canal configurado.

Funciona con "long polling" (pregunta a Telegram por novedades): no
necesita exponer nada a internet. Cada actualización se marca como hecha
en la base de datos al terminarla; si se cae la red a mitad, se repite.

Arranque (en la VM lo hace systemd, ver deploy/):
    python3 -m premier_captacion.bot
"""
import logging
import signal
import sys
import time
from datetime import datetime

from . import db, mensajes, resumen
from .config import ErrorConfig, cargar_config
from .telegram_api import BotAPI, ErrorRed, ErrorTelegram

log = logging.getLogger("captacion.bot")

TIPOS_UPDATE = ["message", "chat_join_request", "my_chat_member"]
TIMEOUT_POLL = 50
ESPERA_MAX = 60

AYUDA_PROPIETARIO = (
    "Comandos:\n"
    "/resumen – lo que va de hoy\n"
    "/semana – lo que va de semana\n"
    "/estado – comprobar que el bot funciona\n"
    "/miid – tu id de Telegram"
)


def nombre_enlace(invite_link):
    """Identificador del enlace de entrada: su nombre si lo tiene.

    Si el enlace lo creó otro administrador, Telegram le enseña al bot la
    URL recortada ("https://t.me/+AbC…"): por eso conviene poner nombre a
    los enlaces (no cambia la URL).
    """
    if not invite_link:
        return None
    return invite_link.get("name") or invite_link.get("invite_link")


def describir(usuario):
    nombre = db.nombre_completo(usuario) or "sin nombre"
    if usuario.get("username"):
        return f"{nombre} (@{usuario['username']})"
    return f"{nombre} (id {usuario['id']})"


class BotCaptacion:
    def __init__(self, cfg, api, con, reloj=time.time, dormir=time.sleep):
        self.cfg = cfg
        self.api = api
        self.con = con
        self.reloj = reloj
        self.dormir = dormir
        self.bot_id = None
        self._update_id = None
        self._fuera_de_plazo = 0
        # Avisos que solo se dan una vez por arranque (p. ej. un mismo error
        # que se repite en cada solicitud), para no inundar al dueño.
        self._avisos_dados = set()

    # --- Avisos al dueño ------------------------------------------------------

    def avisar(self, texto, clave=None):
        if clave is not None:
            if clave in self._avisos_dados:
                return
            self._avisos_dados.add(clave)
        log.warning("AVISO: %s", texto)
        if self.cfg.propietario_id is None:
            return
        try:
            self.api.llamar("sendMessage", chat_id=self.cfg.propietario_id, text=texto)
        except (ErrorTelegram, ErrorRed) as e:
            log.error("No se pudo enviar el aviso al propietario: %s", e)

    def _responder(self, chat_id, texto):
        try:
            self.api.llamar("sendMessage", chat_id=chat_id, text=texto)
        except ErrorTelegram as e:
            log.error("No se pudo responder a %s: %s", chat_id, e)

    # --- Arranque -------------------------------------------------------------

    def comprobar_arranque(self):
        yo = self.api.llamar("getMe")
        self.bot_id = yo["id"]
        log.info("Bot @%s (id %s) arrancando", yo.get("username"), self.bot_id)
        # Con un webhook activo getUpdates no funciona; este bot no usa webhook.
        self.api.llamar("deleteWebhook")
        if self.cfg.propietario_id is None:
            log.warning("CAPTACION_PROPIETARIO_ID vacío: los avisos solo irán al log. "
                        "Escribe /miid al bot desde tu cuenta para saber tu id.")
        if self.cfg.canal_id is None:
            log.warning("CAPTACION_CANAL_ID vacío: modo puesta en marcha, no se acepta a nadie. "
                        "Haz administrador al bot en el canal y te dirá su id.")
            return
        try:
            miembro = self.api.llamar("getChatMember", chat_id=self.cfg.canal_id, user_id=self.bot_id)
        except ErrorTelegram as e:
            self.avisar(f"🚨 No puedo acceder al canal configurado ({self.cfg.canal_id}): "
                        f"{e.descripcion}. ¿Está el bot añadido como administrador?", clave="arranque")
            return
        if miembro.get("status") != "administrator" or not miembro.get("can_invite_users"):
            self.avisar("🚨 En el canal configurado no soy administrador con el permiso "
                        "«Añadir suscriptores»: no puedo aceptar solicitudes.", clave="arranque")
        else:
            log.info("Permisos en el canal %s correctos", self.cfg.canal_id)

    # --- Bucle principal ------------------------------------------------------

    def bucle(self, seguir=lambda: True):
        espera = 0
        while seguir():
            if espera:
                self.dormir(espera)
            offset = db.leer_estado(self.con, "offset")
            try:
                updates = self.api.llamar(
                    "getUpdates",
                    _timeout_red=TIMEOUT_POLL + 15,
                    offset=int(offset) if offset else None,
                    timeout=TIMEOUT_POLL,
                    allowed_updates=TIPOS_UPDATE,
                )
            except ErrorRed as e:
                log.warning("Sin conexión con Telegram: %s", e)
                espera = min(max(espera * 2, 2), ESPERA_MAX)
                continue
            except ErrorTelegram as e:
                if e.codigo == 409:
                    self.avisar("🚨 Hay otro programa usando este mismo bot a la vez "
                                "(¿dos copias arrancadas?). Solo debe haber una.", clave="409")
                log.error("getUpdates rechazado: %s", e)
                espera = min(max(espera * 2, 5), ESPERA_MAX)
                continue

            espera = 0
            for update in updates:
                try:
                    self.procesar(update)
                except ErrorRed as e:
                    # Se repetirá esta misma actualización cuando vuelva la red.
                    log.warning("Red caída procesando la actualización %s: %s", update.get("update_id"), e)
                    espera = 5
                    break
                except Exception:
                    log.exception("Error inesperado procesando la actualización %s", update.get("update_id"))
                    self.avisar("🚨 Error inesperado del bot (revisa el log). Sigo funcionando.",
                                clave="error_interno")
                with self.con:
                    db.guardar_estado(self.con, "offset", update["update_id"] + 1)
            self._avisos_tras_lote()

    def _avisos_tras_lote(self):
        if self._fuera_de_plazo:
            self.avisar(f"⚠️ {self._fuera_de_plazo} solicitud(es) llevaban más de 5 minutos esperando "
                        "(¿el bot estuvo parado?). Se han aceptado, pero Telegram ya no deja "
                        "enviarles la bienvenida.")
            self._fuera_de_plazo = 0

    def procesar(self, update):
        self._update_id = update.get("update_id")
        if "chat_join_request" in update:
            self._solicitud(update["chat_join_request"])
        elif "message" in update:
            self._mensaje(update["message"])
        elif "my_chat_member" in update:
            self._cambio_de_permisos(update["my_chat_member"])

    # --- Solicitudes de unión ------------------------------------------------

    def _solicitud(self, sol):
        ahora = self.reloj()
        usuario, chat = sol["from"], sol["chat"]
        uid = usuario["id"]

        if self.cfg.canal_id is None or chat["id"] != self.cfg.canal_id:
            with self.con:
                db.registrar_evento(self.con, ahora, "solicitud_otro_chat", uid,
                                    chat_id=chat["id"], chat_titulo=chat.get("title"))
            if self.cfg.canal_id is None:
                self.avisar(f"ℹ️ Ha llegado una solicitud al canal «{chat.get('title')}» "
                            f"(id {chat['id']}). Si es el canal que debo gestionar, pon "
                            f"CAPTACION_CANAL_ID={chat['id']} y reinicia el bot. Mientras "
                            "tanto no acepto a nadie.", clave=f"otro_chat:{chat['id']}")
            else:
                self.avisar(f"⚠️ Ha llegado una solicitud a «{chat.get('title')}» (id {chat['id']}), "
                            "que no es el canal configurado: no la toco.", clave=f"otro_chat:{chat['id']}")
            return

        enlace = nombre_enlace(sol.get("invite_link"))
        retraso = max(0, int(ahora - sol.get("date", ahora)))
        with self.con:
            # Si esta actualización ya se registró (se está repitiendo tras
            # un corte de red), no se cuenta dos veces.
            if db.leer_estado(self.con, "solicitud_registrada") != str(self._update_id):
                db.registrar_solicitud(self.con, ahora, usuario, enlace)
                db.registrar_evento(self.con, ahora, "solicitud", uid, enlace=enlace, retraso_s=retraso)
                db.guardar_estado(self.con, "solicitud_registrada", self._update_id)
            fila = db.obtener_usuario(self.con, uid)

        if fila["bienvenida_ts"] is not None:
            # Ya la recibió alguna vez (p. ej. salió del canal y vuelve).
            log.info("Solicitud de %s: ya tenía bienvenida, se acepta sin mensaje", uid)
            with self.con:
                db.registrar_evento(self.con, ahora, "ya_recibida", uid, tipo_mensaje=fila["bienvenida_tipo"])
        elif retraso > self.cfg.ventana_bienvenida_s:
            log.info("Solicitud de %s con %ss de espera: fuera de plazo para escribirle", uid, retraso)
            with self.con:
                db.registrar_evento(self.con, ahora, "bienvenida_fallida", uid, motivo="fuera_de_plazo")
            self._fuera_de_plazo += 1
        else:
            self._enviar_bienvenida(sol, usuario)

        self._aceptar(chat["id"], usuario)

    def _enviar_bienvenida(self, sol, usuario):
        uid = usuario["id"]
        try:
            self.api.llamar(
                "sendMessage",
                chat_id=sol.get("user_chat_id", uid),
                text=mensajes.TEXTO_BIENVENIDA,
                reply_markup=mensajes.teclado_respuesta(self.cfg.perfil),
            )
        except ErrorTelegram as e:
            with self.con:
                db.registrar_evento(self.con, self.reloj(), "bienvenida_fallida", uid, motivo=e.descripcion)
            self.avisar(f"⚠️ No he podido enviar la bienvenida a {describir(usuario)}: {e.descripcion}. "
                        "La solicitud se acepta igualmente. (Si se repite este mismo error no te "
                        "vuelvo a avisar; sale en el resumen.)", clave=f"bienvenida:{e.descripcion}")
            return
        ahora = self.reloj()
        with self.con:
            db.marcar_bienvenida(self.con, uid, ahora, mensajes.TIPO_BIENVENIDA_BOT)
            db.registrar_evento(self.con, ahora, "bienvenida_enviada", uid,
                                tipo_mensaje=mensajes.TIPO_BIENVENIDA_BOT)
        log.info("Bienvenida enviada a %s", uid)

    def _aceptar(self, chat_id, usuario):
        uid = usuario["id"]
        try:
            self.api.llamar("approveChatJoinRequest", chat_id=chat_id, user_id=uid)
        except ErrorTelegram as e:
            texto = e.descripcion.upper()
            with self.con:
                if "USER_ALREADY_PARTICIPANT" in texto:
                    db.registrar_evento(self.con, self.reloj(), "aceptada", uid, ya_estaba=True)
                elif "HIDE_REQUESTER_MISSING" in texto:
                    # La aceptó/rechazó otro administrador o la persona la retiró.
                    db.registrar_evento(self.con, self.reloj(), "aceptacion_fallida", uid,
                                        motivo="solicitud_ya_gestionada")
                else:
                    db.registrar_evento(self.con, self.reloj(), "aceptacion_fallida", uid, motivo=e.descripcion)
                    self.avisar(f"⚠️ No he podido aceptar a {describir(usuario)}: {e.descripcion}. "
                                "Revisa las solicitudes pendientes del canal. (Si se repite este "
                                "mismo error no te vuelvo a avisar; sale en el resumen.)",
                                clave=f"aceptar:{e.descripcion}")
            return
        with self.con:
            db.registrar_evento(self.con, self.reloj(), "aceptada", uid)
        log.info("Solicitud de %s aceptada", uid)

    # --- Mensajes privados al bot ---------------------------------------------

    def _mensaje(self, msg):
        if msg.get("chat", {}).get("type") != "private":
            return
        usuario = msg.get("from")
        if not usuario or usuario.get("is_bot"):
            return
        uid = usuario["id"]
        texto = (msg.get("text") or "").strip()
        # "/miid" o "/miid@nombre_del_bot" (según desde dónde se envíe).
        comando = texto.split()[0].split("@")[0].lower() if texto.startswith("/") else None

        if comando == "/miid":
            self._responder(uid, f"Tu id de Telegram es: {uid}")
            return
        if uid == self.cfg.propietario_id:
            self._comando_propietario(comando)
            return

        ahora = self.reloj()
        with self.con:
            db.actualizar_datos_usuario(self.con, ahora, usuario)
            db.registrar_evento(self.con, ahora, "mensaje_al_bot", uid)
            fila = db.obtener_usuario(self.con, uid)
        ultima = fila["ultima_redireccion_ts"]
        if ultima is not None and ahora - ultima < self.cfg.pausa_redireccion_s:
            return
        try:
            self.api.llamar("sendMessage", chat_id=uid, text=mensajes.TEXTO_REDIRECCION,
                            reply_markup=mensajes.teclado_respuesta(self.cfg.perfil))
        except ErrorTelegram as e:
            with self.con:
                db.registrar_evento(self.con, ahora, "redireccion_fallida", uid, motivo=e.descripcion)
            return
        with self.con:
            db.marcar_redireccion(self.con, uid, ahora)
            db.registrar_evento(self.con, ahora, "redireccion_enviada", uid)

    def _comando_propietario(self, comando):
        ahora = self.reloj()
        tz = self.cfg.tz
        hoy = datetime.fromtimestamp(ahora, tz).date()
        if comando == "/resumen":
            texto = resumen.texto_diario(self.con, tz, hoy, ahora_ts=ahora)
        elif comando == "/semana":
            texto = resumen.texto_semanal(self.con, tz, resumen.lunes_de(hoy), ahora_ts=ahora)
        elif comando == "/estado":
            con_bienvenida = self.con.execute(
                "SELECT COUNT(*) FROM usuarios WHERE bienvenida_ts IS NOT NULL").fetchone()[0]
            canal = self.cfg.canal_id if self.cfg.canal_id is not None else "sin configurar (no acepto a nadie)"
            texto = (f"✅ Funcionando.\nCanal: {canal}\nBotones apuntan a: @{self.cfg.perfil}\n"
                     f"Personas que ya tienen bienvenida: {con_bienvenida}")
        elif comando == "/start":
            texto = "✅ Bot de captación activo. Aquí te llegarán los avisos y los resúmenes.\n\n" + AYUDA_PROPIETARIO
        else:
            texto = AYUDA_PROPIETARIO
        self._responder(self.cfg.propietario_id, texto)

    # --- Cambios en los permisos del bot --------------------------------------

    def _cambio_de_permisos(self, cambio):
        chat = cambio["chat"]
        nuevo = cambio.get("new_chat_member", {})
        estado = nuevo.get("status")
        ahora = self.reloj()

        if chat.get("type") == "private":
            # La persona ha bloqueado (kicked) o desbloqueado el bot.
            with self.con:
                db.registrar_evento(self.con, ahora, "bloqueo_bot" if estado == "kicked" else "desbloqueo_bot",
                                    chat["id"])
            return

        cid, titulo = chat["id"], chat.get("title")
        puede_invitar = bool(nuevo.get("can_invite_users"))
        with self.con:
            db.registrar_evento(self.con, ahora, "permisos_bot", None, chat_id=cid, chat_titulo=titulo,
                                estado=estado, puede_invitar=puede_invitar)

        if estado == "administrator":
            if not puede_invitar:
                self.avisar(f"⚠️ Soy administrador de «{titulo}» pero me falta el permiso "
                            "«Añadir suscriptores»: sin él no puedo aceptar solicitudes.")
            elif self.cfg.canal_id is None:
                self.avisar(f"ℹ️ Ya soy administrador de «{titulo}». Su id es {cid}: pon "
                            f"CAPTACION_CANAL_ID={cid} en la configuración y reinicia el bot.")
            elif cid == self.cfg.canal_id:
                self.avisar(f"✅ Ya soy administrador de «{titulo}» con permiso para aceptar solicitudes.")
            else:
                self.avisar(f"ℹ️ Me han hecho administrador de «{titulo}» (id {cid}), pero solo "
                            "gestiono el canal configurado.")
        elif cid == self.cfg.canal_id:
            self.avisar(f"🚨 He dejado de ser administrador de «{titulo}» (estado: {estado}). "
                        "No puedo aceptar solicitudes ni enviar bienvenidas hasta que vuelva a serlo.")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        cfg = cargar_config()
    except ErrorConfig as e:
        log.error("Configuración incorrecta: %s", e)
        return 2

    # systemd para el servicio con SIGTERM: se sale limpio (SQLite deshace
    # cualquier transacción a medias y la actualización se repite al volver).
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    con = db.abrir(cfg.db_path)
    bot = BotCaptacion(cfg, BotAPI(cfg.bot_token), con)
    try:
        bot.comprobar_arranque()
    except ErrorTelegram as e:
        if e.codigo == 401:
            # Reintentar no arregla un token revocado: se para (código 2).
            log.error("Telegram rechaza el token del bot (¿revocado en @BotFather?)")
            return 2
        raise
    except ErrorRed as e:
        log.error("Sin conexión con Telegram al arrancar (systemd reintentará): %s", e)
        return 1
    bot.bucle()
    return 0


if __name__ == "__main__":
    sys.exit(main())
