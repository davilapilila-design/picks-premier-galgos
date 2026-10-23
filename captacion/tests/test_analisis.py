import asyncio
import importlib.util
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from premier_captacion import analisis, db

from .apoyo import conexion, usuario

MADRID = ZoneInfo("Europe/Madrid")
PICK = "Central Park 19:41 Galgo 3 Rapid Lad\nCuota 3.50🔥 Stake 2"


class TestDetectarApuestas(unittest.TestCase):
    def test_horas_con_erratas(self):
        self.assertEqual(analisis.horas("Romford 9;05 y Hove 21:12"), {"09:05", "21:12"})
        self.assertEqual(analisis.horas("Cuota 3.50 stake 2"), frozenset())

    def test_que_es_una_apuesta(self):
        self.assertTrue(analisis.es_apuesta(PICK))
        self.assertTrue(analisis.es_apuesta("Harlow 20:03 GEMELA 3-4 y 4-3 stake 2"))
        self.assertTrue(analisis.es_apuesta("Sheffield 17:59 T1 Jacktavern Turbo Ciota 2.75"))
        self.assertFalse(analisis.es_apuesta("Hoy a las 18:45 os paso el pack 💙"))
        self.assertFalse(analisis.es_apuesta("Cuota 2.50 que bien!"))


class TestEmparejar(unittest.TestCase):
    def apuesta(self, msg_id, texto=PICK, dia=20):
        return {"canal_id": 7, "msg_id": msg_id, "fecha": date(2026, 10, dia), "texto": texto}

    def test_por_reenvio_o_por_horas_y_dia(self):
        apuestas = [self.apuesta(1), self.apuesta(2, "Hove 14:07 T5 X Cuota 2 Stake 1"),
                    self.apuesta(3, "Romford 11:20 T2 Y Cuota 4 Stake 1")]
        picks = [{"fecha": date(2026, 10, 25), "texto": "", "reenvio": (7, 1)},
                 {"fecha": date(2026, 10, 21), "texto": "Hove 14:07 trap 5", "reenvio": None}]
        self.assertEqual([a["msg_id"] for a in analisis.emparejar(apuestas, picks)], [3])

    def test_cada_mensaje_del_grupo_cuenta_una_vez_y_el_dia_importa(self):
        apuestas = [self.apuesta(1), self.apuesta(2), self.apuesta(3, dia=10)]
        picks = [{"fecha": date(2026, 10, 20), "texto": PICK, "reenvio": None}]
        self.assertEqual([a["msg_id"] for a in analisis.emparejar(apuestas, picks)], [2, 3])


class TestInforme(unittest.TestCase):
    def test_resumen_por_canal(self):
        apuestas = [{"canal": "Debut", "canal_id": 7, "msg_id": i, "hora": 1_792_500_000, "texto": PICK}
                    for i in (1, 2, 3)]
        sin_picks, canales = analisis.filas_informe(apuestas, apuestas[2:],
                                                    [{"canal": "Debut", "id": 7, "apuestas": 3, "solo_foto": 1}], MADRID)
        self.assertEqual(canales, [["Debut", 3, 2, 1, 1]])
        self.assertEqual(sin_picks[0][1:3], ["Debut", 3])


class TestChats(unittest.TestCase):
    def test_etapas_alias_y_quien(self):
        con = conexion()
        self.addCleanup(con.close)
        with con:
            for uid in (500, 501):
                db.actualizar_datos_usuario(con, 1, usuario(uid))
                db.marcar_bienvenida(con, uid, 1, "manual_buenas")
            db.actualizar_campos(con, 500, 1, enlace_venta_ts=2_000)
        dt = lambda ts: datetime.fromtimestamp(ts, timezone.utc)  # noqa: E731
        chats = {
            500: [SimpleNamespace(message="gracias", out=False, date=dt(3_000)),
                  SimpleNamespace(message="aquí la tienes", out=True, date=dt(1_500))],
            501: [SimpleNamespace(message="hola", out=False, date=dt(1_000))],
            999: [SimpleNamespace(message="no es cliente", out=False, date=dt(1_000))],
        }

        class Cliente:
            async def iter_dialogs(self):
                for uid in chats:
                    yield SimpleNamespace(is_user=True, entity=SimpleNamespace(id=uid))

            async def iter_messages(self, entidad, limit=None):
                for m in chats[entidad.id]:  # de más nuevo a más antiguo, como Telegram
                    yield m

        async def sin_esperas(_):
            pass

        orig = analisis.asyncio.sleep
        analisis.asyncio.sleep = sin_esperas
        try:
            filas = asyncio.run(analisis.leer_chats(Cliente(), con, MADRID))
        finally:
            analisis.asyncio.sleep = orig
        self.assertEqual([(f[0], f[1], f[4], f[5]) for f in filas], [
            ("C0001", "antes de la gratuita", "tú", "aquí la tienes"),
            ("C0001", "después de la gratuita", "cliente", "gracias"),
            ("C0002", "sin gratuita", "cliente", "hola"),
        ])


@unittest.skipUnless(importlib.util.find_spec("telethon"), "necesita Telethon (venv de la VM)")
class TestLeerCanales(unittest.TestCase):
    def test_canales_de_la_carpeta_y_grupo_de_picks(self):
        from telethon.tl import types

        from premier_captacion.config import cargar_config
        cfg = cargar_config({"CAPTACION_DB": "/tmp/x.db", "CAPTACION_CANAL_ID": "-1001000000001"},
                            requiere_bot=False)
        principal = types.Channel(id=1000000001, title="PREMIER GALGOS", photo=None, date=None, broadcast=True)
        venta = types.Channel(id=7, title="Premier Galgos Debut", photo=None, date=None, broadcast=True)
        grupo = types.Channel(id=8, title="Picks Premier Galgos", photo=None, date=None, megagroup=True)
        cuando = datetime(2026, 8, 1, 18, 0, tzinfo=timezone.utc)
        mensajes = {
            7: [SimpleNamespace(id=1, message=PICK, photo=None, date=cuando),
                SimpleNamespace(id=2, message="", photo=object(), date=cuando),
                SimpleNamespace(id=3, message="Buenas tardes!", photo=None, date=cuando)],
            8: [SimpleNamespace(id=50, message="", fwd_from=SimpleNamespace(
                channel_post=1, from_id=types.PeerChannel(7)), date=cuando)],
            1000000001: [],
        }

        class Cliente:
            async def __call__(self, peticion):
                return SimpleNamespace(filters=[SimpleNamespace(
                    title=SimpleNamespace(text="CH ventas"), pinned_peers=[],
                    include_peers=[principal, venta, grupo])])

            async def get_entity(self, peer):
                return peer

            async def iter_messages(self, ent, offset_date=None, reverse=False):
                for m in mensajes[ent.id]:
                    yield m

        async def sin_esperas(_):
            pass

        orig = analisis.asyncio.sleep
        analisis.asyncio.sleep = sin_esperas
        try:
            apuestas, picks, resumen = asyncio.run(analisis.leer_canales(Cliente(), cfg, MADRID))
        finally:
            analisis.asyncio.sleep = orig
        self.assertEqual([a["msg_id"] for a in apuestas], [1])
        self.assertEqual(resumen, [{"canal": "Premier Galgos Debut", "id": 7, "apuestas": 1, "solo_foto": 1}])
        self.assertEqual(analisis.emparejar(apuestas, picks), [])  # estaba reenviada en el grupo
