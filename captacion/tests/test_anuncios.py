"""Anuncios de venta del canal principal y cuándo hay una venta abierta
(anuncios.py). Datos INVENTADOS."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from premier_captacion import anuncios, db, publicaciones

from .test_cruce import canal, venta

LONDRES = ZoneInfo("Europe/London")
PRINCIPAL = 500
A = datetime(2026, 9, 10, 16, 45, tzinfo=LONDRES).timestamp()  # hora del anuncio
ANUNCIO = "Estas 3 apuestas por solo 36 € ⬇️\nhttps://payoption.io/Ejemplo/abc\n\nMucha suerte"
H = 3600


def hora(hh, mm):
    return datetime(2026, 9, 10, hh, mm, tzinfo=LONDRES).timestamp()


def mensaje(con, chat_id, msg_id, ts, texto):
    with con:
        publicaciones.guardar_mensajes(con, chat_id, [{"msg_id": msg_id, "ts": ts, "texto": texto, "hashes": [],
                                                       "reenvio": None}])


class TestEsAnuncio(unittest.TestCase):
    def test_con_enlace_de_pago(self):
        self.assertTrue(anuncios.es_anuncio(ANUNCIO))
        self.assertTrue(anuncios.es_anuncio("Por 30 € aquí: overoption.io/Ejemplo/xyz"))

    def test_sin_enlace_de_pago(self):
        self.assertFalse(anuncios.es_anuncio("Vamos equipo, mañana más 💪"))
        self.assertFalse(anuncios.es_anuncio("Entra aquí: https://t.me/+abcdefgh1"))
        self.assertFalse(anuncios.es_anuncio(None))


class TestAbiertas(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        canal(self.con, 10, "Lunes tarde 10.09")
        canal(self.con, 11, "Lunes noche 10.09")
        mensaje(self.con, PRINCIPAL, 1, A, ANUNCIO)

    def abiertas(self, ahora):
        return anuncios.abiertas(self.con, PRINCIPAL, ahora)

    def compra(self, vid, ts, producto="Lunes tarde 10.09"):
        venta(self.con, vid, f"https://t.me/+{vid}", ts, producto=producto)

    def test_sin_compras_ni_carreras_abierta_cuatro_horas(self):
        self.assertEqual(self.abiertas(A + 60), [(A, A + 4 * H)])
        self.assertEqual(self.abiertas(A + 4 * H), [])

    def test_antes_del_anuncio_no(self):
        self.assertEqual(self.abiertas(A - 60), [])

    def test_otro_mensaje_del_canal_principal_no_abre_nada(self):
        mensaje(self.con, PRINCIPAL, 2, A + 600, "Hoy descansamos, mañana más")
        self.assertEqual(self.abiertas(A + 700), [(A, A + 4 * H)])

    def test_hasta_quince_minutos_despues_de_la_ultima_carrera(self):
        self.compra("v1", A + 30)
        self.compra("v2", A + 90)
        mensaje(self.con, 10, 1, A + 60, "17:20 Romford T3 Rapido Cuota 4 Stake 2")
        mensaje(self.con, 10, 2, A + 70, "18:02 Hove T1 Veloz Cuota 3 Stake 1")
        fin = hora(18, 2) + 15 * 60
        self.assertEqual(self.abiertas(fin - 60), [(A, fin)])
        self.assertEqual(self.abiertas(fin), [])

    def test_el_canal_es_el_de_la_mayoria_de_las_compras(self):
        self.compra("v1", A + 30)
        self.compra("v2", A + 40)
        self.compra("v3", A + 50, producto="Lunes noche 10.09")  # compra tardía de otra venta
        mensaje(self.con, 10, 1, A + 60, "17:20 Romford T3 Rapido Cuota 4 Stake 2")
        mensaje(self.con, 11, 1, A + 60, "21:40 Hove T6 Lento Cuota 5 Stake 1")
        self.assertEqual(self.abiertas(A + 60), [(A, hora(17, 35))])

    def test_las_apuestas_de_otro_canal_no_cuentan(self):
        self.compra("v1", A + 30)
        mensaje(self.con, 11, 1, A + 60, "22:00 Hove T6 Lento Cuota 5 Stake 1")
        self.assertEqual(self.abiertas(A + 60), [(A, A + 4 * H)])

    def test_un_aviso_con_la_hora_ya_pasada_no_alarga_la_venta(self):
        self.compra("v1", A + 30)
        mensaje(self.con, 10, 1, A + 60, "17:20 Romford T3 Rapido Cuota 4 Stake 2")
        mensaje(self.con, 10, 2, hora(19, 30), "Mañana a las 11:00 más cuotas, el stake lo digo luego")
        self.assertEqual(self.abiertas(A + 60), [(A, hora(17, 35))])

    def test_nunca_mas_de_ocho_horas(self):
        temprano = hora(13, 0)
        mensaje(self.con, PRINCIPAL, 3, temprano, ANUNCIO)
        venta(self.con, "v9", "https://t.me/+v9", temprano + 30, producto="Lunes noche 10.09")
        mensaje(self.con, 11, 1, temprano + 60, "23:40 Hove T6 Lento Cuota 5 Stake 1")
        self.assertEqual(self.abiertas(temprano + 60), [(temprano, temprano + 8 * H)])
        self.assertEqual(self.abiertas(temprano + 8 * H + 60), [])  # y la de A ya cerró (4 h)

    def test_un_anuncio_antiguo_no_abre_nada(self):
        self.assertEqual(self.abiertas(A + 9 * H), [])


if __name__ == "__main__":
    unittest.main()
