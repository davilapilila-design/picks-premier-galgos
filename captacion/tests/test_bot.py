import unittest

from premier_captacion import db, mensajes
from premier_captacion.bot import BotCaptacion
from premier_captacion.telegram_api import ErrorRed, ErrorTelegram

from .apoyo import (CANAL, PERFIL, PROPIETARIO, APIFalsa, config, conexion,
                    update_mensaje, update_solicitud)


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
        self.assertEqual(envios[0]["reply_markup"], mensajes.teclado_respuesta(PERFIL))

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
