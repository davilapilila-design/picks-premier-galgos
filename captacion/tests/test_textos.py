import unittest
from zoneinfo import ZoneInfo

from premier_captacion import mensajes, textos

from .apoyo import conexion

MADRID = ZoneInfo("Europe/Madrid")


class Base(unittest.TestCase):
    def setUp(self):
        self.con = conexion()
        self.addCleanup(self.con.close)


class TestGuardar(Base):
    def test_sin_cambios_vale_el_de_partida(self):
        self.assertEqual(textos.actual(self.con, "faq:bank"), mensajes.FAQ["bank"]["texto"])
        self.assertIsNone(textos.anterior(self.con, "faq:bank"))
        self.assertEqual(textos.tipo_bienvenida(self.con), mensajes.TIPO_BIENVENIDA_BOT)

    def test_vale_el_ultimo_y_se_puede_volver_atras(self):
        self.assertIsNone(textos.guardar(self.con, "faq:bank", "A", 10))  # solo la bienvenida tiene tipo
        self.assertEqual(textos.anterior(self.con, "faq:bank"), mensajes.FAQ["bank"]["texto"])
        textos.guardar(self.con, "faq:bank", "B", 20)
        self.assertEqual((textos.actual(self.con, "faq:bank"), textos.anterior(self.con, "faq:bank")), ("B", "A"))
        # Un texto no pisa a otro.
        self.assertEqual(textos.actual(self.con, "faq:packs"), mensajes.FAQ["packs"]["texto"])

    def test_cada_bienvenida_distinta_es_un_tipo_y_si_se_repite_recupera_el_suyo(self):
        self.assertEqual(textos.guardar(self.con, "bienvenida", "Hola v2", 10), "bot_b_v2")
        self.assertEqual(textos.guardar(self.con, "bienvenida", "Hola v3", 20), "bot_b_v3")
        self.assertEqual(textos.guardar(self.con, "bienvenida", "Hola v2", 30), "bot_b_v2")
        self.assertEqual(textos.tipo_bienvenida(self.con), "bot_b_v2")
        self.assertEqual(textos.guardar(self.con, "bienvenida", mensajes.TEXTO_BIENVENIDA, 40),
                         mensajes.TIPO_BIENVENIDA_BOT)
        self.assertEqual(textos.versiones_bienvenida(self.con), [("bot_b_v2", "Hola v2", 10), ("bot_b_v3", "Hola v3", 20)])
        cambios = [f["tipo"] for f in self.con.execute("SELECT tipo FROM eventos")]
        self.assertEqual(cambios, ["texto_cambiado"] * 4)

    def test_descripcion_de_los_tipos(self):
        textos.guardar(self.con, "bienvenida", "Hola v2", 1_800_000_000)
        self.assertEqual(textos.descripcion_tipo(self.con, "bot_b_v1"), mensajes.TIPOS_MENSAJE["bot_b_v1"])
        self.assertEqual(textos.descripcion_tipo(self.con, "bot_b_v2", MADRID),
                         "Bienvenida del bot, versión 2 (cambiada desde el bot el 15/01/2027)")
        self.assertEqual(textos.descripcion_tipo(self.con, "otro"), "otro")


class TestLoQueMandaElDueno(unittest.TestCase):
    def test_negritas_de_telegram_a_negrita_unicode(self):
        # 🐕 cuenta como dos en las posiciones de Telegram (UTF-16).
        self.assertEqual(textos.con_negritas("Hola 🐕 amigo mío", [{"type": "bold", "offset": 8, "length": 9}]),
                         "Hola 🐕 " + mensajes.negrita("amigo mío"))
        varias = [{"type": "italic", "offset": 0, "length": 4}, {"type": "bold", "offset": 5, "length": 3},
                  {"type": "bold", "offset": 0, "length": 1}]
        self.assertEqual(textos.con_negritas("abcd efg", varias), mensajes.negrita("a") + "bcd " + mensajes.negrita("efg"))
        self.assertEqual(textos.con_negritas("sin formato", None), "sin formato")

    def test_textos_que_no_valen(self):
        self.assertIsNone(textos.problema("Hola"))
        self.assertEqual(textos.problema(" \n "), "está vacío")
        self.assertIn("demasiado largo", textos.problema("🐕" * 1501))  # 3002 en UTF-16


class TestEdicion(Base):
    def test_dos_pasos_y_caduca(self):
        self.assertIsNone(textos.edicion(self.con, 100))
        textos.empezar_edicion(self.con, "faq:bank", 100)
        edicion = textos.edicion(self.con, 200)
        self.assertEqual((edicion["clave"], edicion["nuevo"]), ("faq:bank", None))
        textos.preparar(self.con, edicion, "Nuevo", 300)
        self.assertEqual(textos.edicion(self.con, 400)["nuevo"], "Nuevo")
        self.assertIsNone(textos.edicion(self.con, 300 + textos.CADUCIDAD_EDICION_S + 1))
        self.assertIsNone(textos.edicion(self.con, 400))  # al caducar se borra

    def test_terminar(self):
        textos.empezar_edicion(self.con, "bienvenida", 100)
        textos.terminar(self.con)
        self.assertIsNone(textos.edicion(self.con, 101))


if __name__ == "__main__":
    unittest.main()
