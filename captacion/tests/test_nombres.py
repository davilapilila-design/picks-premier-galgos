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


class TestChoca(unittest.TestCase):
    """El nombre del correo dice una persona y el de Telegram otra distinta:
    el cruce por hora no puede darle ese correo solo (diseño 2026-11-01)."""

    def test_otro_nombre_de_pila_choca(self):
        self.assertTrue(nombres.choca("victorlopez@example.com", "Raul", None))

    def test_mismo_nombre_no_choca(self):
        self.assertFalse(nombres.choca("victorlopez@example.com", "Victor Lopez", None))

    def test_un_nombre_que_no_es_de_pila_no_choca(self):
        self.assertFalse(nombres.choca("victorlopez@example.com", "Vic", None))

    def test_diminutivo_no_choca(self):
        self.assertFalse(nombres.choca("danirojo@example.com", "Daniel", None))
        self.assertFalse(nombres.choca("danielrojo@example.com", "Dani", None))

    def test_si_su_apellido_esta_en_el_correo_no_choca(self):
        self.assertFalse(nombres.choca("rosalesmanuel@example.com", "Pedro Rosales", None))

    def test_correo_sin_nombre_de_pila_no_choca(self):
        self.assertFalse(nombres.choca("xk81@example.com", "Raul", None))

    def test_usuario_que_casa_con_el_correo_no_choca(self):
        self.assertFalse(nombres.choca("victorlopez@example.com", "Raul", "victorlopez"))


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


class TestNombresAnteriores(unittest.TestCase):
    """Historial de nombres y @ (pedido por el dueño el 2026-11-04)."""

    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)

    def anteriores(self, uid):
        return [tuple(f) for f in self.con.execute(
            "SELECT nombre, username, cambio_ts FROM nombres_anteriores WHERE user_id = ? ORDER BY cambio_ts, rowid",
            (uid,))]

    def test_se_apunta_el_anterior_al_cambiar(self):
        with self.con:
            db.actualizar_datos_usuario(self.con, 1, {"id": 500, "first_name": "Juanito", "username": "juan_viejo"})
            db.actualizar_datos_usuario(self.con, 2, {"id": 500, "first_name": "Juanito", "username": "JUAN_VIEJO"})
            db.actualizar_datos_usuario(self.con, 3, {"id": 500, "first_name": "Juan Pérez", "username": "juanp"})
            db.actualizar_datos_usuario(self.con, 4, {"id": 500, "first_name": "Juan Pérez", "username": "juanp"})
        self.assertEqual(self.anteriores(500), [("Juanito", "JUAN_VIEJO", 3)])  # el @ solo cambió de mayúsculas

    def test_la_lista_de_chats_pone_al_dia_el_nombre_en_todas_partes(self):
        from premier_captacion import ventas
        with self.con:
            db.actualizar_datos_usuario(self.con, 1, {"id": 501, "first_name": "Bea", "username": "bea"})
            ventas.guardar_persona(self.con, 501, "Bea", "bea")
            nombres.guardar_chats(self.con, [(501, "Beatriz Gil", "beagil"), (502, "Luis", None)], ahora=5)
            nombres.guardar_chats(self.con, [(501, "Beatriz Gil", "beagil")], ahora=6)
        self.assertEqual(self.anteriores(501), [("Bea", "bea", 5)])
        for tabla in ("usuarios", "ventas_personas", "personas_chat"):
            fila = self.con.execute(f"SELECT nombre, username FROM {tabla} WHERE user_id = 501").fetchone()
            self.assertEqual(tuple(fila), ("Beatriz Gil", "beagil"), tabla)
        self.assertEqual(self.anteriores(502), [])

    def test_canales_de_venta_sin_dato_no_es_un_cambio(self):
        from premier_captacion import ventas
        with self.con:
            ventas.guardar_persona(self.con, 503, "Leo", "leo")
            ventas.guardar_persona(self.con, 503, "Leo", None)      # sin @ en ese dato: no se sabe
            ventas.guardar_persona(self.con, 503, "Leo Ruiz", None)
        self.assertEqual([a[:2] for a in self.anteriores(503)], [("Leo", "leo")])
        self.assertEqual(tuple(self.con.execute("SELECT nombre, username FROM ventas_personas").fetchone()),
                         ("Leo Ruiz", "leo"))

    def test_sin_datos_no_es_un_cambio(self):
        with self.con:
            db.actualizar_datos_usuario(self.con, 1, {"id": 504, "first_name": "Ana", "username": "ana"})
            db.nombre_visto(self.con, 504, None, None, 2)
        self.assertEqual(self.anteriores(504), [])


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
