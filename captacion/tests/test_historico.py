import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

from premier_captacion import db, historico, mensajes
from premier_captacion.carpetas import Ajustes, CarpetasEnMemoria, Organizador
from zoneinfo import ZoneInfo

from .apoyo import conexion

MADRID = ZoneInfo("Europe/Madrid")
CANAL = 1234567890


def fecha(dia, hora=12):
    return datetime(2026, 9, dia, hora, 0, tzinfo=timezone.utc)


def persona(uid, nombre, bot=False, yo=False):
    return SimpleNamespace(id=uid, first_name=nombre, last_name=None, username=nombre.lower(), bot=bot, is_self=yo)


def mensaje(id_, chat, texto, out, dia, privado=True, url=None):
    entidades = [SimpleNamespace(url=url)] if url else []
    m = SimpleNamespace(id=id_, chat_id=chat.id, message=texto, out=out, date=fecha(dia),
                        is_private=privado, entities=entidades)

    async def get_chat():
        return chat

    m.get_chat = get_chat
    return m


class ClienteFalso:
    """Imita client.iter_messages de Telethon (búsqueda global y por chat)."""

    def __init__(self, chats):
        self.chats = chats  # {user_id: [mensajes en orden]}
        self.llamadas = []

    def iter_messages(self, entidad, search=None, min_id=0, reverse=False, limit=None):
        self.llamadas.append((entidad, search, min_id))

        async def gen():
            if entidad is None:  # búsqueda global
                todos = [m for lista in self.chats.values() for m in lista]
                for m in sorted(todos, key=lambda m: m.date, reverse=True):
                    if search.lower() in (m.message or "").lower():
                        yield m
            else:
                lista = [m for m in self.chats.get(entidad, []) if m.id > min_id]
                for m in (lista if reverse else list(reversed(lista)))[:limit]:
                    yield m

        return gen()


ANA, LUIS, EVA, AMIGO, BOT = (persona(500, "Ana"), persona(501, "Luis"), persona(502, "Eva"),
                              persona(600, "Amigo"), persona(700, "UnBot", bot=True))
BUENAS = mensajes.TEXTO_MANUAL_BUENAS
BUENOS_DIAS = mensajes.TEXTO_MANUAL_BUENOS_DIAS


def chats_de_ejemplo():
    return {
        # Ana: bienvenida «Buenas», responde, recibe primero el enlace del canal
        # principal (no cuenta) y luego uno de venta escondido tras un texto.
        500: [mensaje(10, ANA, BUENAS, True, 1),
              mensaje(11, ANA, "¡Es mi primera vez!", False, 1),
              mensaje(12, ANA, "Únete: t.me/+PRINCIPAL000001", True, 2),
              mensaje(13, ANA, "pulsa aquí", True, 3, url="https://t.me/+VENTA0000000001")],
        # Luis: «Buenas tardes y bienvenido a Premier Galgos» (variante), no responde.
        501: [mensaje(20, LUIS, "Buenas tardes y bienvenido a Premier Galgos! 🐾", True, 5)],
        # Eva: bienvenida «Buenos días», contesta y le dan enlace.
        502: [mensaje(30, EVA, BUENOS_DIAS, True, 7),
              mensaje(31, EVA, "sí, ya he apostado alguna vez", False, 7),
              mensaje(32, EVA, "t.me/+VENTA0000000001", True, 8)],
        # Cosas que NO son bienvenidas manuales del dueño:
        600: [mensaje(40, AMIGO, "bienvenido a casa", True, 9),
              mensaje(41, AMIGO, BUENAS, False, 9)],  # se la reenvió el amigo al dueño
        700: [mensaje(50, BOT, BUENAS, True, 9)],
    }


class TestHistorico(unittest.TestCase):
    def setUp(self):
        self.con = conexion()
        self.addCleanup(self.con.close)
        tg = CarpetasEnMemoria(destinos={"PRINCIPAL000001": (CANAL, "PREMIER GALGOS"),
                                         "VENTA0000000001": (555, "Canal VIP")})
        self.org = Organizador(self.con, tg, MADRID, Ajustes(canal_principal=CANAL))
        self.cliente = ClienteFalso(chats_de_ejemplo())

    def leer(self):
        with mock.patch.object(historico, "PAUSA_ENTRE_CHATS_S", 0):
            return asyncio.run(historico.leer(self.cliente, self.con, self.org))

    def test_clasifica_las_bienvenidas(self):
        self.assertEqual(historico.tipo_bienvenida_manual(BUENAS), "manual_buenas")
        self.assertEqual(historico.tipo_bienvenida_manual(BUENOS_DIAS), "manual_buenos_dias")
        self.assertEqual(historico.tipo_bienvenida_manual("Buenas tardes y bienvenida a premier galgos"),
                         "manual_buenos_dias")
        self.assertIsNone(historico.tipo_bienvenida_manual("bienvenido a casa"))
        self.assertIsNone(historico.tipo_bienvenida_manual(None))

    def test_lee_todo(self):
        resultado = self.leer()
        self.assertEqual(resultado, {"personas": 3, "por_tipo": {"manual_buenas": 1, "manual_buenos_dias": 2},
                                     "respondieron": 2, "con_enlace": 2})
        ana = db.obtener_usuario(self.con, 500)
        self.assertTrue(db.es_del_embudo(ana))  # el bot ya no le repetirá la bienvenida
        self.assertEqual(ana["bienvenida_tipo"], "manual_buenas")
        self.assertEqual(ana["bienvenida_ts"], int(fecha(1).timestamp()))
        self.assertEqual(ana["boton"], "primera_vez")
        self.assertEqual((ana["enlace_venta"], ana["canal_venta"]), ("https://t.me/+VENTA0000000001", "Canal VIP"))
        self.assertEqual(ana["enlace_venta_ts"], int(fecha(3).timestamp()))  # el del canal principal no cuenta
        luis = db.obtener_usuario(self.con, 501)
        self.assertEqual((luis["bienvenida_tipo"], luis["primer_mensaje_ts"]), ("manual_buenos_dias", None))
        self.assertEqual(db.obtener_usuario(self.con, 502)["boton"], "ya_apostado")
        self.assertIsNone(db.obtener_usuario(self.con, 600))
        self.assertIsNone(db.obtener_usuario(self.con, 700))

    def test_se_puede_repetir_sin_duplicar(self):
        self.leer()
        antes = self.con.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
        self.leer()
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM eventos").fetchone()[0], antes)

    def test_si_ya_tenia_la_del_bot_se_queda_la_primera(self):
        with self.con:
            db.actualizar_datos_usuario(self.con, 1, {"id": 500, "first_name": "Ana"})
            db.marcar_bienvenida(self.con, 500, int(fecha(20).timestamp()), "bot_b_v1")
        self.leer()
        self.assertEqual(db.obtener_usuario(self.con, 500)["bienvenida_tipo"], "manual_buenas")

    def test_resumen(self):
        texto = historico.texto_resumen(self.leer())
        self.assertIn("3 personas con bienvenida manual", texto)
        self.assertIn("✉️ Te contestaron: 2", texto)
        self.assertIn("🔗 Recibieron enlace de venta: 2", texto)


if __name__ == "__main__":
    unittest.main()
