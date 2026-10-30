"""Copia para Drive de todo lo que usa el cruce de ventas (copia.py).
Datos INVENTADOS."""
import contextlib
import csv
import io
import os
import sqlite3
import tempfile
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from premier_captacion import copia, db

from .test_cruce import canal, entra_movimiento, persona, venta

MADRID = ZoneInfo("Europe/Madrid")


class TestExportar(unittest.TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(carpeta.cleanup)
        self.dir = carpeta.name
        self.ruta = os.path.join(self.dir, "real.db")
        self.con = db.abrir(self.ruta)
        self.addCleanup(self.con.close)
        canal(self.con, 10, "Canal X")
        persona(self.con, 500, nombre="Ana", username="ana")
        entra_movimiento(self.con, 10, 1, 500, 1000, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 1000, correo="ana@example.com")
        self.con.commit()
        self.salida = os.path.join(self.dir, "salida")
        os.mkdir(self.salida)

    def exportar(self):
        copia.exportar(self.con, self.salida, MADRID)

    def leer(self, nombre):
        with open(os.path.join(self.salida, nombre), encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def test_copia_entera_de_la_base(self):
        self.exportar()
        c = sqlite3.connect(os.path.join(self.salida, "captacion.db"))
        try:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM pagos_overoption").fetchone()[0], 1)
        finally:
            c.close()

    def test_un_csv_por_tabla_con_las_fechas_legibles(self):
        self.exportar()
        for tabla in copia.TABLAS:
            self.assertTrue(os.path.exists(os.path.join(self.salida, f"{tabla}.csv")), tabla)
        mov = self.leer("ventas_movimientos.csv")[0]
        self.assertEqual(mov["user_id"], "500")
        self.assertEqual(mov["ts_fecha"], "1970-01-01 01:16:40")  # 1000 s, hora de España

    def test_resultado_del_cruce(self):
        self.exportar()
        fila = self.leer("cruce_ventas.csv")[0]
        self.assertEqual((fila["id"], fila["estado_cruce"], fila["user_id"]), ("v1", "emparejada", "500"))
        self.assertIn("pago_ts_fecha", fila)

    def test_leeme_y_nunca_la_sesion_de_telegram(self):
        open(os.path.join(self.dir, "real-cuenta.session"), "w").close()
        self.exportar()
        nombres = os.listdir(self.salida)
        self.assertIn("LEEME.txt", nombres)
        self.assertFalse(any("session" in n for n in nombres))

    def test_main_lee_la_base_sin_tocarla(self):
        with mock.patch.dict("os.environ", {"CAPTACION_DB": self.ruta}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(copia.main([self.salida]), 0)
        self.assertEqual(len(self.leer("pagos_overoption.csv")), 1)

    def test_main_sin_carpeta(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(copia.main([]), 2)


if __name__ == "__main__":
    unittest.main()
