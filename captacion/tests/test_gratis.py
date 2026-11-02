"""Entradas gratis a los canales de venta: enlace por privado o publicado en
un canal fallado (gratis.py), y que no cuenten como candidatas en el cruce.
Datos INVENTADOS."""
import unittest

from premier_captacion import db, gratis, publicaciones

from .test_cruce import canal, compra, datos, entra_movimiento, miembro, venta_de

T = 1_000_000


def sale(con, canal_id, log_id, user_id, ts):
    with con:
        con.execute("INSERT INTO ventas_movimientos (canal_id, log_id, user_id, tipo, ts, enlace) "
                    "VALUES (?, ?, ?, 'sale', ?, NULL)", (canal_id, log_id, user_id, ts))


def enlace_de(con, h, canal_id):
    with con:
        db.guardar_enlace(con, h, canal_id, f"Canal {canal_id}", 1)


def privado(con, uid, ts, h, msg_id=1):
    with con:
        publicaciones.guardar_privados(con, uid, [(msg_id, ts, h)])


def publicado(con, canal_id, ts, h, msg_id=1):
    with con:
        publicaciones.guardar_mensajes(con, canal_id, [{"msg_id": msg_id, "ts": ts, "texto": "👉",
                                                        "hashes": [h], "reenvio": None}])


class ConCanales(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        canal(self.con, 10, "Lunes")
        canal(self.con, 11, "Martes")
        enlace_de(self.con, "hashmartes1", 11)


class TestPorPrivado(ConCanales):
    def test_enlace_antes_de_entrar_es_gratis(self):
        privado(self.con, 500, T, "hashmartes1")
        entra_movimiento(self.con, 11, 1, 500, T + 300, None)
        self.assertEqual(gratis.ofertas(self.con), {(11, 500): (T, gratis.PRIVADO)})
        self.assertEqual(gratis.para_cruce(self.con), {(11, 500)})

    def test_enlace_despues_de_entrar_no(self):
        entra_movimiento(self.con, 11, 1, 500, T, None)
        privado(self.con, 500, T + 300, "hashmartes1")
        self.assertEqual(gratis.para_cruce(self.con), set())

    def test_enlace_de_algo_que_no_es_canal_de_venta_no_cuenta(self):
        enlace_de(self.con, "hashprincipal", 99)
        privado(self.con, 500, T, "hashprincipal")
        privado(self.con, 500, T, "hashdesconocido", msg_id=2)
        self.assertEqual(gratis.ofertas(self.con), {})

    def test_vale_el_enlace_guardado_de_las_ventas(self):
        # El de overoption (mismo enlace para gratis y pagadas), aunque no
        # se haya preguntado a Telegram.
        compra(self.con, "v1", 12, T - 9999, "otro@example.com", entra=600)  # enlace https://t.me/+C12
        privado(self.con, 500, T, "C12")
        self.assertIn((12, 500), gratis.ofertas(self.con))


class TestEnElCanalFallado(ConCanales):
    def test_gratis_para_quien_estaba_dentro(self):
        miembro(self.con, 10, 500, T - 3600)      # dentro desde antes
        entra_movimiento(self.con, 10, 1, 501, T - 60, None)
        sale(self.con, 10, 2, 501, T - 30)        # salió antes de la publicación
        entra_movimiento(self.con, 10, 3, 502, T + 60, None)  # entró después
        publicado(self.con, 10, T, "hashmartes1")
        self.assertEqual(gratis.ofertas(self.con), {(11, 500): (T, gratis.CANAL)})

    def test_volver_a_entrar_tras_salir_cuenta(self):
        entra_movimiento(self.con, 10, 1, 501, T - 600, None)
        sale(self.con, 10, 2, 501, T - 500)
        entra_movimiento(self.con, 10, 3, 501, T - 400, None)
        publicado(self.con, 10, T, "hashmartes1")
        self.assertIn((11, 501), gratis.ofertas(self.con))

    def test_el_enlace_del_mismo_canal_no_es_compensacion(self):
        enlace_de(self.con, "hashlunes1", 10)
        miembro(self.con, 10, 500, T - 3600)
        publicado(self.con, 10, T, "hashlunes1")
        self.assertEqual(gratis.ofertas(self.con), {})

    def test_se_queda_la_primera_oferta(self):
        miembro(self.con, 10, 500, T - 3600)
        publicado(self.con, 10, T, "hashmartes1")
        privado(self.con, 500, T - 100, "hashmartes1")
        self.assertEqual(gratis.ofertas(self.con)[(11, 500)], (T - 100, gratis.PRIVADO))


class TestEnElCruce(ConCanales):
    def test_la_gratis_no_es_candidata(self):
        # Ana entra gratis justo cuando otro paga el mismo canal: no es su compra.
        compra(self.con, "v1", 11, T, "luis@example.com", entra=(500, 501))
        privado(self.con, 500, T - 600, "C11")
        v = venta_de(datos(self.con), "v1")
        self.assertEqual(v["candidatos"], {501})


if __name__ == "__main__":
    unittest.main()
