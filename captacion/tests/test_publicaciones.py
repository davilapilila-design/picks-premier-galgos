"""Lectura de los mensajes de los canales de venta y del grupo de picks, y de
los enlaces que el dueño manda por privado (publicaciones.py). Telegram
falso y datos INVENTADOS."""
import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

from premier_captacion import db, publicaciones

MADRID = ZoneInfo("Europe/Madrid")
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc).timestamp()
CFG = SimpleNamespace(tz=MADRID)


def mensaje(mid, ts, texto="", out=False, url=None, reenvio=None):
    fwd = None
    if reenvio is not None:
        fwd = SimpleNamespace(channel_post=reenvio[1], from_id=SimpleNamespace(channel_id=reenvio[0]))
    entidades = [SimpleNamespace(url=url)] if url else []
    return SimpleNamespace(id=mid, date=datetime.fromtimestamp(ts, timezone.utc), message=texto, out=out,
                           entities=entidades, fwd_from=fwd)


def chat(cid, titulo="Canal", dia=1):
    return SimpleNamespace(id=cid, title=titulo, date=datetime(2026, 8, dia, tzinfo=timezone.utc))


def persona(uid, bot=False, yo=False):
    return SimpleNamespace(id=uid, bot=bot, is_self=yo, deleted=False)


def dialogo(entidad, ts, fijado=False):
    return SimpleNamespace(entity=entidad, date=datetime.fromtimestamp(ts, timezone.utc), pinned=fijado,
                           is_user=hasattr(entidad, "is_self"))


class Cliente:
    """Imita lo que se usa de Telethon: iter_messages (en los dos sentidos)
    e iter_dialogs. Puede lanzar un FloodWaitError la primera vez."""

    def __init__(self, mensajes, dialogos=(), esperas=0):
        self.mensajes = mensajes  # chat_id -> [mensaje]
        self.dialogos = list(dialogos)
        self.esperas = esperas
        self.llamadas = []

    async def iter_messages(self, entidad, reverse=False, min_id=0, offset_date=None, filter=None):
        self.llamadas.append((entidad.id, reverse, min_id, offset_date, filter))
        if self.esperas:
            self.esperas -= 1
            error = type("FloodWaitError", (Exception,), {})("espera")
            error.seconds = 7
            raise error
        lista = sorted(self.mensajes.get(entidad.id, []), key=lambda m: m.id)
        if reverse:
            for m in lista:
                if m.id > min_id and (offset_date is None or m.date >= offset_date):
                    yield m
        else:
            for m in reversed(lista):
                if filter is None or m.entities or "t.me" in (m.message or ""):
                    yield m

    async def iter_dialogs(self):
        for d in self.dialogos:
            yield d


class ConBase(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        self.destinos = {"abcdefgh1": (10, "Lunes"), "abcdefgh2": (11, "Martes")}
        self.preguntas = []
        self.dormido = []

    async def destino(self, h):
        self.preguntas.append(h)
        return self.destinos.get(h, (None, None))

    async def dormir(self, s):
        self.dormido.append(s)


class TestGuardar(ConBase):
    def test_sin_duplicar(self):
        fila = {"msg_id": 1, "ts": T0, "texto": "hola", "hashes": ["abcdefgh1"], "reenvio": None}
        with self.con:
            publicaciones.guardar_mensajes(self.con, 10, [fila])
            publicaciones.guardar_mensajes(self.con, 10, [fila])
            publicaciones.guardar_privados(self.con, 500, [(7, T0, "abcdefgh1"), (7, T0, "abcdefgh1")])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM publicaciones").fetchone()[0], 1)
        self.assertEqual(publicaciones.ultimo(self.con, 10), 1)
        self.assertIsNone(publicaciones.ultimo(self.con, 99))
        self.assertEqual([tuple(f) for f in self.con.execute("SELECT * FROM enlaces_privados")],
                         [(500, 7, int(T0), "abcdefgh1")])


class TestLeerCanales(ConBase):
    def leer(self, cliente, canales, grupo):
        async def falsos(client, cfg):
            return canales, grupo
        with mock.patch.object(publicaciones.analisis, "canales_de_venta", falsos):
            return asyncio.run(publicaciones.leer_canales(cliente, self.con, CFG, self.destino, dormir=self.dormir))

    def test_lee_canales_y_grupo_y_sigue_por_donde_iba(self):
        lunes, grupo = chat(10, "Lunes"), chat(20, "Picks Premier Galgos")
        cliente = Cliente({
            10: [mensaje(1, T0, "14:37 Harlow T5 Cuota 4.33 Stake 3"),
                 mensaje(2, T0 + 60, "Compensación 👉 https://t.me/+abcdefgh2"),
                 mensaje(3, T0 + 90, "")],  # foto sin texto ni enlace: fuera
            20: [mensaje(5, T0 + 30, "14:37 Harlow T5", reenvio=(10, 1))],
        })
        self.assertEqual(self.leer(cliente, [lunes], grupo), 3)
        filas = [tuple(f) for f in self.con.execute(
            "SELECT chat_id, msg_id, enlaces, reenvio_chat, reenvio_msg FROM publicaciones ORDER BY chat_id, msg_id")]
        self.assertEqual(filas, [(10, 1, "", None, None), (10, 2, "abcdefgh2", None, None), (20, 5, "", 10, 1)])
        self.assertEqual(db.leer_estado(self.con, publicaciones.CLAVE_GRUPO), "20")
        self.assertEqual(self.preguntas, ["abcdefgh2"])  # el destino de cada enlace nuevo, una vez
        self.assertEqual(db.enlace_guardado(self.con, "abcdefgh2")["chat_id"], 11)
        # La primera vez, desde el 22/07; luego, desde el último mensaje guardado.
        self.assertEqual(cliente.llamadas[0][2], 0)
        self.assertEqual(cliente.llamadas[0][3].date().isoformat(), "2026-07-22")
        cliente.mensajes[10].append(mensaje(4, T0 + 120, "otra https://t.me/+abcdefgh2"))
        self.assertEqual(self.leer(cliente, [lunes], grupo), 1)
        self.assertEqual(cliente.llamadas[-2][2], 3)  # Lunes desde el 3 (el 3 se leyó aunque no se guardó)
        self.assertEqual(self.preguntas, ["abcdefgh2"])  # ya estaba en la caché

    def test_enlace_detras_de_un_texto(self):
        cliente = Cliente({10: [mensaje(1, T0, "Pulsa aquí", url="https://t.me/+abcdefgh1")]})
        self.leer(cliente, [chat(10)], None)
        self.assertEqual(self.con.execute("SELECT enlaces FROM publicaciones").fetchone()[0], "abcdefgh1")

    def test_si_telegram_pide_esperar_espera_y_sigue(self):
        cliente = Cliente({10: [mensaje(1, T0, "14:37 Harlow T5 Cuota 2 Stake 1")]}, esperas=1)
        self.assertEqual(self.leer(cliente, [chat(10)], None), 1)
        self.assertEqual(self.dormido[0], 8)

    def test_un_canal_que_falla_no_para_los_demas(self):
        class Roto(Cliente):
            async def iter_messages(self, entidad, **kw):
                if entidad.id == 10:
                    raise RuntimeError("sin acceso")
                async for m in super().iter_messages(entidad, **kw):
                    yield m
        cliente = Roto({11: [mensaje(1, T0, "hola")]})
        self.assertEqual(self.leer(cliente, [chat(10), chat(11)], None), 1)


class TestLeerPrivados(ConBase):
    def leer(self, cliente, ahora):
        with mock.patch.object(publicaciones, "_filtro_url", lambda: "URL"):
            return asyncio.run(publicaciones.leer_privados(cliente, self.con, CFG, self.destino,
                                                           dormir=self.dormir, ahora=ahora))

    def test_solo_los_enlaces_que_manda_el_dueno(self):
        ana, luis, bot = persona(500), persona(501), persona(9, bot=True)
        cliente = Cliente({
            500: [mensaje(1, T0, "toma https://t.me/+abcdefgh1", out=True),
                  mensaje(2, T0 + 5, "y este https://t.me/+abcdefgh9", out=False),  # lo manda ella
                  mensaje(3, T0 + 9, "hola", out=True)],
            501: [mensaje(4, T0, "Pulsa aquí", out=True, url="https://t.me/+abcdefgh2")],
            9: [mensaje(5, T0, "https://t.me/+abcdefgh1", out=True)],
        }, dialogos=[dialogo(ana, T0 + 9), dialogo(luis, T0), dialogo(bot, T0)])
        self.assertEqual(self.leer(cliente, ahora=T0 + 100), 2)
        filas = [tuple(f) for f in self.con.execute("SELECT user_id, msg_id, hash FROM enlaces_privados ORDER BY 1")]
        self.assertEqual(filas, [(500, 1, "abcdefgh1"), (501, 4, "abcdefgh2")])
        self.assertEqual(sorted(self.preguntas), ["abcdefgh1", "abcdefgh2"])
        self.assertEqual(db.leer_estado(self.con, publicaciones.CLAVE_PRIVADOS), str(int(T0 + 100)))

    def test_la_siguiente_vez_solo_lo_nuevo(self):
        ana, luis = persona(500), persona(501)
        cliente = Cliente({500: [mensaje(1, T0, "https://t.me/+abcdefgh1", out=True)],
                           501: [mensaje(2, T0 - 9 * 86400, "https://t.me/+abcdefgh2", out=True)]},
                          dialogos=[dialogo(ana, T0), dialogo(luis, T0 - 9 * 86400)])
        with self.con:
            db.guardar_estado(self.con, publicaciones.CLAVE_PRIVADOS, int(T0 - 86400))
        self.leer(cliente, ahora=T0 + 100)
        self.assertEqual([c[0] for c in cliente.llamadas], [500])  # el chat de Luis no se mira
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM enlaces_privados").fetchone()[0], 1)

    def test_los_fijados_antiguos_no_cortan(self):
        viejo, ana = persona(502), persona(500)
        cliente = Cliente({500: [mensaje(1, T0, "https://t.me/+abcdefgh1", out=True)]},
                          dialogos=[dialogo(viejo, T0 - 99 * 86400, fijado=True), dialogo(ana, T0)])
        with self.con:
            db.guardar_estado(self.con, publicaciones.CLAVE_PRIVADOS, int(T0 - 86400))
        self.assertEqual(self.leer(cliente, ahora=T0 + 100), 1)


if __name__ == "__main__":
    unittest.main()
