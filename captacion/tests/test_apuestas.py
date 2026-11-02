"""Apuestas de cada canal de venta con su resultado de la hoja de picks
(apuestas.py). Datos INVENTADOS."""
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from premier_captacion import apuestas, db, publicaciones

from .test_cruce import canal

MADRID = ZoneInfo("Europe/Madrid")
T = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc).timestamp()
GRUPO = 77


class Hoja:
    def __init__(self, filas):
        self.filas = filas
        self.opciones = None

    def get_all_values(self, **kw):
        self.opciones = kw
        return self.filas


class Libro:
    def __init__(self, hojas):
        self.hojas = hojas

    def worksheet(self, nombre):
        return self.hojas[nombre]


def libro_picks():
    return Libro({
        "apuestas": Hoja([
            ["message_id", "stake", "oculto", "resultado_final", "unidades_netas"],
            [101, 3, False, "gano", 9.54],
            [102, 2, False, "perdio", -2],
            [103, 1, True, "perdio", -1],      # oculta: el dueño la descartó
            ["", "", "", "pendiente", ""],     # fila vacía con fórmulas
            ["104", "2", "FALSE", "gano", "3,5"],
        ]),
        "apuestas_exoticas": Hoja([
            ["message_id", "stake_total", "resultado_final", "unidades_netas", "oculto"],
            [201, 1, "gano", 12.4, False],
        ]),
    })


class TestLeerPicks(unittest.TestCase):
    def test_resultados_por_mensaje(self):
        libro = libro_picks()
        picks = apuestas.leer_picks(libro)
        self.assertEqual(picks[101], {"resultado": "gano", "unidades": 9.54, "stake": 3, "oculta": False})
        self.assertEqual(picks[102]["unidades"], -2)
        self.assertTrue(picks[103]["oculta"])
        self.assertEqual(picks[104], {"resultado": "gano", "unidades": 3.5, "stake": 2, "oculta": False})
        self.assertEqual(picks[201], {"resultado": "gano", "unidades": 12.4, "stake": 1, "oculta": False})
        self.assertEqual(len(picks), 5)
        self.assertEqual(libro.hojas["apuestas"].opciones, {"value_render_option": "UNFORMATTED_VALUE"})


def mensaje(con, chat_id, msg_id, ts, texto, reenvio=None):
    with con:
        publicaciones.guardar_mensajes(con, chat_id, [{"msg_id": msg_id, "ts": ts, "texto": texto, "hashes": [],
                                                       "reenvio": reenvio}])


class TestPorCanal(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        canal(self.con, 10, "Lunes")
        canal(self.con, 11, "Martes")
        with self.con:
            db.guardar_estado(self.con, publicaciones.CLAVE_GRUPO, GRUPO)
        self.picks = apuestas.leer_picks(libro_picks())

    def test_reenviada_mismo_texto_y_sin_encontrar(self):
        mensaje(self.con, 10, 1, T, "14:37 Harlow T5 Blundel Cuota 4.33 Stake 3")
        mensaje(self.con, 10, 2, T + 60, "Vamos equipo 💪")  # no es apuesta
        mensaje(self.con, 11, 1, T, "18:02 Hove T2 Rapido Cuota 2 Stake 2")
        mensaje(self.con, 11, 2, T, "20:15 Romford T1 Nada Cuota 3 Stake 1")
        mensaje(self.con, GRUPO, 101, T + 5, "14:37 Harlow T5 Blundel Cuota 4.33 Stake 3", reenvio=(10, 1))
        mensaje(self.con, GRUPO, 102, T + 9, "18:02 hove t2 rapido cuota 2 stake 2")
        lista = apuestas.por_canal(self.con, self.picks, MADRID)
        self.assertEqual([(a["msg_id"], a["en_grupo"], a["resultado"], a["unidades"]) for a in lista[10]],
                         [(1, "reenviado", "gano", 9.54)])
        self.assertEqual([(a["msg_id"], a["en_grupo"], a["resultado"], a["unidades"]) for a in lista[11]],
                         [(1, "mismo texto", "perdio", -2), (2, "no", None, None)])
        self.assertEqual(lista[10][0]["ts"], int(T))

    def test_la_oculta_no_suma(self):
        mensaje(self.con, 10, 1, T, "14:37 Harlow T5 Blundel Cuota 4.33 Stake 1")
        mensaje(self.con, GRUPO, 103, T + 5, "x", reenvio=(10, 1))
        a = apuestas.por_canal(self.con, self.picks, MADRID)[10][0]
        self.assertEqual((a["resultado"], a["unidades"], a["oculta"]), ("perdio", None, True))

    def test_un_aviso_con_una_hora_ya_pasada_no_es_apuesta(self):
        # Publicado a las 21:00: «mañana rondando las 11:00» no es una carrera de hoy.
        noche = datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc).timestamp()
        mensaje(self.con, 10, 1, noche, "Chicos empezaremos mañana rondando las 11:00, el stake lo digo luego")
        self.assertEqual(apuestas.por_canal(self.con, self.picks, MADRID), {})

    def test_mensajes_de_otros_chats_no_cuentan(self):
        mensaje(self.con, 99, 1, T, "14:37 Harlow T5 Cuota 4 Stake 1")  # no es canal de venta
        self.assertEqual(apuestas.por_canal(self.con, self.picks, MADRID), {})


if __name__ == "__main__":
    unittest.main()
