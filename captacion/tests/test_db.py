import os
import sqlite3
import tempfile
import threading
import unittest

from premier_captacion import db


class TestMigraciones(unittest.TestCase):
    def test_base_nueva_queda_en_la_ultima_version(self):
        con = db.abrir(":memory:")
        self.addCleanup(con.close)
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], len(db.MIGRACIONES))
        columnas = {f[1] for f in con.execute("PRAGMA table_info(usuarios)")}
        self.assertIn("enlace_venta_ts", columnas)

    def test_actualiza_una_base_de_la_version_1_sin_perder_datos(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "vieja.db")
            vieja = sqlite3.connect(ruta)
            vieja.executescript(db.MIGRACIONES[0] + "\nPRAGMA user_version = 1;")
            vieja.execute("INSERT INTO usuarios (user_id, nombre, creado_ts, actualizado_ts, bienvenida_ts) "
                          "VALUES (5, 'Ana', 1, 1, 1)")
            vieja.commit()
            vieja.close()

            con = db.abrir(ruta)
            self.addCleanup(con.close)
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], len(db.MIGRACIONES))
            fila = db.obtener_usuario(con, 5)
            self.assertEqual(fila["nombre"], "Ana")
            self.assertIsNone(fila["enlace_venta_ts"])
            self.assertTrue(db.es_del_embudo(fila))

    def test_varios_procesos_abriendo_a_la_vez_no_fallan(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "nueva.db")
            errores = []

            def abrir():
                try:
                    db.abrir(ruta).close()
                except Exception as e:  # pragma: no cover - solo si falla
                    errores.append(e)

            hilos = [threading.Thread(target=abrir) for _ in range(6)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join()
            self.assertEqual(errores, [])
            con = db.abrir(ruta)
            self.addCleanup(con.close)
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], len(db.MIGRACIONES))


class TestAyudas(unittest.TestCase):
    def test_actualizar_campos_y_enlaces(self):
        con = db.abrir(":memory:")
        self.addCleanup(con.close)
        with con:
            db.actualizar_datos_usuario(con, 10, {"id": 7, "first_name": "Pepe"})
            db.actualizar_campos(con, 7, 20, boton="primera_vez", carpeta="10.14")
            db.guardar_enlace(con, "AbCdEf123", 1234567890, "Canal", 30)
            db.guardar_enlace(con, "AbCdEf123", 1234567890, "Canal renombrado", 40)
        fila = db.obtener_usuario(con, 7)
        self.assertEqual((fila["boton"], fila["carpeta"], fila["actualizado_ts"]), ("primera_vez", "10.14", 20))
        self.assertFalse(db.es_del_embudo(fila))
        self.assertEqual(db.enlace_guardado(con, "AbCdEf123")["titulo"], "Canal renombrado")
        self.assertIsNone(db.enlace_guardado(con, "otro"))


if __name__ == "__main__":
    unittest.main()
