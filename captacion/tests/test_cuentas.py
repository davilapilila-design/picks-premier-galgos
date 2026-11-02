"""Cuentas por persona de Telegram: canales pagados, gratis y sin explicar,
apuestas, unidades, simulación a 10 €/unidad y balance (cuentas.py). Datos
INVENTADOS."""
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from premier_captacion import cruce, cuentas, db, publicaciones

from .test_cruce import compra, entra_movimiento, indicar, persona

MADRID = ZoneInfo("Europe/Madrid")
T = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc).timestamp()  # 11:00 en Londres
DESDE = datetime(2026, 7, 22, tzinfo=timezone.utc).timestamp()


def apuesta(ts, texto, resultado, unidades):
    return {"ts": int(ts), "texto": texto, "resultado": resultado, "unidades": unidades}


class ConCliente(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        persona(self.con, 500, nombre="Ana", username="ana")
        persona(self.con, 900, nombre="Admin", username="jefe")
        with self.con:
            self.con.execute("UPDATE ventas_personas SET admin = 1 WHERE user_id = 900")
        compra(self.con, "v1", 1, T, "ana@example.com", entra=500)
        compra(self.con, "v2", 2, T + 1000, "ana@example.com", entra=500)
        compra(self.con, "v3", 2, T + 2000, "bob@example.com")  # sin persona
        compra(self.con, "v0", 1, DESDE - 86400, "ana@example.com")  # antes del 22/07: no cuenta
        entra_movimiento(self.con, 1, 99, 900, T + 30, None)  # el equipo no sale
        # Canal 3: gratis por privado; canal 4: entra sin compra ni gratis.
        for n in (3, 4):
            with self.con:
                self.con.execute("INSERT INTO ventas_canales (canal_id, titulo, leido_ts) VALUES (?, ?, 0)",
                                 (n, f"Canal {n}"))
        with self.con:
            db.guardar_enlace(self.con, "hashcanal3", 3, "Canal 3", 1)
            publicaciones.guardar_privados(self.con, 500, [(1, T + 50, "hashcanal3")])
        entra_movimiento(self.con, 3, 31, 500, T + 200, None)
        entra_movimiento(self.con, 4, 41, 500, T + 300, None)
        indicar(self.con, "ana@example.com", "@ana")
        self.apuestas = {
            1: [apuesta(T - 7200, "09:00 Romford T1 Cuota 2 Stake 1", "gano", 1),  # corrida antes de entrar
                apuesta(T + 100, "14:37 Harlow T5 Cuota 4.33 Stake 3", "gano", 9.54)],
            2: [apuesta(T + 1500, "18:02 Hove T2 Cuota 2 Stake 2", "perdio", -2)],
            3: [apuesta(T + 400, "19:10 Towcester T4 Cuota 3 Stake 1", None, None)],
            4: [apuesta(T + 500, "20:15 Romford T1 Cuota 4.5 Stake 1", "gano", 3.5)],
        }

    def cuentas(self):
        return cuentas.calcular(self.con, cruce.calcular(self.con), self.apuestas, DESDE, del_equipo=set())


class TestCalcular(ConCliente):
    def test_persona(self):
        personas, _ = self.cuentas()
        self.assertEqual(set(personas), {500})
        ana = personas[500]
        self.assertEqual((ana["correos"], ana["compras"], ana["euros"]), (["ana@example.com"], 2, 60))
        self.assertEqual((ana["pagados"], ana["gratis"], ana["sin_explicar"]), (2, 1, 1))
        self.assertEqual((ana["apuestas"], ana["ganadas"], ana["perdidas"], ana["sin_resultado"]), (4, 2, 1, 1))
        self.assertAlmostEqual(ana["unidades"], 11.04)

    def test_correo_sin_persona(self):
        _, sin_persona = self.cuentas()
        bob = sin_persona["bob@example.com"]
        self.assertEqual((bob["compras"], bob["euros"], bob["pagados"], bob["apuestas"], bob["perdidas"]),
                         (1, 30, 1, 1, 1))
        self.assertEqual(bob["unidades"], -2)


class TestFilas(ConCliente):
    def test_simulacion_y_balance(self):
        personas, sin_persona = self.cuentas()
        filas = cuentas.filas(personas, sin_persona, cruce.calcular(self.con).personas)
        ana = filas[0]
        self.assertEqual(ana[:3], ["Ana (@ana)", 500, "ana@example.com"])
        self.assertEqual(ana[3:], [2, 60, 2, 1, 1, 4, 2, 1, 1, 11.04, 110.4, 50.4])
        self.assertEqual(filas[1], [""])  # separación
        self.assertEqual(filas[2][0], cuentas.TITULO_SIN_PERSONA)
        bob = filas[3]
        self.assertEqual(bob[:3], ["", "", "bob@example.com"])
        self.assertEqual(bob[3:], [1, 30, 1, "", "", 1, 0, 1, 0, -2, -20, -50])

    def test_pestana(self):
        from premier_captacion import sheet

        from .test_sheet import LibroFalso
        falso = LibroFalso()
        libro = sheet.LibroGoogle(falso)
        libro.preparar()
        personas, sin_persona = self.cuentas()
        cuentas.escribir_pestana(libro, cuentas.filas(personas, sin_persona, {}))
        tabla = falso.hoja(cuentas.TAB).tabla()
        self.assertEqual(tabla[0], cuentas.CABECERA)
        self.assertEqual(tabla[1][2], "ana@example.com")

    def test_la_sincronizacion_la_escribe(self):
        from premier_captacion import pagos, sheet

        from .test_sheet import LibroFalso
        falso = LibroFalso()
        libro = sheet.LibroGoogle(falso)
        libro.preparar()
        pagos.escribir_pestanas(self.con, MADRID, libro, picks={})
        self.assertEqual(falso.hoja(cuentas.TAB).tabla()[1][2], "ana@example.com")


if __name__ == "__main__":
    unittest.main()
