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
6. Freno de emergencia: con /pausar el dueño lo para al momento (no envía
   bienvenidas ni acepta; las solicitudes se quedan pendientes para que las
   acepte él a mano) y con /reanudar vuelve. Se guarda en la base de datos:
   sigue en pausa aunque el bot se reinicie.
7. Dudas frecuentes: la respuesta a quien escribe al bot lleva un botón
   «📚 Dudas frecuentes» con un menú de temas; cada respuesta acaba
   invitando a escribir al dueño (y, a quien aún no tiene la apuesta de
   regalo, con los dos botones de la bienvenida).
8. El dueño cambia los textos (bienvenida, respuestas y dudas) desde el
   propio bot con /textos: manda el nuevo, ve cómo quedará y lo guarda.

Nunca acepta solicitudes de un chat que no sea el canal configurado.

Funciona con "long polling" (pregunta a Telegram por novedades): no
necesita exponer nada a internet. Cada actualización se marca como hecha
en la base de datos al terminarla; si se cae la red a mitad, se repite.

Arranque (en la VM lo hace systemd, ver deploy/):
    python3 -m premier_captacion.bot
"""
import logging
import os
import signal
import sys
import time
from datetime import datetime

from . import db, mensajes, resumen, textos
from .config import ErrorConfig, cargar_config
from .telegram_api import BotAPI, ErrorRed, ErrorTelegram

log = logging.getLogger("captacion.bot")

TIPOS_UPDATE = ["message", "chat_join_request", "my_chat_member", "callback_query"]
TIMEOUT_POLL = 50
ESPERA_MAX = 60

AYUDA_PROPIETARIO = (
    "Comandos:\n"
    "/resumen – lo que va de hoy\n"
    "/semana – lo que va de semana\n"
    "/estado – comprobar que el bot funciona\n"
    "/pausar – dejar de aceptar solicitudes al momento (por si algo falla)\n"
    "/reanudar – volver a aceptarlas\n"
    "/textos – cambiar la bienvenida, las respuestas y las dudas frecuentes\n"
    "/dudas – ver las dudas frecuentes como las ve un cliente\n"
    "/miid – tu id de Telegram"
)


def version_instalada():
    """Versión que dejó deploy/instalar.sh en /opt/premier-captacion/VERSION."""
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION")
    try:
        with open(ruta, encoding="utf-8") as f:
            return f.read().strip() or "desconocida"
    except OSError:
        return "sin instalar (desarrollo)"


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

    def _responder(self, chat_id, texto, teclado=None):
        try:
            if teclado is None:
                self.api.llamar("sendMessage", chat_id=chat_id, text=texto)
            else:
                self.api.llamar("sendMessage", chat_id=chat_id, text=texto, reply_markup=teclado)
            return True
        except ErrorTelegram as e:
            log.error("No se pudo responder a %s: %s", chat_id, e)
            return False

    # --- Arranque -------------------------------------------------------------

    def comprobar_arranque(self):
        yo = self.api.llamar("getMe")
        self.bot_id = yo["id"]
        log.info("Bot @%s (id %s) arrancando, versión %s", yo.get("username"), self.bot_id, version_instalada())
        # Con un webhook activo getUpdates no funciona; este bot no usa webhook.
        self.api.llamar("deleteWebhook")
        pausa = db.pausa_desde(self.con)
        if pausa is not None:
            self.avisar(f"⏸️ Arranco EN PAUSA (desde las {self._hora(pausa)}): no acepto a nadie "
                        "hasta que escribas /reanudar.", clave="pausa_arranque")
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
        elif "callback_query" in update:
            self._boton(update["callback_query"])

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

        pausa = db.pausa_desde(self.con)
        if pausa is not None:
            # El dueño lo ha parado con /pausar: ni bienvenida ni aceptación.
            # La solicitud se queda pendiente para que la acepte él a mano.
            log.info("Solicitud de %s: bot en pausa, se queda pendiente", uid)
            with self.con:
                db.registrar_evento(self.con, ahora, "solicitud_en_pausa", uid)
            self.avisar("⏸️ Ha llegado una solicitud y estoy en pausa: la dejo pendiente en el canal "
                        "para que la aceptes tú. De las siguientes no te aviso (salen en el "
                        "resumen). Para volver a aceptar: /reanudar", clave=f"pausa:{pausa}")
            return

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
        # El texto y su tipo: los que haya puesto el dueño con /textos, o los
        # de partida.
        tipo = textos.tipo_bienvenida(self.con)
        try:
            self.api.llamar(
                "sendMessage",
                chat_id=sol.get("user_chat_id", uid),
                text=textos.actual(self.con, "bienvenida"),
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
            db.marcar_bienvenida(self.con, uid, ahora, tipo)
            db.registrar_evento(self.con, ahora, "bienvenida_enviada", uid, tipo_mensaje=tipo)
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
        if self.cfg.propietario_id is None and self.cfg.canal_id is None:
            # Puesta en marcha (aún sin dueño ni canal): al abrir el bot por
            # primera vez Telegram envía /start ("Iniciar"); se contesta con
            # el id en vez de con la respuesta "escríbeme" de los clientes.
            self._responder(uid, f"🛠️ Bot en puesta en marcha.\nTu id de Telegram es: {uid}\n"
                                 "Ponlo en CAPTACION_PROPIETARIO_ID y reinicia el bot.")
            return
        if uid == self.cfg.propietario_id:
            if comando is None and textos.edicion(self.con, self.reloj()) is not None:
                self._texto_nuevo(msg)  # está cambiando un texto con /textos
            else:
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
        # A quien ya tiene la apuesta de regalo (el dueño le envió un enlace
        # de venta) no se le vuelve a hacer la pregunta de la bienvenida.
        con_gratuita = fila["enlace_venta_ts"] is not None
        clave = "redireccion_gratuita" if con_gratuita else "redireccion"
        try:
            self.api.llamar("sendMessage", chat_id=uid, text=textos.actual(self.con, clave),
                            reply_markup=mensajes.teclado_redireccion(self.cfg.perfil, con_gratuita))
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
        elif comando == "/textos":
            self._menu_textos()
            return
        elif comando == "/cancelar":
            if textos.edicion(self.con, ahora) is None:
                texto = "No estabas cambiando ningún texto."
            else:
                textos.terminar(self.con)
                texto = "❌ Cancelado: se queda como estaba."
        elif comando == "/dudas":
            self._responder(self.cfg.propietario_id,
                            "👀 Así ve el menú quien escribe al bot (y aún no tiene la gratuita):")
            texto, teclado = self._pantalla_dudas(None, con_gratuita=False)
            self._responder(self.cfg.propietario_id, texto, teclado)
            return
        elif comando == "/pausar":
            texto = self._pausar(ahora)
        elif comando == "/reanudar":
            texto = self._reanudar(ahora)
        elif comando == "/estado":
            con_bienvenida = self.con.execute(
                "SELECT COUNT(*) FROM usuarios WHERE bienvenida_ts IS NOT NULL").fetchone()[0]
            canal = self.cfg.canal_id if self.cfg.canal_id is not None else "sin configurar (no acepto a nadie)"
            pausa = db.pausa_desde(self.con)
            cabecera = ("✅ Funcionando." if pausa is None else
                        f"⏸️ Funcionando, pero EN PAUSA desde las {self._hora(pausa)}: no acepto a "
                        "nadie. Para volver: /reanudar")
            texto = (f"{cabecera}\nCanal: {canal}\nBotones apuntan a: @{self.cfg.perfil}\n"
                     f"Personas que ya tienen bienvenida: {con_bienvenida}\n"
                     f"Versión: {version_instalada()}")
        elif comando == "/start":
            texto = "✅ Bot de captación activo. Aquí te llegarán los avisos y los resúmenes.\n\n" + AYUDA_PROPIETARIO
        else:
            texto = AYUDA_PROPIETARIO
        self._responder(self.cfg.propietario_id, texto)

    # --- Botones con respuesta (dudas frecuentes y /textos) --------------------

    def _boton(self, cq):
        # Hay que contestar siempre, o el botón se queda «cargando».
        try:
            self.api.llamar("answerCallbackQuery", callback_query_id=cq["id"])
        except ErrorTelegram as e:
            log.info("Telegram no aceptó la respuesta al botón: %s", e)
        datos = cq.get("data") or ""
        uid = (cq.get("from") or {}).get("id")
        if uid is None:
            return
        if datos == mensajes.CALLBACK_DUDAS or datos.startswith("faq:"):
            self._boton_dudas(cq, uid, datos)
        elif datos.startswith("txt") and uid == self.cfg.propietario_id:
            self._boton_textos(datos)

    def _pantalla_dudas(self, tema, con_gratuita):
        """(texto, teclado) del menú de dudas (tema None) o de un tema."""
        if tema is None:
            return textos.actual(self.con, "faq_menu"), mensajes.teclado_menu_faq()
        pie = textos.actual(self.con, "faq_pie_gratuita" if con_gratuita else "faq_pie")
        texto = mensajes.mensaje_tema(tema, textos.actual(self.con, f"faq:{tema}"), pie)
        return texto, mensajes.teclado_tema(tema, self.cfg.perfil, con_gratuita)

    def _boton_dudas(self, cq, uid, datos):
        if datos in (mensajes.CALLBACK_DUDAS, mensajes.CALLBACK_MENU):
            tema = None
        else:
            tema = datos.split(":", 1)[1]
            if tema not in mensajes.FAQ:
                return
        fila = db.obtener_usuario(self.con, uid)
        con_gratuita = fila is not None and fila["enlace_venta_ts"] is not None
        texto, teclado = self._pantalla_dudas(tema, con_gratuita)
        if datos == mensajes.CALLBACK_DUDAS:
            # Desde la respuesta del bot: el menú va en un mensaje nuevo (la
            # respuesta, con sus botones, se queda donde está).
            hecho = self._responder(uid, texto, teclado)
        else:
            hecho = self._editar(cq.get("message"), uid, texto, teclado)
        if hecho and uid != self.cfg.propietario_id:
            ahora = self.reloj()
            with self.con:
                db.actualizar_datos_usuario(self.con, ahora, cq["from"])
                db.registrar_evento(self.con, ahora, "faq", uid, tema=tema or "menu")

    def _editar(self, mensaje, chat_id, texto, teclado):
        """Cambia el mensaje de las dudas al navegar. Si no se puede (p. ej.
        es muy antiguo), lo envía de nuevo."""
        if not mensaje or "message_id" not in mensaje:
            return self._responder(chat_id, texto, teclado)
        try:
            self.api.llamar("editMessageText", chat_id=mensaje["chat"]["id"], message_id=mensaje["message_id"],
                            text=texto, reply_markup=teclado)
            return True
        except ErrorTelegram as e:
            if "not modified" in e.descripcion.lower():
                return True  # ha pulsado el tema que ya estaba viendo
            log.info("No se pudo cambiar el mensaje (%s): lo envío de nuevo", e.descripcion)
            return self._responder(chat_id, texto, teclado)

    # --- Cambiar textos (/textos, solo el dueño) -------------------------------

    def _menu_textos(self):
        textos.terminar(self.con)
        filas = [[{"text": nombre, "callback_data": f"txt:{clave}"}]
                 for clave, (nombre, _) in mensajes.TEXTOS_EDITABLES.items()]
        self._responder(self.cfg.propietario_id, "✏️ ¿Qué texto quieres cambiar?", {"inline_keyboard": filas})

    def _boton_textos(self, datos):
        ahora = self.reloj()
        accion, _, clave = datos.partition(":")
        if accion in ("txt", "txt_ant", "txt_orig") and clave not in mensajes.TEXTOS_EDITABLES:
            return
        if accion == "txt":
            self._empezar_edicion(clave, ahora)
        elif accion in ("txt_ant", "txt_orig"):
            texto = textos.anterior(self.con, clave) if accion == "txt_ant" else textos.original(clave)
            if texto is None or texto == textos.actual(self.con, clave):
                self._responder(self.cfg.propietario_id, "Ya está así: no hay nada que cambiar.")
                return
            textos.empezar_edicion(self.con, clave, ahora)
            self._vista_previa(textos.edicion(self.con, ahora), texto, ahora)
        elif accion == "txt_ok":
            self._guardar_texto(ahora)
        elif accion == "txt_no":
            textos.terminar(self.con)
            self._responder(self.cfg.propietario_id, "❌ Cancelado: se queda como estaba.")

    def _empezar_edicion(self, clave, ahora):
        textos.empezar_edicion(self.con, clave, ahora)
        dueno = self.cfg.propietario_id
        actual = textos.actual(self.con, clave)
        self._responder(dueno, actual)  # tal cual, para que lo copie y lo retoque
        botones = []
        if textos.anterior(self.con, clave) is not None:
            botones.append([{"text": "↩️ Volver al anterior", "callback_data": f"txt_ant:{clave}"}])
        if actual != textos.original(clave):
            botones.append([{"text": "♻️ Volver al original", "callback_data": f"txt_orig:{clave}"}])
        botones.append([{"text": "❌ Cancelar", "callback_data": "txt_no"}])
        self._responder(dueno, f"✏️ Arriba tienes el texto actual de «{textos.nombre(clave)}». Cópialo, "
                               "cámbialo y mándamelo.\nPara poner negritas, usa la negrita de Telegram "
                               "(selecciona el texto → Negrita).\nPara dejarlo como está: /cancelar",
                        {"inline_keyboard": botones})

    def _texto_nuevo(self, msg):
        ahora = self.reloj()
        edicion = textos.edicion(self.con, ahora)
        dueno = self.cfg.propietario_id
        if msg.get("text") is None:
            self._responder(dueno, "Mándamelo como texto, sin fotos ni archivos. O /cancelar.")
            return
        nuevo = textos.con_negritas(msg["text"], msg.get("entities"))
        fallo = textos.problema(nuevo)
        if fallo:
            self._responder(dueno, f"⚠️ Ese texto {fallo}. Mándamelo otra vez o /cancelar.")
        elif nuevo == textos.actual(self.con, edicion["clave"]):
            self._responder(dueno, "Es igual que el actual: no hay nada que cambiar. Mándame otro o /cancelar.")
        else:
            self._vista_previa(edicion, nuevo, ahora)

    def _vista_previa(self, edicion, nuevo, ahora):
        textos.preparar(self.con, edicion, nuevo, ahora)
        clave = edicion["clave"]
        dueno = self.cfg.propietario_id
        self._responder(dueno, "👀 Así lo verán:")
        texto, teclado = self._como_lo_veran(clave, nuevo)
        self._responder(dueno, texto, teclado)
        aviso = ("\nSerá una versión nueva de la bienvenida: en la hoja podrás comparar cuál hace que "
                 "te escriban más." if clave == "bienvenida" else "")
        self._responder(dueno, f"¿Guardo el texto nuevo de «{textos.nombre(clave)}»?{aviso}",
                        {"inline_keyboard": [[{"text": "✅ Guardar", "callback_data": "txt_ok"},
                                              {"text": "❌ Cancelar", "callback_data": "txt_no"}]]})

    def _como_lo_veran(self, clave, texto):
        perfil = self.cfg.perfil
        if clave == "bienvenida":
            return texto, mensajes.teclado_respuesta(perfil)
        if clave in ("redireccion", "redireccion_gratuita"):
            return texto, mensajes.teclado_redireccion(perfil, clave == "redireccion_gratuita")
        if clave == "faq_menu":
            return texto, mensajes.teclado_menu_faq()
        if clave in ("faq_pie", "faq_pie_gratuita"):
            # El final se ve debajo de un tema cualquiera (el primero del menú).
            tema = mensajes.FAQ_MENU[0]
            return (mensajes.mensaje_tema(tema, textos.actual(self.con, f"faq:{tema}"), texto),
                    mensajes.teclado_tema(tema, perfil, clave == "faq_pie_gratuita"))
        tema = clave.split(":", 1)[1]
        return (mensajes.mensaje_tema(tema, texto, textos.actual(self.con, "faq_pie")),
                mensajes.teclado_tema(tema, perfil, False))

    def _guardar_texto(self, ahora):
        dueno = self.cfg.propietario_id
        edicion = textos.edicion(self.con, ahora)
        if edicion is None or edicion["nuevo"] is None:
            self._responder(dueno, "⌛ Ese cambio ya no está pendiente (se canceló o pasó media hora). "
                                   "Vuelve a empezar con /textos.")
            return
        tipo = textos.guardar(self.con, edicion["clave"], edicion["nuevo"], ahora)
        textos.terminar(self.con)
        log.info("Texto «%s» cambiado por el dueño", edicion["clave"])
        texto = f"✅ Guardado. Desde ahora se usa el texto nuevo de «{textos.nombre(edicion['clave'])}»."
        if tipo:
            texto += f"\nEsta bienvenida es la versión {tipo} (así sale en la hoja)."
        self._responder(dueno, texto)

    # --- Freno de emergencia (/pausar y /reanudar) ---------------------------

    def _hora(self, ts):
        return f"{datetime.fromtimestamp(ts, self.cfg.tz):%H:%M del %d.%m}"

    def _pausar(self, ahora):
        pausa = db.pausa_desde(self.con)
        if pausa is not None:
            return f"⏸️ Ya estaba en pausa desde las {self._hora(pausa)}. Para volver a aceptar: /reanudar"
        with self.con:
            db.guardar_estado(self.con, "pausa_desde", int(ahora))
            db.registrar_evento(self.con, ahora, "pausa", None)
        log.warning("Bot EN PAUSA por orden del dueño")
        return ("⏸️ En pausa: ya no acepto solicitudes ni envío bienvenidas. Las que lleguen se "
                "quedan pendientes en el canal para que las aceptes tú a mano.\n"
                "Para volver a aceptar: /reanudar")

    def _reanudar(self, ahora):
        pausa = db.pausa_desde(self.con)
        if pausa is None:
            return "▶️ No estaba en pausa: sigo aceptando solicitudes."
        pendientes = self.con.execute(
            "SELECT COUNT(DISTINCT user_id) FROM eventos WHERE tipo = 'solicitud_en_pausa' AND ts >= ?",
            (pausa,)).fetchone()[0]
        with self.con:
            db.guardar_estado(self.con, "pausa_desde", "")
            db.registrar_evento(self.con, ahora, "reanudacion", None)
        log.warning("Bot REANUDADO por orden del dueño")
        texto = "▶️ Vuelvo a aceptar solicitudes con la bienvenida."
        if pendientes:
            llegaron = "llegó 1 solicitud" if pendientes == 1 else f"llegaron {pendientes} solicitudes"
            texto += f"\nDurante la pausa {llegaron}: siguen pendientes en el canal, acéptalas tú a mano."
        return texto

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
