import unittest
from zoneinfo import ZoneInfo

from premier_captacion import consulta, db, nombres, ventas

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

    def ids(self, dato, contiene=False):
        return [f["user_id"] for f in consulta.buscar(self.con, dato, contiene=contiene)]

    def test_por_arroba_exacta_aunque_otros_lo_contengan(self):
        self.assertEqual(self.ids("@JOSEP"), [1])
        self.assertEqual(self.ids("josep"), [1])

    def test_por_nombre_exacto_sin_tildes_ni_mayusculas(self):
        self.assertEqual(self.ids("jose perez"), [1])
        self.assertEqual(self.ids("  JOSÉ   Pérez "), [1])
        self.assertEqual(self.ids("ana"), [3])
        self.assertEqual(self.ids("3"), [3])
        self.assertEqual(self.ids("jose"), [])  # nadie se llama solo «jose»
        self.assertEqual(self.ids("nadie"), [])

    def test_por_parte_del_nombre_si_se_pide(self):
        self.assertEqual(sorted(self.ids("jose", contiene=True)), [1, 2])
        self.assertEqual(self.ids("PEREZ", contiene=True), [1])
        self.assertEqual(sorted(self.ids("@jos", contiene=True)), [1, 2])

    def test_ficha_con_la_gratuita_y_los_envios_posteriores(self):
        texto = consulta.ficha(self.con, db.obtener_usuario(self.con, 1), TZ)
        self.assertTrue(texto.startswith("👤 Nombre: José Pérez\n🆔 Id de Telegram: 1\n📛 Usuario: @josep\n"), texto)
        self.assertIn("🎁 Gratuita: 09/10/2025 a las 11:53, canal de venta «VIP Galgos»", texto)
        self.assertIn("Después se le envió 1 enlace de venta más", texto)
        self.assertIn("10/10/2025 a las 10:53: «Packs» – t.me/+falso", texto)
        self.assertIn("Enlace: t.me/+falso", texto)

    def test_ficha_sin_gratuita(self):
        texto = consulta.ficha(self.con, db.obtener_usuario(self.con, 3), TZ)
        self.assertIn("No le consta ninguna apuesta gratuita", texto)

    def test_un_nombre_exacto_da_la_ficha_y_el_boton_de_contiene(self):
        texto, teclado = consulta.respuesta(self.con, "Ana", TZ)
        self.assertTrue(texto.startswith("👤 Nombre: Ana\n"), texto)
        self.assertEqual(teclado, {"inline_keyboard": [
            [{"text": "🔎 Buscar los que contienen «Ana»", "callback_data": "grc:Ana"}]]})

    def test_por_id_no_ofrece_buscar_los_que_contienen(self):
        self.assertIsNone(consulta.respuesta(self.con, "3", TZ)[1])

    def test_sin_nadie_exacto_busca_los_que_lo_contienen(self):
        texto, teclado = consulta.respuesta(self.con, "jos", TZ)
        self.assertTrue(texto.startswith("Nadie se llama exactamente «jos».\nHay 2 personas que contienen «jos»"),
                        texto)
        botones = [fila[0] for fila in teclado["inline_keyboard"]]
        self.assertEqual(botones[0], {"text": "🎁 José Pérez (@josep)", "callback_data": "gra:1"})
        self.assertEqual([b["callback_data"] for b in botones], ["gra:1", "gra:2"])  # sin botón de contiene

    def test_sin_nadie_exacto_y_una_que_lo_contiene_da_su_ficha(self):
        texto, teclado = consulta.respuesta(self.con, "ruiz", TZ)
        self.assertTrue(texto.startswith("Nadie se llama exactamente «ruiz». Lo contiene:\n\n👤 Nombre: Josefa Ruiz"),
                        texto)
        self.assertIsNone(teclado)

    def test_varias_exactas_dan_botones_y_el_de_contiene(self):
        persona(self.con, 4, "ana")
        texto, teclado = consulta.respuesta(self.con, "ANA", TZ)
        self.assertIn("Hay 2 personas que se llaman «ANA»", texto)
        self.assertEqual([fila[0]["callback_data"] for fila in teclado["inline_keyboard"]],
                         ["gra:3", "gra:4", "grc:ANA"])

    def test_buscar_los_que_contienen(self):
        texto, _ = consulta.respuesta(self.con, "jos", TZ, contiene=True)
        self.assertTrue(texto.startswith("Hay 2 personas que contienen «jos»"), texto)

    def test_el_boton_de_contiene_cabe_en_telegram(self):
        largo = "Á" * 40  # 80 bytes: no cabe en los 64 de un botón
        persona(self.con, 5, largo)
        texto, teclado = consulta.respuesta(self.con, largo, TZ)
        self.assertIn("🆔 Id de Telegram: 5", texto)
        self.assertIsNone(teclado)

    def test_demasiadas_coincidencias_se_recortan(self):
        for uid in range(10, 25):
            persona(self.con, uid, f"Luis {uid}")
        texto, teclado = consulta.respuesta(self.con, "luis", TZ)
        self.assertIn("Hay 15 personas que contienen «luis»", texto)
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
        self.bot.procesar(update_boton(3, "grc:jos", uid=500))
        self.assertFalse(any("VIP Galgos" in e["text"] or "Josefa" in e["text"] for e in self.api.envios_a(500)))
        self.assertEqual(self.api.envios_a(PROPIETARIO), [])

    def test_el_boton_de_contiene_da_la_lista(self):
        self.bot.procesar(update_boton(1, "grc:jos", uid=PROPIETARIO))
        self.assertTrue(self.ultimo()["text"].startswith("Hay 2 personas que contienen «jos»"))
        self.assertIn("reply_markup", self.ultimo())

    def test_el_boton_da_la_ficha_de_quien_no_paso_por_la_bienvenida(self):
        with self.con:
            nombres.guardar_chats(self.con, [(40, "M", None)], T)
        self.bot.procesar(update_boton(1, "gra:40", uid=PROPIETARIO))
        self.assertIn("🆔 Id de Telegram: 40", self.ultimo()["text"])


class TestSinBienvenida(unittest.TestCase):
    """Clientes de antes (o que entraron por otro camino): el lector los
    conoce por el chat privado con el dueño o por los canales de venta, pero
    no están en `usuarios`."""

    def setUp(self):
        self.con = conexion()
        self.addCleanup(self.con.close)
        persona(self.con, 1, "José Pérez", "josep")
        with self.con:
            nombres.guardar_chats(self.con, [(40, "M", None), (1, "José Pérez", "josep")], T)
            ventas.guardar_persona(self.con, 41, "Marta Gil", "martag")
            ventas.guardar_persona(self.con, 40, "M", None)

    def ids(self, dato, contiene=False):
        return [f["user_id"] for f in consulta.buscar(self.con, dato, contiene=contiene)]

    def test_se_encuentran_por_id_arroba_o_nombre_sin_repetirse(self):
        self.assertEqual(self.ids("40"), [40])
        self.assertEqual(self.ids("@martag"), [41])
        self.assertEqual(self.ids("marta gil"), [41])
        self.assertEqual(self.ids("m"), [40])
        self.assertEqual(self.ids("marta"), [])
        self.assertEqual(self.ids("marta", contiene=True), [41])
        self.assertEqual(self.ids("jose", contiene=True), [1])

    def test_ficha_sin_gratuita(self):
        texto, teclado = consulta.respuesta(self.con, "40", TZ)
        self.assertIsNone(teclado)
        self.assertTrue(texto.startswith("👤 Nombre: M\n🆔 Id de Telegram: 40\n📛 Usuario: no tiene @\n"), texto)
        self.assertIn("Sin bienvenida apuntada", texto)
        self.assertIn("No le consta ninguna apuesta gratuita", texto)

    def test_los_caracteres_invisibles_del_nombre_no_cuentan(self):
        with self.con:  # relleno coreano y espacios de anchura cero alrededor del nombre
            nombres.guardar_chats(self.con, [(42, "ㅤㅤRicardoㅤ", None),
                                             (43, "​Luis⁠ Ruiz​", None)], T)
        self.assertEqual(self.ids("ricardo"), [42])
        self.assertEqual(self.ids("luis ruiz"), [43])

    def test_ficha_de_quien_entro_sin_pasar_por_el_bot(self):
        with self.con:  # lo registra el lector cuando escribe estando en el canal
            db.actualizar_datos_usuario(self.con, T, {"id": 44, "first_name": "Rita"})
            db.actualizar_campos(self.con, 44, T, bienvenida_tipo="sin_bot", bienvenida_ts=T)
        texto, _ = consulta.respuesta(self.con, "44", TZ)
        self.assertIn("👋 Sin bienvenida: entró al canal sin pasar por el bot", texto)
        self.assertIn("· registrado el", texto)
        self.assertNotIn("👋 Bienvenida:", texto)

    def cambia(self, uid, nombre, username, ts):
        with self.con:
            nombres.guardar_chats(self.con, [(uid, nombre, username)], ts)

    def test_por_el_nombre_o_el_arroba_de_antes(self):
        self.cambia(41, "Marta G.", "marta_nueva", T + 86400)
        self.assertEqual(self.ids("@martag"), [41])
        self.assertEqual(self.ids("marta gil"), [41])
        self.assertEqual(self.ids("martag", contiene=True), [41])
        texto, _ = consulta.respuesta(self.con, "@martag", TZ)
        self.assertTrue(texto.startswith("⚠️ «@martag» es como se llamaba antes (cambio visto el 10/10/2025). "
                                         "Ahora:\n\n👤 Nombre: Marta G.\n"), texto)
        self.assertIn("📝 Antes: Marta Gil (@martag) (cambio visto el 10/10/2025)", texto)

    def test_el_actual_va_antes_que_quien_lo_tuvo(self):
        self.cambia(41, "Marta G.", "marta_nueva", T + 86400)
        self.cambia(45, "Otra Marta", "martag", T + 2 * 86400)  # alguien coge el @ que quedó libre
        self.assertEqual(self.ids("@martag"), [45, 41])
        _, teclado = consulta.respuesta(self.con, "@martag", TZ)
        botones = [b[0]["text"] for b in teclado["inline_keyboard"]]
        self.assertEqual(botones[:2], ["Otra Marta (@martag)", "Marta G. (@marta_nueva) · antes @martag"])

    def test_quien_no_se_conoce_sigue_sin_encontrarse(self):
        self.assertEqual(self.ids("99"), [])
        self.assertIsNone(consulta.persona(self.con, 99))


if __name__ == "__main__":
    unittest.main()


class TestFichaQueYaEstaba(unittest.TestCase):
    def test_dice_si_estaba_en_el_canal_y_si_volvio(self):
        con = conexion()
        self.addCleanup(con.close)
        persona(con, 9, "Leo")
        with con:
            db.guardar_miembros(con, [9], T)
            db.actualizar_campos(con, 9, T, recurrente_ts=T + 86400)
        texto = consulta.ficha(con, db.obtener_usuario(con, 9), TZ)
        self.assertIn("📋 Ya estaba en el canal (lista de suscriptores del 09/10/2025)", texto)
        self.assertIn("🔁 Volvió a pedir entrar: 10/10/2025", texto)
