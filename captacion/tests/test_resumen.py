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
        self.assertEqual(lineas[0], "📊 Resumen del miércoles 14.10")
        self.assertIn("👥 Solicitudes: 2 (2 personas)", lineas)
        self.assertIn("   · landing: 1", lineas)
        self.assertIn("   · descripcion-web: 1", lineas)
        self.assertIn("👋 Bienvenidas enviadas: 1", lineas)
        self.assertIn("⚠️ Sin bienvenida por algún problema: 1", lineas)
        self.assertIn("   · llegaron con más de 5 min de espera (¿bot parado?): 1", lineas)
        self.assertIn("🔁 Ya estaban o volvieron (bienvenida sin gratuita): 0", lineas)
        self.assertIn("✅ Aceptadas: 2", lineas)
        self.assertIn("🤖 Escribieron al bot: 1 persona", lineas)

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
        self.assertIn("📚 Miraron las dudas frecuentes: 2 personas", texto)
        # Con dos versiones de bienvenida en el día, sale el desglose con sus nombres.
        self.assertIn("   · Bienvenida del bot, versión 2 (cambiada desde el bot el 14/10/2026): 1", texto)
        self.assertIn(f"   · {mensajes.TIPOS_MENSAJE['bot_b_v1']}: 1", texto)

    def test_lo_que_va_de_dia(self):
        texto = resumen.texto_diario(self.con, MADRID, date(2026, 10, 14), ahora_ts=ts(2026, 10, 14, 11, 0))
        self.assertTrue(texto.startswith("📊 Hoy, miércoles 14.10 (hasta las 11:00)"))
        self.assertIn("👥 Solicitudes: 1 (1 persona)", texto)

    def test_dia_vacio_no_falla(self):
        texto = resumen.texto_diario(self.con, MADRID, date(2026, 1, 1))
        self.assertIn("👥 Solicitudes: 0 (0 personas)", texto)
        self.assertNotIn("⚠️", texto)

    def test_cambio_de_hora_de_octubre(self):
        # El 25-10-2026 dura 25 horas en España; el día se corta en las
        # medianoches de Madrid, no cada 24 h desde UTC.
        self.evento(ts(2026, 10, 25, 23, 30), "solicitud", 9, enlace="landing")
        self.evento(ts(2026, 10, 26, 0, 10), "solicitud", 10, enlace="landing")
        texto = resumen.texto_diario(self.con, MADRID, date(2026, 10, 25))
        self.assertIn("👥 Solicitudes: 1 (1 persona)", texto)


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
        self.assertIn("👥 Solicitudes: 3 (3 personas)  ↗️ +50 % vs semana anterior (2)", lineas)
        self.assertIn("👋 Bienvenidas enviadas: 3 (semana anterior: 0)", lineas)
        self.assertIn("   · Bienvenida del bot, versión B (dos botones), desde 2026-10: 3", lineas)
        self.assertEqual(lineas[-1], "📈 Solicitudes por día: lun 2 · mar 0 · mié 0 · jue 0 · vie 0 · sáb 0 · dom 1")

    def test_semana_en_curso_compara_el_mismo_tramo(self):
        self.evento(ts(2026, 10, 6, 9, 0), "solicitud", 1, enlace="x")    # martes anterior, 9:00
        self.evento(ts(2026, 10, 6, 20, 0), "solicitud", 2, enlace="x")   # martes anterior, 20:00
        self.evento(ts(2026, 10, 13, 9, 0), "solicitud", 3, enlace="x")   # este martes, 9:00
        texto = resumen.texto_semanal(self.con, MADRID, date(2026, 10, 12), ahora_ts=ts(2026, 10, 13, 12, 0))
        self.assertTrue(texto.startswith("📅 Semana en curso, desde el lunes 12.10"))
        # Hasta el martes a las 12:00 en ambas semanas: 1 frente a 1.
        self.assertIn("👥 Solicitudes: 1 (1 persona)  ➡️ +0 % vs semana anterior (1)", texto)


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
