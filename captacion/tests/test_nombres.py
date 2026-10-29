"""El correo de una venta y el nombre o @usuario de una persona de Telegram
(nombres.py). Datos INVENTADOS."""
import asyncio
import unittest

from premier_captacion import db, nombres

try:
    from telethon.tl import types
except ImportError:  # pragma: no cover
    types = None


class TestCasa(unittest.TestCase):
    def casa(self, correo, nombre, username=None):
        return nombres.puntos(correo, nombre, username) is not None

    def test_usuario_igual_al_correo(self):
        self.assertTrue(self.casa("pepito77@example.com", "Pepe", "Pepito77"))

    def test_usuario_dentro_del_correo_si_es_largo(self):
        self.assertTrue(self.casa("pepitogrillo_madrid@example.com", "Pepe", "pepitogrillo"))
        self.assertFalse(self.casa("ana@example.com", "Ana", "ana_lopez_99"))  # «ana» es muy corto

    def test_nombre_y_apellido(self):
        self.assertTrue(self.casa("luisferrandiz80@example.com", "Luis Ferrándiz"))
        self.assertTrue(self.casa("jonaferrandiz@example.com", "Jonathan Ferrandiz"))  # «jona…»

    def test_nombre_suelto_nunca(self):
        self.assertFalse(self.casa("luis.ferrandiz@example.com", "Luis"))

    def test_hace_falta_el_nombre_tambien(self):
        self.assertFalse(self.casa("pedroferrandiz@example.com", "Luis Ferrandiz"))
        self.assertFalse(self.casa("marlonferrandiz@example.com", "Marga Ferrandiz"))  # «marl» ≠ «marg»

    def test_nombre_compuesto_no_es_apellido(self):
        self.assertFalse(self.casa("miguelangel77@example.com", "Miguel Angel"))
        self.assertFalse(self.casa("juancarlos@example.com", "Juan Carlos"))

    def test_apellido_repetido_o_parte_del_nombre_no_cuenta(self):
        self.assertFalse(self.casa("alexsanz@example.com", "Alex Alex"))
        self.assertFalse(self.casa("carlos.sanz@example.com", "Carlos Carl0s"))

    def test_acentos_y_mayusculas(self):
        self.assertTrue(self.casa("JoseMariaÑuñez@example.com", "José Ñúñez"))

    def test_si_falta_algun_apellido_es_parcial(self):
        def motivo(correo, nombre):
            return nombres.puntos(correo, nombre, None)[1]
        self.assertEqual(motivo("juanferrandizgimeno@example.com", "Juan Manuel Ferrandiz Gimeno"), "nombre")
        self.assertEqual(motivo("juan.ferrandiz.rosado@example.com", "Juan Manuel Ferrandiz Gimeno"),
                         "nombre_parcial")

    def test_mas_palabras_mas_puntos(self):
        mas = nombres.puntos("joseluisferrandizgil@example.com", "Jose Luis Ferrandiz Gil", None)[0]
        menos = nombres.puntos("joseluisferrandizgil@example.com", "Jose Ferrandiz", None)[0]
        self.assertGreater(mas, menos)


class TestChats(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)

    def test_guarda_y_actualiza(self):
        with self.con:
            nombres.guardar_chats(self.con, [(500, "Ana", None)], ahora=1)
            nombres.guardar_chats(self.con, [(500, "Ana Ferrandiz", "anaf"), (501, "Luis", None)], ahora=2)
        filas = [tuple(f) for f in self.con.execute(
            "SELECT user_id, nombre, username, visto_ts FROM personas_chat ORDER BY user_id")]
        self.assertEqual(filas, [(500, "Ana Ferrandiz", "anaf", 2), (501, "Luis", None, 2)])


class ClienteDialogos:
    def __init__(self, entidades):
        self.entidades = entidades

    async def iter_dialogs(self):
        for e in self.entidades:
            yield type("Dialogo", (), {"entity": e})()


@unittest.skipIf(types is None, "telethon no está instalado")
class TestLeerChats(unittest.TestCase):
    def test_solo_personas(self):
        ana = types.User(id=500, first_name="Ana", last_name="Ferrandiz", username="anaf")
        bot = types.User(id=501, first_name="Bot", bot=True)
        borrada = types.User(id=502, deleted=True)
        yo = types.User(id=503, first_name="Yo", is_self=True)
        canal = types.Channel(id=10, title="Canal", photo=types.ChatPhotoEmpty(), date=None)
        cliente = ClienteDialogos([ana, bot, borrada, yo, canal])
        self.assertEqual(asyncio.run(nombres.leer_chats(cliente)), [(500, "Ana Ferrandiz", "anaf")])


if __name__ == "__main__":
    unittest.main()
