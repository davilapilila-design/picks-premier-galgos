import os
import tempfile
import unittest
from datetime import date, datetime
from unittest import mock
from zoneinfo import ZoneInfo

from premier_captacion import db, mensajes, resumen

from .apoyo import conexion

MADRID = ZoneInfo("Europe/Madrid")


def ts(*fecha_hora):
    return int(datetime(*fecha_hora, tzinfo=MADRID).timestamp())


class Base(unittest.TestCase):
    def setUp(self):
        self.con = conexion()
        self.addCleanup(self.con.close)

    def evento(self, momento, tipo, uid, **detalle):
        with self.con:
            db.registrar_evento(self.con, momento, tipo, uid, **detalle)


class TestDiario(Base):
    def setUp(self):
        super().setUp()
        self.evento(ts(2026, 10, 13, 23, 59), "solicitud", 1, enlace="landing")  # día anterior
        self.evento(ts(2026, 10, 14, 0, 0), "solicitud", 2, enlace="landing")
        self.evento(ts(2026, 10, 14, 0, 0), "bienvenida_enviada", 2, tipo_mensaje="bot_b_v1")
        self.evento(ts(2026, 10, 14, 0, 0), "aceptada", 2)
        self.evento(ts(2026, 10, 14, 12, 0), "solicitud", 3, enlace="descripcion-web")
        self.evento(ts(2026, 10, 14, 12, 0), "bienvenida_fallida", 3, motivo="fuera_de_plazo")
        self.evento(ts(2026, 10, 14, 12, 0), "aceptada", 3)
        self.evento(ts(2026, 10, 14, 23, 59), "mensaje_al_bot", 2)
        self.evento(ts(2026, 10, 14, 23, 59), "mensaje_al_bot", 2)
        self.evento(ts(2026, 10, 15, 0, 0), "solicitud", 4, enlace="landing")  # día siguiente

    def test_dia_cerrado(self):
        texto = resumen.texto_diario(self.con, MADRID, date(2026, 10, 14))
        lineas = texto.split("\n")
        self.assertEqual(lineas[0], "📊 Miércoles 14/10")
        self.assertIn("🆕 Entraron 2 personas nuevas. El bot les mandó a 1 de ellas la bienvenida con la gratuita.",
                      lineas)
        self.assertIn("🔗 Por qué enlace entraron: «landing» 1 · «descripcion-web» 1", lineas)
        self.assertIn("🤖 1 persona escribió al bot en vez de a ti.", lineas)
        self.assertIn("⚠️ Sin bienvenida por algún problema: 1", lineas)
        self.assertIn("   · llegaron con más de 5 min de espera (¿bot parado?): 1", lineas)
        self.assertEqual(lineas[-1], "✅ El bot aceptó las 2 solicitudes.")
        self.assertNotIn("↩️", texto)  # nadie volvió
        self.assertNotIn("💶", texto)  # sin ventas de overoption leídas

    def test_pausa(self):
        self.evento(ts(2026, 10, 14, 13, 0), "solicitud_en_pausa", 5)
        self.evento(ts(2026, 10, 14, 13, 5), "solicitud_en_pausa", 6)
        texto = resumen.texto_diario(self.con, MADRID, date(2026, 10, 14))
        self.assertIn("⏸️ Sin atender por la pausa (para aceptar a mano): 2", texto)
        self.assertNotIn("sigue EN PAUSA", texto)  # ya se reanudó
        with self.con:
            db.guardar_estado(self.con, "pausa_desde", ts(2026, 10, 14, 12, 30))
        for texto in (resumen.texto_diario(self.con, MADRID, date(2026, 10, 14)),
                      resumen.texto_semanal(self.con, MADRID, date(2026, 10, 12))):
            self.assertTrue(texto.endswith("⏸️ El bot sigue EN PAUSA desde las 12:30 del 14.10: "
                                           "no acepta a nadie (simulación). Escríbele /arrancar para que actúe."), texto)

    def test_dudas_y_versiones_de_la_bienvenida(self):
        from premier_captacion import textos

        self.evento(ts(2026, 10, 14, 13, 0), "faq", 5, tema="menu")
        self.evento(ts(2026, 10, 14, 13, 1), "faq", 5, tema="casas")
        self.evento(ts(2026, 10, 14, 14, 0), "faq", 6, tema="packs")
        textos.guardar(self.con, "bienvenida", "Hola v2", ts(2026, 10, 14, 15, 0))
        self.evento(ts(2026, 10, 14, 16, 0), "bienvenida_enviada", 7, tipo_mensaje="bot_b_v2")
        texto = resumen.texto_diario(self.con, MADRID, date(2026, 10, 14))
        self.assertNotIn("📚", texto)  # ninguno de los que entraron ese día
        self.evento(ts(2026, 10, 14, 17, 0), "faq", 2, tema="menu")  # el 2 entró ese día
        self.evento(ts(2026, 10, 14, 17, 0), "solicitud", 8)
        self.evento(ts(2026, 10, 14, 17, 0), "ya_recibida", 8)  # ya estaba en el canal
        self.evento(ts(2026, 10, 14, 17, 1), "faq", 8, tema="menu")
        texto = resumen.texto_diario(self.con, MADRID, date(2026, 10, 14))
        self.assertIn("📚 1 de las 2 miró las preguntas frecuentes del bot.", texto)
        self.assertIn("↩️ 1 persona volvió a entrar al canal (id 8): sin gratuita, porque ya estaba "
                      "o ya había pasado por aquí.", texto)
        # Con dos versiones de bienvenida en el día, sale el desglose con sus nombres.
        self.assertIn("🧪 Versiones de la bienvenida:", texto)
        self.assertIn("   · Bienvenida del bot, versión 2 (cambiada desde el bot el 14/10/2026): 1", texto)
        self.assertIn(f"   · {mensajes.TIPOS_MENSAJE['bot_b_v1']}: 1", texto)

    def test_lo_que_va_de_dia(self):
        texto = resumen.texto_diario(self.con, MADRID, date(2026, 10, 14), ahora_ts=ts(2026, 10, 14, 11, 0))
        self.assertTrue(texto.startswith("📊 Hoy, miércoles 14/10 (hasta las 11:00)"))
        self.assertIn("🆕 Entró 1 persona nueva. El bot le mandó la bienvenida con la gratuita.", texto)

    def test_dia_vacio_no_falla(self):
        texto = resumen.texto_diario(self.con, MADRID, date(2026, 1, 1))
        self.assertIn("🆕 No entró nadie nuevo.", texto)
        self.assertNotIn("⚠️", texto)
        self.assertNotIn("✅", texto)

    def test_cambio_de_hora_de_octubre(self):
        # El 25-10-2026 dura 25 horas en España; el día se corta en las
        # medianoches de Madrid, no cada 24 h desde UTC.
        self.evento(ts(2026, 10, 25, 23, 30), "solicitud", 9, enlace="landing")
        self.evento(ts(2026, 10, 26, 0, 10), "solicitud", 10, enlace="landing")
        texto = resumen.texto_diario(self.con, MADRID, date(2026, 10, 25))
        self.assertIn("🆕 Entró 1 persona nueva.", texto)

    def test_bot_bloqueado_al_volver(self):
        # Quien bloqueó el bot y vuelve a entrar: no le llega la bienvenida,
        # pero se le acepta igual.
        self.evento(ts(2026, 10, 14, 18, 0), "bienvenida_fallida", 2, motivo="Forbidden: bot was blocked by the user")
        texto = resumen.texto_diario(self.con, MADRID, date(2026, 10, 14))
        self.assertIn("   · tenían el bot bloqueado: 1", texto)


class TestEmbudo(Base):
    """El día contado con frases y nombres (2026-11-05). Personas inventadas."""

    def persona(self, uid, nombre, username=None, momento=None, **campos):
        with self.con:
            db.actualizar_datos_usuario(self.con, momento or ts(2026, 10, 1, 9, 0),
                                        {"id": uid, "first_name": nombre, "username": username})
            db.actualizar_campos(self.con, uid, momento or ts(2026, 10, 1, 9, 0), **campos)

    def nuevo(self, uid, nombre, hora, username=None):
        momento = ts(2026, 11, 4, hora, 0)
        with self.con:
            db.registrar_solicitud(self.con, momento, {"id": uid, "first_name": nombre, "username": username},
                                   "Enlace de campaña")
        self.evento(momento, "solicitud", uid, enlace="Enlace de campaña")
        self.evento(momento, "bienvenida_enviada", uid, tipo_mensaje="bot_b_v1")
        self.evento(momento, "aceptada", uid)

    def gratuita(self, uid, momento):
        self.evento(momento, "enlace_venta", uid, canal="Canal de venta", enlace="https://t.me/+inventado")
        with self.con:
            fila = db.obtener_usuario(self.con, uid)
            if fila["enlace_venta_ts"] is None:
                db.actualizar_campos(self.con, uid, momento, enlace_venta_ts=momento)

    def setUp(self):
        super().setUp()
        h = lambda hora, minuto=0: ts(2026, 11, 4, hora, minuto)  # noqa: E731
        # Nuevos del día.
        self.nuevo(21, "Ana Ruiz", 10, "ana_r")
        self.evento(h(10, 1), "faq", 21, tema="menu")
        self.evento(h(10, 5), "te_escribe", 21, primera_vez=True)
        self.gratuita(21, h(11))
        self.nuevo(22, "Bruno", 12)
        self.evento(h(12, 10), "te_escribe", 22, primera_vez=True)
        self.nuevo(23, "Carla", 13, "carla")
        self.evento(h(13, 1), "bloqueo_bot", 23)
        self.nuevo(24, "Dani", 14)
        self.evento(h(14, 1), "faq", 24, tema="menu")
        # Gente de otros días que te escribe.
        self.persona(30, "Eva", bienvenida_ts=ts(2026, 10, 20, 9, 0))
        self.evento(h(15), "te_escribe", 30, primera_vez=True)
        self.persona(31, "Fede", "fede")
        self.evento(h(15, 30), "registrado_sin_bienvenida", 31, tipo_mensaje=mensajes.TIPO_SIN_BOT)
        self.evento(h(15, 30), "te_escribe", 31, primera_vez=True)
        self.persona(32, "Gema")
        self.evento(h(15, 40), "registrado_sin_bienvenida", 32, tipo_mensaje=mensajes.TIPO_APROBADO_SIN_BIENVENIDA)
        self.evento(h(15, 40), "te_escribe", 32, primera_vez=True)
        self.persona(33, "Hugo", enlace_venta_ts=ts(2026, 10, 2, 9, 0))
        self.evento(h(16), "te_escribe", 33)
        self.gratuita(33, h(16, 5))  # otro enlace: la gratuita ya la tuvo
        self.persona(34, "Iris")
        self.evento(h(16, 10), "te_escribe", 34)
        with self.con:
            self.con.execute("INSERT INTO personas_chat (user_id, nombre, username, visto_ts) VALUES (35, 'Juan', NULL, 0)")
        self.evento(h(16, 20), "aviso_fuera_del_canal", 35)
        # Volvió a entrar.
        self.persona(36, "Kike", "kike", bienvenida_ts=ts(2026, 9, 1, 9, 0))
        self.evento(h(17), "solicitud", 36, enlace="Enlace de campaña")
        self.evento(h(17), "ya_recibida", 36, tipo_mensaje="bot_b_v1")
        self.evento(h(17), "bienvenida_enviada", 36, tipo_mensaje=mensajes.TIPO_BIENVENIDA_RECURRENTE)
        self.evento(h(17), "aceptada", 36)
        # La gratuita a alguien de otro día.
        self.persona(37, "Laura")
        self.gratuita(37, h(18))

    def test_el_dia_con_frases(self):
        texto = resumen.texto_diario(self.con, MADRID, date(2026, 11, 4))
        self.assertEqual(texto.split("\n"), [
            "📊 Miércoles 04/11",
            "",
            "🆕 Entraron 4 personas nuevas. El bot les mandó a todas la bienvenida con la gratuita.",
            "",
            "✉️ 2 de esas 4 te escribieron por privado (50 %): Ana Ruiz @ana_r y Bruno.",
            "🎁 Les enviaste la gratuita a 1 de las 2. Falta: Bruno.",
            "😶 Las otras 2 no te han escrito. 1 de ellas bloqueó el bot: Carla @carla "
            "(sigue en el canal, pero el bot ya no puede escribirle).",
            "",
            "📚 2 de las 4 miraron las preguntas frecuentes del bot. 1 de ellas te escribió.",
            "",
            "💬 También te escribieron 6 personas que no son nuevas:",
            "· Eva (entró el 20/10), que te escribe por primera vez.",
            "· Fede @fede, que entró al canal sin pasar por el bot: no tiene gratuita, va a free send.",
            "· Gema, que pidió entrar pero no le llegó la bienvenida: sí tiene gratuita, va a la carpeta del día.",
            "· Juan, que no está en el canal: te avisé con el enlace para que entre.",
            "· 2 que ya te habían escrito otras veces (1 ya tuvo su gratuita).",
            "🎁 También enviaste la gratuita a Laura (no era nueva).",
            "🔗 También enviaste enlaces de venta a Hugo, que ya había tenido la gratuita.",
            "",
            "↩️ 1 persona volvió a entrar al canal (Kike @kike): sin gratuita, porque ya estaba "
            "o ya había pasado por aquí.",
            "",
            "✅ El bot aceptó las 5 solicitudes, sin fallos.",
        ])

    def test_todas_con_gratuita_y_nadie_sin_escribir(self):
        self.gratuita(22, ts(2026, 11, 4, 19, 0))
        lineas = resumen.texto_diario(self.con, MADRID, date(2026, 11, 4)).split("\n")
        self.assertIn("🎁 A todas les enviaste la gratuita.", lineas)

    def test_ninguna_gratuita(self):
        with self.con:
            self.con.execute("UPDATE usuarios SET enlace_venta_ts = NULL WHERE user_id = 21")
        lineas = resumen.texto_diario(self.con, MADRID, date(2026, 11, 4)).split("\n")
        self.assertIn("🎁 A ninguna de las 2 le has enviado todavía la gratuita.", lineas)

    def test_muchos_nombres_se_cortan(self):
        for i in range(12):
            self.nuevo(100 + i, f"Persona{i}", 20)
            self.evento(ts(2026, 11, 4, 20, 30), "te_escribe", 100 + i, primera_vez=True)
        texto = resumen.texto_diario(self.con, MADRID, date(2026, 11, 4))
        self.assertIn("Persona7 y 4 más.", texto)

    def test_ventas_del_dia(self):
        from .test_cruce import canal, entra_movimiento, persona, venta
        persona(self.con, 41, "Comprador", "comprador")
        with self.con:
            self.con.execute("INSERT INTO pagos_correos_manual (correo, texto, ts) VALUES ('a@example.com', '41', 0)")
        canal(self.con, 5, "Canal 5")
        entra_movimiento(self.con, 5, 1, 42, ts(2026, 11, 4, 11, 0) + 5, "https://t.me/+C5")
        leido = ts(2026, 11, 4, 20, 0)
        venta(self.con, "v1", "https://t.me/+C1", ts(2026, 11, 4, 10, 0), correo="a@example.com", importe=30, ahora=leido)
        venta(self.con, "v2", "https://t.me/+C5", ts(2026, 11, 4, 11, 0), producto="Canal 5", correo="b@example.com",
              importe=22.5, ahora=leido)
        venta(self.con, "v3", "https://t.me/+otro", ts(2026, 11, 4, 12, 0), correo="c@example.com", importe=20, ahora=leido)
        venta(self.con, "v4", "https://t.me/+C1", ts(2026, 11, 3, 12, 0), correo="a@example.com", importe=99, ahora=leido)
        lineas = resumen.texto_diario(self.con, MADRID, date(2026, 11, 4)).split("\n")
        self.assertIn("💶 Ventas del día: 3, 72,50 € (leídas hasta las 20:00). Sabemos de quién es 1; "
                      "1 está dudosa; 1 sin identificar.", lineas)

    def test_euros(self):
        self.assertEqual(resumen._euros(644.0), "644 €")
        self.assertEqual(resumen._euros(1234.5), "1.234,50 €")


class TestSemanal(Base):
    def test_compara_con_la_semana_anterior(self):
        for dia in (6, 8):  # semana anterior (lunes 05.10): 2 solicitudes
            self.evento(ts(2026, 10, dia, 10, 0), "solicitud", dia, enlace="landing")
        for dia, uid in ((12, 1), (12, 2), (18, 3)):  # semana del lunes 12.10: 3
            self.evento(ts(2026, 10, dia, 10, 0), "solicitud", uid, enlace="landing")
            self.evento(ts(2026, 10, dia, 10, 0), "bienvenida_enviada", uid, tipo_mensaje="bot_b_v1")

        texto = resumen.texto_semanal(self.con, MADRID, date(2026, 10, 12))
        lineas = texto.split("\n")
        self.assertEqual(lineas[0], "📅 Resumen semanal: lunes 12.10 – domingo 18.10")
        self.assertIn("👥 Entraron al canal: 3 personas  ↗️ +50 % vs semana anterior (2)", lineas)
        self.assertIn("   · Bienvenida del bot, versión B (dos botones), desde 2026-10: 3", lineas)
        self.assertEqual(lineas[-1], "📈 Solicitudes por día: lun 2 · mar 0 · mié 0 · jue 0 · vie 0 · sáb 0 · dom 1")

    def test_semana_en_curso_compara_el_mismo_tramo(self):
        self.evento(ts(2026, 10, 6, 9, 0), "solicitud", 1, enlace="x")    # martes anterior, 9:00
        self.evento(ts(2026, 10, 6, 20, 0), "solicitud", 2, enlace="x")   # martes anterior, 20:00
        self.evento(ts(2026, 10, 13, 9, 0), "solicitud", 3, enlace="x")   # este martes, 9:00
        texto = resumen.texto_semanal(self.con, MADRID, date(2026, 10, 12), ahora_ts=ts(2026, 10, 13, 12, 0))
        self.assertTrue(texto.startswith("📅 Semana en curso, desde el lunes 12.10"))
        # Hasta el martes a las 12:00 en ambas semanas: 1 frente a 1.
        self.assertIn("👥 Entraron al canal: 1 persona  ➡️ +0 % vs semana anterior (1)", texto)


class TestMain(unittest.TestCase):
    def ejecutar(self, propietario):
        with tempfile.TemporaryDirectory() as carpeta:
            entorno = {
                "CAPTACION_BOT_TOKEN": "123456:" + "Z" * 35,
                "CAPTACION_PERFIL": "Dronwhite",
                "CAPTACION_DB": os.path.join(carpeta, "prueba.db"),
                "CAPTACION_PROPIETARIO_ID": propietario,
            }
            with mock.patch.dict(os.environ, entorno, clear=True), \
                    mock.patch("premier_captacion.resumen.BotAPI") as api:
                codigo = resumen.main(["diario"])
        return codigo, api

    def test_sin_propietario_no_falla_ni_envia(self):
        # Durante la puesta en marcha los timers ya están activos.
        codigo, api = self.ejecutar("")
        self.assertEqual(codigo, 0)
        api.assert_not_called()

    def test_con_propietario_envia_el_resumen(self):
        codigo, api = self.ejecutar("111")
        self.assertEqual(codigo, 0)
        metodo, = (c.args[0] for c in api.return_value.llamar.call_args_list)
        self.assertEqual(metodo, "sendMessage")
        self.assertEqual(api.return_value.llamar.call_args.kwargs["chat_id"], 111)


class TestFechasPorDefecto(unittest.TestCase):
    def test_ayer_y_lunes(self):
        # A las 00:05 del jueves 15.10 en Madrid, "ayer" es el miércoles 14.
        self.assertEqual(resumen.ayer(MADRID, ts(2026, 10, 15, 0, 5)), date(2026, 10, 14))
        self.assertEqual(resumen.lunes_de(date(2026, 10, 18)), date(2026, 10, 12))
        self.assertEqual(resumen.lunes_de(date(2026, 10, 12)), date(2026, 10, 12))


if __name__ == "__main__":
    unittest.main()
