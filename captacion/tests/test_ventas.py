import asyncio
import importlib.util
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from premier_captacion import db, guardia, ventas

MADRID = ZoneInfo("Europe/Madrid")
TS = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc).timestamp()


def conexion():
    return db.abrir(":memory:")


def usuario(uid, nombre, username=None, desde=None):
    participante = SimpleNamespace(date=datetime.fromtimestamp(desde, timezone.utc)) if desde else None
    return SimpleNamespace(id=uid, first_name=nombre, last_name=None, username=username, bot=False,
                           deleted=False, participant=participante)


class TestGuardia(unittest.TestCase):
    def test_modo_ventas_solo_lee(self):
        permitidas = guardia.MODOS["ventas"]
        self.assertIn("channels.GetAdminLogRequest", permitidas)
        self.assertIn("channels.GetParticipantsRequest", permitidas)
        self.assertNotIn("messages.SendMessageRequest", permitidas)
        self.assertNotIn("messages.UpdateDialogFilterRequest", permitidas)
        self.assertIn("channels.GetAdminLogRequest", guardia.MODOS["lector"])


class TestMovimiento(unittest.TestCase):
    def test_tipos(self):
        def accion(nombre):
            return type(nombre, (), {})()
        self.assertEqual(ventas._movimiento(accion("ChannelAdminLogEventActionParticipantJoinByInvite")), "entra")
        self.assertEqual(ventas._movimiento(accion("ChannelAdminLogEventActionParticipantJoinByRequest")), "entra")
        self.assertEqual(ventas._movimiento(accion("ChannelAdminLogEventActionParticipantLeave")), "sale")
        self.assertIsNone(ventas._movimiento(accion("ChannelAdminLogEventActionChangeTitle")))


class TestPersonas(unittest.TestCase):
    def setUp(self):
        self.con = conexion()
        self.addCleanup(self.con.close)
        with self.con:
            ventas.guardar_canal(self.con, 1, "Lunes Tarde", TS)
            ventas.guardar_canal(self.con, 2, "Martes Noche", TS)
            ventas.guardar_canal(self.con, 3, "Stakazo 9", TS)

    def test_canales_y_gratuita(self):
        with self.con:
            db.actualizar_datos_usuario(self.con, TS, {"id": 500, "first_name": "Ana", "username": "ana"})
            db.actualizar_campos(self.con, 500, TS, enlace_venta_ts=int(TS), canal_venta="Lunes Tarde")
            ventas.guardar_persona(self.con, 500, "Ana", "ana")
            ventas.guardar_miembros(self.con, 1, [(500, TS)], TS)
            ventas.guardar_miembros(self.con, 2, [(500, TS + 86400)], TS)
            # Entró y salió de un tercero (solo se ve en el registro).
            ventas.guardar_movimientos(self.con, 3, [(10, 500, "entra", TS + 2 * 86400, "https://t.me/+x"),
                                                     (11, 500, "sale", TS + 3 * 86400, None)])
            ventas.guardar_persona(self.con, 600, "Luis", None)
            ventas.guardar_miembros(self.con, 1, [(600, TS)], TS)
        filas = ventas.filas_personas(self.con, MADRID)
        ana = filas[0]
        self.assertEqual(ana[:5], ["Ana", "@ana", 500, 3, 2])
        self.assertIn("Stakazo 9 (entró 22/10) (salió 23/10)", ana[5])
        self.assertEqual(ana[6], "Lunes Tarde")
        self.assertEqual((ana[7], ana[8]), ("Martes Noche · Stakazo 9", 2))
        luis = filas[1]
        self.assertEqual((luis[0], luis[6], luis[7], luis[8]), ("Luis", "", "Lunes Tarde", 1))

    def test_movimientos_sin_repetir(self):
        with self.con:
            self.assertEqual(ventas.guardar_movimientos(self.con, 1, [(1, 500, "entra", TS, None)]), 1)
            self.assertEqual(ventas.guardar_movimientos(self.con, 1, [(1, 500, "entra", TS, None)]), 0)
        filas = ventas.filas_movimientos(self.con, MADRID)
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0][1:], ["Lunes Tarde", "", "", 500, "Entra", ""])
        self.assertTrue(ventas.hay_datos(self.con))


class FalsoCliente:
    def __init__(self, miembros):
        self.miembros = miembros
        self.busquedas = []

    async def iter_participants(self, canal, search=None):
        if search:
            self.busquedas.append(search)
        for u in self.miembros:
            yield u


class TestCanales(unittest.TestCase):
    def test_solo_desde_el_debut(self):
        from unittest import mock

        def canal(titulo, dia):
            return SimpleNamespace(title=titulo, date=datetime(2026, 7, dia, 10, tzinfo=timezone.utc))
        todos = [canal("Viejo", 10), canal("Premier Galgos Debut", 22), canal("Lunes", 30),
                 canal("Prueba canal captación con bot", 30)]

        async def falsos(client, cfg):
            return todos, None
        with mock.patch.object(ventas.analisis, "canales_de_venta", falsos):
            lista = asyncio.run(ventas.canales(None, SimpleNamespace(tz=MADRID)))
        self.assertEqual([c.title for c in lista], ["Premier Galgos Debut", "Lunes"])


class TestLeerMiembros(unittest.TestCase):
    def test_fecha_de_entrada_y_sin_bots(self):
        bot = usuario(9, "Bot")
        bot.bot = True
        admin = usuario(7, "Socio", desde=TS)
        admin.participant = type("ChannelParticipantAdmin", (), {"date": None})()
        cliente = FalsoCliente([usuario(500, "Ana", desde=TS), bot, admin, usuario(600, "Luis")])
        leidos = asyncio.run(ventas.leer_miembros(cliente, "canal"))
        self.assertEqual([(u.id, d) for u, d in leidos], [(500, TS), (600, None)])
        self.assertEqual(cliente.busquedas, [])  # pocos: no hace falta buscar


@unittest.skipIf(importlib.util.find_spec("telethon") is None, "sin Telethon")
class TestRegistro(unittest.TestCase):
    def test_invitado_por_un_admin_cuenta_el_invitado(self):
        from telethon.tl import types

        canal = types.Channel(id=1, title="Lunes", photo=types.ChatPhotoEmpty(), date=None, access_hash=1)
        invitacion = types.ChannelAdminLogEventActionParticipantInvite(
            participant=types.ChannelParticipant(user_id=700, date=datetime.now(timezone.utc)))
        entra = types.ChannelAdminLogEventActionParticipantJoinByInvite(
            invite=SimpleNamespace(link="https://t.me/+abc"), via_chatlist=False)
        eventos = [
            SimpleNamespace(id=1, user_id=1, user=usuario(1, "Admin"), action=invitacion,
                            date=datetime.fromtimestamp(TS, timezone.utc), entities={700: usuario(700, "Eva")}),
            SimpleNamespace(id=2, user_id=500, user=usuario(500, "Ana"), action=entra,
                            date=datetime.fromtimestamp(TS, timezone.utc), entities={}),
        ]

        class Cliente:
            async def iter_admin_log(self, canal, **kw):
                for ev in eventos:
                    yield ev

        movs = asyncio.run(ventas.leer_registro(Cliente(), canal))
        self.assertEqual([(m[0], m[2], m[3], m[5]) for m in movs],
                         [(1, 700, "entra", None), (2, 500, "entra", "https://t.me/+abc")])
        self.assertEqual(movs[0][1].first_name, "Eva")


if __name__ == "__main__":
    unittest.main()
