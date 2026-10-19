import unittest
from zoneinfo import ZoneInfo

from premier_captacion import consulta, db

from .apoyo import PROPIETARIO, conexion, update_boton, update_mensaje, usuario
from .test_bot import Base

TZ = ZoneInfo("Europe/Madrid")
T = 1_760_000_000  # 2025-10-09 08:53:20 UTC


def persona(con, uid, nombre, username=None, gratuita=None):
    """Alta de una persona con bienvenida; `gratuita` = [(ts, canal), …] enlaces de venta enviados."""
    db.actualizar_datos_usuario(con, T, usuario(uid, nombre, username))
    db.marcar_bienvenida(con, uid, T, "manual_buenas")
    for ts, canal in gratuita or ():
        db.registrar_evento(con, ts, "enlace_venta", uid, enlace="t.me/+falso", canal=canal)
    if gratuita:
        db.actualizar_campos(con, uid, T, enlace_venta_ts=gratuita[0][0], canal_venta=gratuita[-1][1])


class TestConsulta(unittest.TestCase):
    def setUp(self):
        self.con = conexion()
        self.addCleanup(self.con.close)
        persona(self.con, 1, "José Pérez", "josep", gratuita=[(T + 3600, "VIP Galgos"), (T + 86400, "Packs")])
        persona(self.con, 2, "Josefa Ruiz")
        persona(self.con, 3, "Ana", "ana_g")

    def test_por_arroba_exacta_aunque_otros_lo_contengan(self):
        self.assertEqual([f["user_id"] for f in consulta.buscar(self.con, "@JOSEP")], [1])

    def test_por_parte_del_nombre_sin_tildes_ni_mayusculas(self):
        self.assertEqual(sorted(f["user_id"] for f in consulta.buscar(self.con, "jose")), [1, 2])
        self.assertEqual([f["user_id"] for f in consulta.buscar(self.con, "PEREZ")], [1])
        self.assertEqual([f["user_id"] for f in consulta.buscar(self.con, "3")], [3])
        self.assertEqual(consulta.buscar(self.con, "nadie"), [])

    def test_ficha_con_la_gratuita_y_los_envios_posteriores(self):
        texto = consulta.ficha(self.con, db.obtener_usuario(self.con, 1), TZ)
        self.assertIn("José Pérez (@josep)", texto)
        self.assertIn("🎁 Gratuita: 09/10/2025 a las 11:53, canal de venta «VIP Galgos»", texto)
        self.assertIn("Después se le envió 1 enlace de venta más", texto)
        self.assertIn("10/10/2025 a las 10:53: «Packs»", texto)

    def test_ficha_sin_gratuita(self):
        texto = consulta.ficha(self.con, db.obtener_usuario(self.con, 3), TZ)
        self.assertIn("No le consta ninguna apuesta gratuita", texto)

    def test_varias_coincidencias_dan_botones_con_la_gratuita_primero(self):
        texto, teclado = consulta.respuesta(self.con, "jos", TZ)
        self.assertIn("Hay 2 personas", texto)
        botones = [fila[0] for fila in teclado["inline_keyboard"]]
        self.assertEqual(botones[0], {"text": "🎁 José Pérez (@josep)", "callback_data": "gra:1"})
        self.assertEqual(botones[1]["callback_data"], "gra:2")

    def test_demasiadas_coincidencias_se_recortan(self):
        for uid in range(10, 25):
            persona(self.con, uid, f"Luis {uid}")
        texto, teclado = consulta.respuesta(self.con, "luis", TZ)
        self.assertIn("Hay 15 personas", texto)
        self.assertEqual(len(teclado["inline_keyboard"]), consulta.MAX_OPCIONES)


class TestOrdenGratuita(Base):
    def setUp(self):
        super().setUp()
        persona(self.con, 1, "José Pérez", "josep", gratuita=[(T, "VIP Galgos")])
        persona(self.con, 2, "Josefa Ruiz")

    def ultimo(self):
        return self.api.envios_a(PROPIETARIO)[-1]

    def test_una_persona_da_su_ficha(self):
        self.bot.procesar(update_mensaje(1, uid=PROPIETARIO, texto="/gratuita @josep"))
        self.assertIn("canal de venta «VIP Galgos»", self.ultimo()["text"])

    def test_sin_dato_explica_como_se_usa_y_varias_dan_botones(self):
        self.bot.procesar(update_mensaje(1, uid=PROPIETARIO, texto="/gratuita"))
        self.assertIn("Dime a quién", self.ultimo()["text"])
        self.bot.procesar(update_mensaje(2, uid=PROPIETARIO, texto="/gratuita jos"))
        self.assertIn("reply_markup", self.ultimo())
        self.bot.procesar(update_boton(3, "gra:2", uid=PROPIETARIO))
        self.assertIn("Josefa Ruiz", self.ultimo()["text"])

    def test_un_cliente_no_puede_consultar(self):
        self.bot.procesar(update_mensaje(1, uid=500, texto="/gratuita jos"))
        self.bot.procesar(update_boton(2, "gra:1", uid=500))
        self.assertFalse(any("VIP Galgos" in e["text"] for e in self.api.envios_a(500)))
        self.assertEqual(self.api.envios_a(PROPIETARIO), [])


if __name__ == "__main__":
    unittest.main()
