import json
import unittest
from urllib.parse import quote

from premier_captacion import db, mensajes, textos
from premier_captacion.bot import BotCaptacion
from premier_captacion.telegram_api import ErrorRed, ErrorTelegram

from .apoyo import (CANAL, PERFIL, PROPIETARIO, APIFalsa, config, conexion, update_boton,
                    update_mensaje, update_solicitud, update_texto_con_formato)


class Reloj:
    def __init__(self, ahora=1_000_000):
        self.ahora = ahora

    def __call__(self):
        return self.ahora


def tipos_eventos(con, uid=None):
    sql = "SELECT tipo FROM eventos" + (" WHERE user_id = ?" if uid else "") + " ORDER BY id"
    return [f["tipo"] for f in con.execute(sql, (uid,) if uid else ())]


class Base(unittest.TestCase):
    def setUp(self):
        self.api = APIFalsa()
        self.con = conexion()
        self.addCleanup(self.con.close)
        self.reloj = Reloj()
        self.dormidas = []
        self.bot = self.crear_bot()

    def crear_bot(self, **cambios_config):
        return BotCaptacion(config(**cambios_config), self.api, self.con,
                            reloj=self.reloj, dormir=self.dormidas.append)


class TestSolicitudes(Base):
    def test_primera_vez_envia_bienvenida_y_despues_acepta(self):
        self.bot.procesar(update_solicitud(1, uid=500))

        self.assertEqual(self.api.metodos(), ["sendMessage", "approveChatJoinRequest"])
        envio = self.api.llamadas[0][1]
        self.assertEqual(envio["chat_id"], 500)
        self.assertEqual(envio["text"], mensajes.TEXTO_BIENVENIDA)
        self.assertEqual(envio["reply_markup"], mensajes.teclado_respuesta(PERFIL))
        self.assertEqual(self.api.llamadas[1][1], {"chat_id": CANAL, "user_id": 500})

        fila = db.obtener_usuario(self.con, 500)
        self.assertEqual(fila["bienvenida_tipo"], mensajes.TIPO_BIENVENIDA_BOT)
        self.assertEqual(fila["enlace_entrada"], "landing")
        self.assertEqual(fila["username"], "pepe")
        self.assertEqual(tipos_eventos(self.con), ["solicitud", "bienvenida_enviada", "aceptada"])

    def test_si_vuelve_se_acepta_sin_volver_a_escribirle(self):
        self.bot.procesar(update_solicitud(1, uid=500))
        self.api.llamadas.clear()
        self.reloj.ahora += 90 * 24 * 3600  # meses después
        self.bot.procesar(update_solicitud(2, uid=500, fecha=self.reloj.ahora, enlace_nombre="otro"))

        self.assertEqual(self.api.metodos(), ["approveChatJoinRequest"])
        fila = db.obtener_usuario(self.con, 500)
        self.assertEqual(fila["num_solicitudes"], 2)
        self.assertEqual(fila["enlace_entrada"], "landing")  # se guarda el de la primera vez
        self.assertEqual(tipos_eventos(self.con)[-3:], ["solicitud", "ya_recibida", "aceptada"])

    def test_fuera_de_plazo_se_acepta_sin_bienvenida_y_avisa_una_vez_por_lote(self):
        self.reloj.ahora = 1_000_000 + 400  # la solicitud lleva 400 s esperando
        self.api.respuestas["getUpdates"] = [update_solicitud(1, uid=500), update_solicitud(2, uid=501)]
        vueltas = iter([True, False])
        self.bot.bucle(seguir=lambda: next(vueltas))

        self.assertEqual(self.api.envios_a(500), [])
        self.assertEqual(self.api.envios_a(501), [])
        self.assertEqual(self.api.metodos().count("approveChatJoinRequest"), 2)
        avisos = self.api.envios_a(PROPIETARIO)
        self.assertEqual(len(avisos), 1)
        self.assertIn("2 solicitud(es)", avisos[0]["text"])
        self.assertIsNone(db.obtener_usuario(self.con, 500)["bienvenida_ts"])
        self.assertIn("bienvenida_fallida", tipos_eventos(self.con, 500))

    def test_si_falla_la_bienvenida_se_acepta_igual_y_puede_recibirla_otra_vez(self):
        self.api.fallos["sendMessage"] = [ErrorTelegram("sendMessage", 403, "Forbidden: bot can't initiate conversation")]
        self.bot.procesar(update_solicitud(1, uid=500))

        self.assertIn("approveChatJoinRequest", self.api.metodos())
        self.assertIsNone(db.obtener_usuario(self.con, 500)["bienvenida_ts"])
        avisos = self.api.envios_a(PROPIETARIO)
        self.assertEqual(len(avisos), 1)
        self.assertIn("No he podido enviar la bienvenida a Pepe (@pepe)", avisos[0]["text"])

        # Como nunca la recibió, si vuelve a solicitar se le envía.
        self.api.llamadas.clear()
        self.reloj.ahora += 3600
        self.bot.procesar(update_solicitud(2, uid=500, fecha=self.reloj.ahora))
        self.assertEqual(self.api.envios_a(500)[0]["text"], mensajes.TEXTO_BIENVENIDA)

    def test_un_mismo_error_repetido_solo_avisa_una_vez(self):
        error = ErrorTelegram("sendMessage", 400, "Bad Request: algo")
        # Orden de los sendMessage: bienvenida a 500 (falla), aviso al
        # propietario (va bien), bienvenida a 501 (falla igual).
        self.api.fallos["sendMessage"] = [error, None, error]
        self.bot.procesar(update_solicitud(1, uid=500))
        self.bot.procesar(update_solicitud(2, uid=501))
        self.assertEqual(len(self.api.envios_a(501)), 1)
        self.assertEqual(self.api.fallos["sendMessage"], [])
        self.assertEqual(len(self.api.envios_a(PROPIETARIO)), 1)

    def test_no_toca_solicitudes_de_otros_chats(self):
        self.bot.procesar(update_solicitud(1, uid=500, chat_id=-1009999))
        self.assertNotIn("approveChatJoinRequest", self.api.metodos())
        self.assertEqual(self.api.envios_a(500), [])
        self.assertEqual(len(self.api.envios_a(PROPIETARIO)), 1)

    def test_sin_canal_configurado_no_acepta_y_dice_el_id(self):
        bot = self.crear_bot(canal_id=None)
        bot.procesar(update_solicitud(1, uid=500))
        self.assertNotIn("approveChatJoinRequest", self.api.metodos())
        self.assertIn(f"CAPTACION_CANAL_ID={CANAL}", self.api.envios_a(PROPIETARIO)[0]["text"])

    def test_corte_de_red_no_duplica_la_solicitud(self):
        self.api.fallos["sendMessage"] = [ErrorRed("sendMessage: timeout")]
        with self.assertRaises(ErrorRed):
            self.bot.procesar(update_solicitud(7, uid=500))
        # Se repite la misma actualización cuando vuelve la red.
        self.bot.procesar(update_solicitud(7, uid=500))

        self.assertEqual(db.obtener_usuario(self.con, 500)["num_solicitudes"], 1)
        self.assertEqual(tipos_eventos(self.con).count("solicitud"), 1)
        self.assertIsNotNone(db.obtener_usuario(self.con, 500)["bienvenida_ts"])
        self.assertEqual(self.api.metodos().count("approveChatJoinRequest"), 1)

    def test_errores_al_aceptar(self):
        casos = [
            ("Bad Request: USER_ALREADY_PARTICIPANT", "aceptada", 0),
            ("Bad Request: HIDE_REQUESTER_MISSING", "aceptacion_fallida", 0),
            ("Bad Request: USER_CHANNELS_TOO_MUCH", "aceptacion_fallida", 1),
        ]
        for i, (descripcion, evento, avisos) in enumerate(casos):
            with self.subTest(descripcion):
                self.api.llamadas.clear()
                self.api.fallos["approveChatJoinRequest"] = [ErrorTelegram("approve", 400, descripcion)]
                uid = 600 + i
                self.bot.procesar(update_solicitud(10 + i, uid=uid))
                self.assertEqual(tipos_eventos(self.con, uid)[-1], evento)
                self.assertEqual(len(self.api.envios_a(PROPIETARIO)), avisos)


class TestMensajesAlBot(Base):
    def test_responde_escribeme_con_los_dos_botones(self):
        self.bot.procesar(update_mensaje(1, uid=500, texto="Es mi primera vez"))
        envios = self.api.envios_a(500)
        self.assertEqual(len(envios), 1)
        self.assertEqual(envios[0]["text"], mensajes.TEXTO_REDIRECCION)
        self.assertEqual(envios[0]["reply_markup"], mensajes.teclado_redireccion(PERFIL, False))

    def test_rafaga_una_sola_respuesta_pero_vuelve_a_responder_despues(self):
        for i in range(3):
            self.bot.procesar(update_mensaje(i, uid=500))
        self.assertEqual(len(self.api.envios_a(500)), 1)
        self.reloj.ahora += 61
        self.bot.procesar(update_mensaje(9, uid=500))
        self.assertEqual(len(self.api.envios_a(500)), 2)
        self.assertEqual(tipos_eventos(self.con, 500).count("mensaje_al_bot"), 4)

    def test_miid(self):
        self.bot.procesar(update_mensaje(1, uid=500, texto="/miid"))
        self.bot.procesar(update_mensaje(2, uid=500, texto="/miid@bot_prueba"))
        self.assertEqual([e["text"] for e in self.api.envios_a(500)], ["Tu id de Telegram es: 500"] * 2)

    def test_en_puesta_en_marcha_iniciar_devuelve_el_id(self):
        bot = self.crear_bot(propietario_id=None, canal_id=None)
        bot.procesar(update_mensaje(1, uid=500, texto="/start"))
        envios = self.api.envios_a(500)
        self.assertEqual(len(envios), 1)
        self.assertIn("Tu id de Telegram es: 500", envios[0]["text"])
        self.assertNotIn("reply_markup", envios[0])

    def test_con_canal_configurado_iniciar_es_un_cliente_mas(self):
        # Si ya hay canal (aunque falte el dueño), quien escribe es un cliente.
        bot = self.crear_bot(propietario_id=None)
        bot.procesar(update_mensaje(1, uid=500, texto="/start"))
        self.assertEqual(self.api.envios_a(500)[0]["text"], mensajes.TEXTO_REDIRECCION)

    def test_el_propietario_recibe_comandos_no_redireccion(self):
        self.bot.procesar(update_mensaje(1, uid=PROPIETARIO, texto="/resumen"))
        self.bot.procesar(update_mensaje(2, uid=PROPIETARIO, texto="/estado"))
        self.bot.procesar(update_mensaje(3, uid=PROPIETARIO, texto="hola"))
        textos = [e["text"] for e in self.api.envios_a(PROPIETARIO)]
        self.assertTrue(textos[0].startswith("📊 Hoy"))
        self.assertTrue(textos[1].startswith("✅ Funcionando"))
        self.assertIn("Versión: ", textos[1])
        self.assertIn("/resumen", textos[2])
        self.assertNotIn(mensajes.TEXTO_REDIRECCION, textos)

    def test_ignora_grupos_y_bots(self):
        upd = update_mensaje(1, uid=500)
        upd["message"]["chat"]["type"] = "group"
        self.bot.procesar(upd)
        upd = update_mensaje(2, uid=501)
        upd["message"]["from"]["is_bot"] = True
        self.bot.procesar(upd)
        self.assertEqual(self.api.llamadas, [])


class TestPausa(Base):
    """Freno de emergencia: /pausar y /reanudar (solo el dueño)."""

    def orden(self, update_id, texto):
        self.bot.procesar(update_mensaje(update_id, uid=PROPIETARIO, texto=texto))
        return self.api.envios_a(PROPIETARIO)[-1]["text"]

    def test_en_pausa_no_da_la_bienvenida_ni_acepta_y_al_reanudar_vuelve(self):
        self.assertTrue(self.orden(1, "/pausar").startswith("⏸️ En pausa"))
        self.api.llamadas.clear()
        self.bot.procesar(update_solicitud(2, uid=500))
        self.bot.procesar(update_solicitud(3, uid=501))
        self.assertNotIn("approveChatJoinRequest", self.api.metodos())
        self.assertEqual(self.api.envios_a(500), [])  # ni bienvenida
        avisos = [e["text"] for e in self.api.envios_a(PROPIETARIO)]
        self.assertEqual(len(avisos), 1)  # solo avisa de la primera
        self.assertIn("pendiente", avisos[0])
        self.assertEqual(tipos_eventos(self.con, 500), ["solicitud", "solicitud_en_pausa"])
        self.assertIsNone(db.obtener_usuario(self.con, 500)["bienvenida_ts"])  # podrá recibirla luego
        self.assertIn("EN PAUSA", self.orden(4, "/estado"))
        self.assertIn("llegaron 2 solicitudes", self.orden(5, "/reanudar"))
        self.api.llamadas.clear()
        self.bot.procesar(update_solicitud(6, uid=502))
        self.assertEqual(self.api.metodos(), ["sendMessage", "approveChatJoinRequest"])

    def test_sigue_en_pausa_aunque_se_reinicie(self):
        self.orden(1, "/pausar")
        otro = self.crear_bot()  # misma base de datos, como tras un reinicio
        self.api.llamadas.clear()
        self.api.respuestas["getChatMember"] = {"status": "administrator", "can_invite_users": True}
        otro.comprobar_arranque()
        self.assertIn("Arranco EN PAUSA", self.api.envios_a(PROPIETARIO)[0]["text"])
        otro.procesar(update_solicitud(2, uid=500))
        self.assertNotIn("approveChatJoinRequest", self.api.metodos())

    def test_pausar_dos_veces_y_reanudar_sin_pausa(self):
        self.orden(1, "/pausar")
        self.assertIn("Ya estaba en pausa", self.orden(2, "/pausar"))
        self.assertEqual(self.orden(3, "/reanudar"), "▶️ Vuelvo a aceptar solicitudes con la bienvenida.")
        self.assertIn("No estaba en pausa", self.orden(4, "/reanudar"))
        self.assertEqual(tipos_eventos(self.con), ["pausa", "reanudacion"])

    def test_solo_el_dueno_puede_pausar(self):
        self.bot.procesar(update_mensaje(1, uid=500, texto="/pausar"))
        self.assertIsNone(db.pausa_desde(self.con))
        self.assertEqual(self.api.envios_a(500)[0]["text"], mensajes.TEXTO_REDIRECCION)

    def test_la_ayuda_lo_explica(self):
        self.assertIn("/pausar", self.orden(1, "hola"))


class TestDudas(Base):
    """Dudas frecuentes, desde la respuesta del bot a quien le escribe."""

    def con_gratuita(self, uid=500):
        with self.con:
            db.actualizar_datos_usuario(self.con, 1, {"id": uid, "first_name": "Ana"})
            db.actualizar_campos(self.con, uid, 1, enlace_venta_ts=5)

    def ediciones(self):
        return [p for m, p in self.api.llamadas if m == "editMessageText"]

    def temas_vistos(self):
        return [json.loads(f["detalle"])["tema"]
                for f in self.con.execute("SELECT detalle FROM eventos WHERE tipo = 'faq' ORDER BY id")]

    def test_la_respuesta_no_repite_la_pregunta_a_quien_ya_tiene_la_gratuita(self):
        self.con_gratuita(500)
        self.bot.procesar(update_mensaje(1, uid=500))
        envio = self.api.envios_a(500)[0]
        self.assertEqual(envio["text"], mensajes.TEXTO_REDIRECCION_CON_GRATUITA)
        botones = [b["text"] for fila in envio["reply_markup"]["inline_keyboard"] for b in fila]
        self.assertEqual(botones, ["✉️ Escríbeme", "📚 Dudas frecuentes"])

    def test_menu_en_un_mensaje_nuevo_y_temas_en_el_mismo(self):
        self.bot.procesar(update_boton(1, "faq"))
        self.assertEqual(self.api.metodos(), ["answerCallbackQuery", "sendMessage"])
        menu = self.api.envios_a(500)[0]
        self.assertEqual((menu["text"], menu["reply_markup"]), (mensajes.FAQ_TITULO, mensajes.teclado_menu_faq()))
        self.bot.procesar(update_boton(2, "faq:casas"))
        tema = self.ediciones()[-1]
        self.assertEqual((tema["chat_id"], tema["message_id"]), (500, 77))
        self.assertTrue(tema["text"].startswith(mensajes.FAQ["casas"]["titulo"]))
        self.assertIn(mensajes.negrita("Betway"), tema["text"])
        self.assertTrue(tema["text"].endswith(mensajes.PIE_SIN_GRATUITA))
        datos = [b.get("callback_data") for fila in tema["reply_markup"]["inline_keyboard"] for b in fila]
        # El submenú, los dos botones de la bienvenida (enlaces) y volver.
        self.assertEqual(datos, ["faq:otras_casas", None, None, "faq:menu"])
        self.bot.procesar(update_boton(3, "faq:otras_casas"))
        self.assertIn(mensajes.negrita("Codere"), self.ediciones()[-1]["text"])
        self.bot.procesar(update_boton(4, "faq:menu"))
        self.assertEqual(self.ediciones()[-1]["text"], mensajes.FAQ_TITULO)
        self.assertEqual(self.temas_vistos(), ["menu", "casas", "otras_casas", "menu"])

    def test_con_la_gratuita_el_final_es_escribeme_sobre_ese_tema(self):
        self.con_gratuita(500)
        self.bot.procesar(update_boton(1, "faq:packs"))
        tema = self.ediciones()[0]
        self.assertTrue(tema["text"].endswith(mensajes.PIE_CON_GRATUITA))
        filas = tema["reply_markup"]["inline_keyboard"]
        self.assertIn(quote("Hola, tengo una duda sobre los packs", safe=""), filas[0][0]["url"])
        self.assertEqual(filas[-1][0]["callback_data"], "faq:menu")

    def test_mismo_tema_dos_veces_o_mensaje_que_ya_no_se_puede_cambiar(self):
        self.api.fallos["editMessageText"] = [
            ErrorTelegram("editMessageText", 400, "Bad Request: message is not modified"),
            ErrorTelegram("editMessageText", 400, "Bad Request: message can't be edited"),
        ]
        self.bot.procesar(update_boton(1, "faq:unidades"))
        self.assertEqual(self.api.envios_a(500), [])  # ya lo estaba viendo
        self.bot.procesar(update_boton(2, "faq:unidades"))
        self.assertEqual(len(self.api.envios_a(500)), 1)  # se le envía de nuevo
        self.assertTrue(self.api.envios_a(500)[0]["text"].startswith(mensajes.FAQ["unidades"]["titulo"]))

    def test_siempre_contesta_al_boton_aunque_falle_o_no_lo_conozca(self):
        self.api.fallos["answerCallbackQuery"] = [ErrorTelegram("answerCallbackQuery", 400, "query is too old")]
        self.bot.procesar(update_boton(1, "faq:no_existe"))
        self.bot.procesar(update_boton(2, "otra_cosa"))
        self.assertEqual(self.api.metodos(), ["answerCallbackQuery", "answerCallbackQuery"])
        self.assertEqual(tipos_eventos(self.con), [])

    def test_el_dueno_las_ve_con_dudas_y_no_cuenta(self):
        self.bot.procesar(update_mensaje(1, uid=PROPIETARIO, texto="/dudas"))
        self.assertEqual(self.api.envios_a(PROPIETARIO)[1]["text"], mensajes.FAQ_TITULO)
        self.bot.procesar(update_boton(2, "faq:bank", uid=PROPIETARIO))
        self.assertEqual(tipos_eventos(self.con), [])


class TestTextos(Base):
    """El dueño cambia los textos desde el bot con /textos."""

    def orden(self, update_id, texto):
        self.bot.procesar(update_mensaje(update_id, uid=PROPIETARIO, texto=texto))
        return self.api.envios_a(PROPIETARIO)[-1]

    def boton(self, update_id, datos, uid=PROPIETARIO):
        self.bot.procesar(update_boton(update_id, datos, uid=uid))
        envios = self.api.envios_a(PROPIETARIO)
        return envios[-1] if envios else None

    def cambiar(self, update_id, clave, texto):
        self.boton(update_id, f"txt:{clave}")
        self.orden(update_id + 1, texto)
        return self.boton(update_id + 2, "txt_ok")

    def test_cambiar_un_tema_con_negritas_de_telegram(self):
        menu = self.orden(1, "/textos")
        datos = [fila[0]["callback_data"] for fila in menu["reply_markup"]["inline_keyboard"]]
        self.assertEqual(datos, [f"txt:{clave}" for clave in mensajes.TEXTOS_EDITABLES])
        self.boton(2, "txt:faq:packs")
        envios = self.api.envios_a(PROPIETARIO)
        self.assertEqual(envios[-2]["text"], mensajes.FAQ["packs"]["texto"])  # el actual, para copiarlo
        self.assertIn("/cancelar", envios[-1]["text"])
        self.bot.procesar(update_texto_con_formato(3, PROPIETARIO, "Packs con garantía total", negritas=[(10, 8)]))
        nuevo = "Packs con " + mensajes.negrita("garantía") + " total"
        envios = self.api.envios_a(PROPIETARIO)
        self.assertEqual(envios[-3]["text"], "👀 Así lo verán:")
        self.assertIn(nuevo, envios[-2]["text"])
        confirmar = envios[-1]["reply_markup"]["inline_keyboard"][0]
        self.assertEqual([b["callback_data"] for b in confirmar], ["txt_ok", "txt_no"])
        # Hasta que no lo guarda, los clientes ven el de antes.
        self.bot.procesar(update_boton(4, "faq:packs", uid=500))
        ediciones = [p for m, p in self.api.llamadas if m == "editMessageText"]
        self.assertNotIn(nuevo, ediciones[-1]["text"])
        self.assertTrue(self.boton(5, "txt_ok")["text"].startswith("✅ Guardado"))
        self.bot.procesar(update_boton(6, "faq:packs", uid=500))
        ediciones = [p for m, p in self.api.llamadas if m == "editMessageText"]
        self.assertIn(nuevo, ediciones[-1]["text"])

    def test_cambiar_la_bienvenida_es_una_version_nueva(self):
        self.boton(1, "txt:bienvenida")
        self.orden(2, "¡Hola! Bienvenido 🐕")
        self.assertIn("versión nueva", self.api.envios_a(PROPIETARIO)[-1]["text"])
        self.assertIn("bot_b_v2", self.boton(3, "txt_ok")["text"])
        self.api.llamadas.clear()
        self.bot.procesar(update_solicitud(4, uid=500))
        envio = self.api.envios_a(500)[0]
        self.assertEqual(envio["text"], "¡Hola! Bienvenido 🐕")
        self.assertEqual(envio["reply_markup"], mensajes.teclado_respuesta(PERFIL))  # los botones no cambian
        self.assertEqual(db.obtener_usuario(self.con, 500)["bienvenida_tipo"], "bot_b_v2")
        # Vuelve al original, y con él al tipo de partida.
        self.boton(5, "txt:bienvenida")
        self.boton(6, "txt_orig:bienvenida")
        self.boton(7, "txt_ok")
        self.bot.procesar(update_solicitud(8, uid=501))
        self.assertEqual(self.api.envios_a(501)[0]["text"], mensajes.TEXTO_BIENVENIDA)
        self.assertEqual(db.obtener_usuario(self.con, 501)["bienvenida_tipo"], mensajes.TIPO_BIENVENIDA_BOT)

    def test_cancelar_y_textos_que_no_valen(self):
        self.boton(1, "txt:faq_menu")
        self.assertEqual(self.orden(2, "/cancelar")["text"], "❌ Cancelado: se queda como estaba.")
        self.assertEqual(self.orden(3, "/cancelar")["text"], "No estabas cambiando ningún texto.")
        self.assertIn("/textos", self.orden(4, "hola")["text"])  # sin cambio en curso: la ayuda
        self.boton(5, "txt:faq_menu")
        self.assertIn("igual que el actual", self.orden(6, mensajes.FAQ_TITULO)["text"])
        self.assertIn("vacío", self.orden(7, "   ")["text"])
        self.assertIn("demasiado largo", self.orden(8, "x" * 3001)["text"])
        foto = update_mensaje(9, uid=PROPIETARIO)
        del foto["message"]["text"]
        self.bot.procesar(foto)
        self.assertIn("como texto", self.api.envios_a(PROPIETARIO)[-1]["text"])
        # En medio de un cambio, las órdenes siguen funcionando.
        self.assertTrue(self.orden(10, "/estado")["text"].startswith("✅ Funcionando"))
        self.assertEqual(self.boton(11, "txt_no")["text"], "❌ Cancelado: se queda como estaba.")
        self.assertEqual(textos.actual(self.con, "faq_menu"), mensajes.FAQ_TITULO)

    def test_si_pasa_media_hora_hay_que_empezar_otra_vez(self):
        self.boton(1, "txt:faq:bank")
        self.orden(2, "Texto nuevo del bank")
        self.reloj.ahora += 31 * 60
        self.assertIn("ya no está pendiente", self.boton(3, "txt_ok")["text"])
        self.assertEqual(textos.actual(self.con, "faq:bank"), mensajes.FAQ["bank"]["texto"])

    def test_volver_al_anterior(self):
        self.cambiar(10, "faq:unidades", "Versión A")
        self.cambiar(20, "faq:unidades", "Versión B")
        self.boton(30, "txt:faq:unidades")
        filas = self.api.envios_a(PROPIETARIO)[-1]["reply_markup"]["inline_keyboard"]
        self.assertEqual([f[0]["callback_data"] for f in filas],
                         ["txt_ant:faq:unidades", "txt_orig:faq:unidades", "txt_no"])
        self.boton(31, "txt_ant:faq:unidades")
        self.boton(32, "txt_ok")
        self.assertEqual(textos.actual(self.con, "faq:unidades"), "Versión A")

    def test_un_cliente_no_puede_cambiar_textos(self):
        self.bot.procesar(update_boton(1, "txt:bienvenida", uid=500))
        self.bot.procesar(update_mensaje(2, uid=500, texto="/textos"))
        self.assertEqual(self.api.envios_a(PROPIETARIO), [])
        self.assertIsNone(textos.edicion(self.con, self.reloj()))
        self.assertEqual(self.api.envios_a(500)[0]["text"], mensajes.TEXTO_REDIRECCION)


class TestPermisos(Base):
    def cambio(self, estado, chat_id=CANAL, puede_invitar=True):
        return {"update_id": 1, "my_chat_member": {
            "chat": {"id": chat_id, "type": "channel", "title": "Canal de prueba"},
            "new_chat_member": {"status": estado, "can_invite_users": puede_invitar},
        }}

    def test_al_hacerlo_admin_sin_canal_configurado_dice_el_id(self):
        self.crear_bot(canal_id=None).procesar(self.cambio("administrator"))
        self.assertIn(f"CAPTACION_CANAL_ID={CANAL}", self.api.envios_a(PROPIETARIO)[0]["text"])

    def test_admin_sin_permiso_de_anadir(self):
        self.bot.procesar(self.cambio("administrator", puede_invitar=False))
        self.assertIn("Añadir suscriptores", self.api.envios_a(PROPIETARIO)[0]["text"])

    def test_deja_de_ser_admin_del_canal(self):
        self.bot.procesar(self.cambio("left"))
        self.assertTrue(self.api.envios_a(PROPIETARIO)[0]["text"].startswith("🚨"))


class TestArranqueYBucle(Base):
    def test_arranque_avisa_si_no_tiene_permisos(self):
        self.api.respuestas["getChatMember"] = {"status": "member"}
        self.bot.comprobar_arranque()
        self.assertEqual(self.bot.bot_id, 999)
        self.assertTrue(self.api.envios_a(PROPIETARIO)[0]["text"].startswith("🚨"))

    def test_arranque_correcto_no_avisa(self):
        self.api.respuestas["getChatMember"] = {"status": "administrator", "can_invite_users": True}
        self.bot.comprobar_arranque()
        self.assertEqual(self.api.envios_a(PROPIETARIO), [])

    def test_guarda_el_offset_y_reintenta_con_espera_si_cae_la_red(self):
        self.api.fallos["getUpdates"] = [ErrorRed("x"), ErrorRed("x"), None]
        self.api.respuestas["getUpdates"] = [update_mensaje(41, uid=500)]
        vueltas = iter([True, True, True, False])
        self.bot.bucle(seguir=lambda: next(vueltas))
        self.assertEqual(self.dormidas, [2, 4])
        self.assertEqual(db.leer_estado(self.con, "offset"), "42")
        ultimo_get = [p for m, p in self.api.llamadas if m == "getUpdates"][-1]
        self.assertIsNone(ultimo_get["offset"])

    def test_si_cae_la_red_a_mitad_no_avanza_el_offset(self):
        self.api.respuestas["getUpdates"] = [update_solicitud(50, uid=500), update_solicitud(51, uid=501)]
        self.api.fallos["sendMessage"] = [None, ErrorRed("x")]
        vueltas = iter([True, False])
        self.bot.bucle(seguir=lambda: next(vueltas))
        self.assertEqual(db.leer_estado(self.con, "offset"), "51")

    def test_un_error_inesperado_no_bloquea_el_bot(self):
        # Solicitud malformada (sin "from"): provoca un KeyError dentro del bot.
        self.api.respuestas["getUpdates"] = [{"update_id": 60, "chat_join_request": {"chat": {"id": CANAL}}}]
        vueltas = iter([True, False])
        self.bot.bucle(seguir=lambda: next(vueltas))
        self.assertEqual(db.leer_estado(self.con, "offset"), "61")
        self.assertTrue(self.api.envios_a(PROPIETARIO)[0]["text"].startswith("🚨"))


if __name__ == "__main__":
    unittest.main()
