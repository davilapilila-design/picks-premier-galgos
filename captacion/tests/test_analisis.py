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

    def test_la_misma_apuesta_en_dos_canales_vale_con_un_reenvio_y_el_dia_importa(self):
        otra = {"canal_id": 8, "msg_id": 9, "fecha": date(2026, 10, 20), "texto": PICK}
        apuestas = [self.apuesta(1), otra, self.apuesta(3, dia=10)]
        picks = [{"fecha": date(2026, 10, 20), "texto": PICK, "reenvio": (8, 9)}]  # reenviada desde el otro canal
        self.assertEqual([a["msg_id"] for a in analisis.emparejar(apuestas, picks)], [3])

    def test_misma_hora_pero_otro_galgo_no_cuenta(self):
        apuestas = [self.apuesta(1, "Harlow 13:12 Galgo T2 X Cuota 1.90 Stake 6")]
        picks = [{"fecha": date(2026, 10, 20), "texto": "Harlow 13:12 Galgo T4 Y Cuota 3", "reenvio": None}]
        self.assertEqual(len(analisis.emparejar(apuestas, picks)), 1)

    def test_trampas(self):
        self.assertEqual(analisis.trampas("Galgo T5 Blundel Croia"), {"5"})
        self.assertEqual(analisis.trampas("Gemela reversible 3/4 4/3 Total Stake 4"), {"3", "4"})
        self.assertEqual(analisis.trampas("Galgo 3 Rapid Lad Cuota 3.50"), {"3"})


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
        venta_grupo = types.Chat(id=9, title="Miercoles Harlow 8.50", photo=None, participants_count=3,
                                 date=None, version=1)
        persona = types.User(id=500, first_name="Ana")
        otro_tipster = types.Channel(id=11, title="Tipster ajeno", photo=None, date=None, broadcast=True)
        de_la_regla = types.Channel(id=12, title="Jueves Central Park", photo=None, date=None, broadcast=True)
        grupo = types.Channel(id=8, title="Picks Premier Galgos", photo=None, date=None, megagroup=True)
        cuando = datetime(2026, 8, 1, 18, 0, tzinfo=timezone.utc)
        mensajes = {
            7: [SimpleNamespace(id=1, message=PICK, photo=None, date=cuando),
                SimpleNamespace(id=2, message="", photo=object(), date=cuando),
                SimpleNamespace(id=3, message="Buenas tardes!", photo=None, date=cuando)],
            8: [SimpleNamespace(id=50, message="", fwd_from=SimpleNamespace(
                channel_post=1, from_id=types.PeerChannel(7)), date=cuando)],
            1000000001: [],
            9: [SimpleNamespace(id=4, message="Harlow 20:03 T3 Cuota 8.50 Stake 1", photo=None, date=cuando)],
            12: [],
        }

        class Cliente:
            async def __call__(self, peticion):
                return SimpleNamespace(filters=[SimpleNamespace(
                    id=3, title=SimpleNamespace(text="💰 CH. Venta"), pinned_peers=[],
                    include_peers=[principal, venta, grupo, venta_grupo, persona], broadcasts=True,
                    exclude_peers=[types.InputPeerChannel(11, 0)], exclude_archived=False)])

            async def iter_dialogs(self):
                for e in (persona, otro_tipster, de_la_regla, venta):
                    yield SimpleNamespace(entity=e, archived=False)

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
        self.assertEqual([a["msg_id"] for a in apuestas], [1, 4])
        self.assertEqual(resumen, [{"canal": "Premier Galgos Debut", "id": 7, "apuestas": 1, "solo_foto": 1},
                                   {"canal": "Miercoles Harlow 8.50", "id": 9, "apuestas": 1, "solo_foto": 0},
                                   {"canal": "Jueves Central Park", "id": 12, "apuestas": 0, "solo_foto": 0}])
        # La 1 estaba reenviada en el grupo; la 4 (de un grupo de venta) no.
        self.assertEqual([a["msg_id"] for a in analisis.emparejar(apuestas, picks)], [4])


class TestDatosApuesta(unittest.TestCase):
    def test_formatos_de_los_canales(self):
        self.assertEqual(analisis.datos_apuesta("14:37 Harlow\n\nGalgo T5 Blundel Croia\n\nCuota 4.33🔥\n\n⚠️Stake 3⚠️"),
                         {"tipo": "simple", "carreras": "14:37 Harlow", "galgos": "T5 Blundel Croia",
                          "cuota": "4.33", "stake": "3"})
        doble = analisis.datos_apuesta("Apuesta Doble\n\n20:46 Hove T2 Droopys Flare\n20:50 Central Park T5 Zari Aki"
                                       "\n\nCuota 2.59🔥\n\n⚠️Stake 6⚠️")
        self.assertEqual((doble["tipo"], doble["carreras"], doble["galgos"]),
                         ("doble", "20:46 Hove | 20:50 Central Park", "T2 Droopys Flare | T5 Zari Aki"))
        gemela = analisis.datos_apuesta("22:31 Star Pelaw\n\nGemela reversible 3/4 4/3\n\nTotal Stake 4")
        self.assertEqual((gemela["tipo"], gemela["galgos"], gemela["cuota"], gemela["stake"]),
                         ("gemela", "3-4 | 4-3", "", "4"))
        self.assertEqual(analisis.datos_apuesta("Sheffield 17:59 T1 Jacktavern Turbo Ciota 2.75")["carreras"],
                         "17:59 Sheffield")


class TestTodas(unittest.TestCase):
    def test_estado_en_el_grupo_de_cada_apuesta(self):
        base = {"canal": "Debut", "canal_id": 7, "fecha": date(2026, 10, 20), "hora": 1_792_500_000}
        apuestas = [dict(base, msg_id=1, texto=PICK, enlace="https://t.me/c/7/1"),
                    dict(base, msg_id=2, texto="Hove 14:07 T5 X Cuota 2 Stake 1"),
                    dict(base, msg_id=3, texto="Romford 11:20 T2 Y Cuota 4 Stake 1")]
        picks = [{"fecha": date(2026, 10, 20), "texto": PICK, "reenvio": (7, 1), "enlace": "https://t.me/c/8/50"},
                 {"fecha": date(2026, 10, 20), "texto": "Hove 14:07 trap 5", "reenvio": None, "enlace": "https://t.me/c/8/51"}]
        filas = analisis.filas_todas(apuestas, picks, MADRID)
        self.assertEqual([(f[8], f[9], f[10]) for f in filas], [
            ("sí", "reenviado", "https://t.me/c/8/50"),
            ("parecido", "misma hora y galgo", "https://t.me/c/8/51"),
            ("no", "no", ""),
        ])
        self.assertEqual(filas[0][2:8], ["https://t.me/c/7/1", "simple", "19:41 Central Park", "T3 Rapid Lad", "3.50", "2"])
